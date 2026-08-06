# Rock101 ERP — Session Context Log

> Saved conversation for the Project Material Planning feature in the `rock101_erp` app.
> Workdir: `/home/aster/frappe-bench/apps/rock101_erp` · Bench: `/home/aster/frappe-bench`
> Stack: Frappe v15 · ERPNext 15.103.1 · bench 5.29.1 · Sites: `test.site` (tests), `rock101.site` (production)

---

## 1. Goal

Build Project Material Planning (PMO) into the ERPNext custom app `rock101_erp`: custom DocTypes, PO/PR
integration with server-side excess-quantity validation, idempotent recalculation from submitted
transactions, a "Create Purchase Order" button, and automated tests — deployed on test + production.

## 2. Key architecture decisions

- **Standalone planning doc** with an optional `project` Link to ERPNext Project; `project_id` is
  required, unique, auto-uppercased (normalized in `before_insert` + `before_validate`).
- **No submit/cancel workflow** on the plan — always editable; recalculated from source transactions.
- **Idempotent recalc**: sums of *submitted* (docstatus=1) PO/PR items grouped by the planning-item
  child-row link; never `+=`/`-=`, so PO/PR cancels reverse automatically.
- **Excess purchases allowed only with reason** (server-side, blocks Save/Submit of PO; client shows a
  live warning). Receiving over-plan is never blocked, only tracked (`excess_qty`, `exceeded`).
- **PO Qty (placed)** vs **Received Qty** tracked separately.

## 3. Module layout (important import paths)

- App package root: `rock101_erp/` (e.g. `/home/aster/frappe-bench/apps/rock101_erp/rock101_erp/`)
- Frappe module (Doctypes): `rock101_erp/rock101_erp/` ("Rock101 Erp")
  - doctypes: `rock101_erp.rock101_erp.doctype.<doctype>.<module>`
- App-level code:
  - Engine: `rock101_erp/controllers/material_planning.py` → import path **`rock101_erp.controllers.material_planning`** (NOT `rock101_erp.rock101_erp.controllers...`)
  - Hooks: `rock101_erp/hooks.py`, custom fields: `rock101_erp/customizations.py`, install: `rock101_erp/install.py`
  - Patches: `rock101_erp.patches.v1_0_add_material_planning_custom_fields` (file `rock101_erp/patches/...`)
- Client scripts: `rock101_erp/public/js/{purchase_order,purchase_receipt,project_material_planning}.js`

## 4. Deliverables built

### DocTypes
- **Project Material Planning** (`project_material_planning`): project_id (unique, reqd, uppercased),
  project link, dates, currency (read-only, default from Global Defaults), progress fields, Items
  table, Purchase Orders table (read-only), Purchase History table (read-only), Notes.
  Permissions: System Manager / Projects Manager / Purchase Manager / Purchase User (full), All (read).
  `autoname: "field:project_id"` — doc name == project id.
- **Project Material Planning Item** (child): item, description (fetch from item), uom (fetch from
  `item.stock_uom`), required_qty, estimated_rate, estimated_amount (read-only, qty×rate, in grid),
  po_qty, received_qty, remaining_qty (= max(required−received, 0)), excess_qty, variance_qty,
  exceeded, actual_rate (weighted avg), actual_amount.
- **Project Material Planning Purchase Order** (child, read-only): date, supplier, PO, status, item,
  qty, rate, amount — logs submitted PO lines.
- **Project Material Planning History** (child, read-only): date, supplier, PO, PR, item, qty, rate,
  amount — logs submitted PR lines.

### Engine — `rock101_erp/controllers/material_planning.py`
- `get_po_aggregates` / `get_pr_aggregates` / `get_purchase_order_history` / `get_purchase_history`
  (SQL over submitted docs; PO uses `transaction_date`, PR uses `posting_date`; item column aliased
  as `item` to match child field name).
- `recalculate_planning(doc)` — idempotent; sets all derived values + both log tables.
- `update_planning(planning_name)` — recalc + save (used by PO/PR doc events).
- `validate_purchase_order` — excess check (`ordered-so-far + current line > required`); blocks
  submit/save unless `excess_purchase_reason`; validates item ownership.
- `resolve_purchase_receipt_planning` — inherits planning item from PO item on PR.
- PO/PR `on_submit` / `on_cancel` → `update_planning`.
- `@frappe.whitelist() validate_po_item_excess` — client live warning.
- `@frappe.whitelist() validate_po_items_excess(planning_name, items)` — batch excess check for
  the create-PO dialog (accounts for already-submitted POs).
- `@frappe.whitelist() create_purchase_order(planning_name, supplier, schedule_date, items, company)`
  — creates draft PO (warehouse from Item Default, planning refs set, opens the PO form). Accepts a
  per-item `excess_purchase_reason`; falls back to matching planning row by `item_code`. Draft
  insert runs the same excess guard (throws if reason missing).

### Integration
- hooks.py: `doc_events` for Purchase Order + Purchase Receipt (validate/on_submit/on_cancel),
  `override_doctype_class` → ProjectMaterialPlanning, `doctype_js` ×3, `after_install`.
  (**Note:** the Purchase Order `validate` hook was accidentally commented out in an earlier
  iteration — re-enabled it this session; the hard server-side block was silently off.)
- customizations.py: 7 Custom Fields (PO header planning link; PO Item: planning item link,
  exceeds_project_requirement, excess_quantity, excess_purchase_reason; PR + PR Item links).
- patches.txt → `v1_0_add_material_planning_custom_fields` (logged in Patch Log on prod).
- Client scripts: PO excess flow (`frappe.confirm` → required `frappe.prompt` for reason), PR
  planning-item inheritance, planning form **Create Purchase Order** dialog — batch check via
  `validate_po_items_excess`; if any qty exceeds, `frappe.confirm` (per-line required/already/new
  total/excess figures) → required `frappe.prompt` reason applied to all exceeding lines.

### Tests — `test_project_material_planning.py` (11 tests, all pass)
uppercase ID, initial recalc, PO within requirement, PO excess requires reason, PR submit updates,
PR cancel reverses, remaining floored at zero + excess tracked, multi-PO/PR recalc from source,
PO submit updates purchased_items + PO list (incl. cancel reversal), Create PO dialog flow,
Create PO batch excess (without reason throws; with reason → reason lands on the PO item).

> Run: `bench --site test.site run-tests --app rock101_erp --skip-test-records`
> (`--skip-test-records` required — this bench's app mix breaks test-record auto-generation for
> Payment Gateway; unrelated to the app).

## 5. Issues found & fixed this session

1. **`purchased_items` not updating on PO submit** — it summed `received_qty` (0 until receipt).
   Changed to sum `po_qty` (on-order quantity). `remaining_items` stays required−received.
2. **No PO list on the plan** — added the read-only Purchase Orders child table, populated in recalc.
3. **JS method path bug** — JS called `rock101_erp.rock101_erp.controllers.material_planning.*` but
   the module is `rock101_erp.controllers.material_planning.*` → "No module named
   'rock101_erp.rock101_erp.controllers'" on Create Purchase Order / excess warning. Fixed in
   `project_material_planning.js` and `purchase_order.js`.
4. **Uppercase reset bug** — with `autoname: "field:project_id"`, Frappe's `_sync_autoname_field`
   (base_document.py:1024, called from `_validate`) copies `name` back into `project_id` after
   `before_validate` had uppercased it (name is derived from the field at `set_new_name` *before*
   before_validate). That's why prod docs showed `project_id == name == random lowercase hash`
   (e.g. `5i1hoqloe5`). Fixed by normalizing in `before_insert` (runs before `set_new_name`).
5. **History/PO list Item column always empty** — SQL returned `item_code`, child field is `item`;
   fixed with `AS item`.
6. **PO has no `posting_date`** — uses `transaction_date` (broke first test run; fixed).
7. **Header totals semantics (final decision)** — after two iterations (received-based → PO-based →
   received-based), the agreed rule is: **a purchase is recognized only when stock is received**.
   `purchased_items` = Σ received_qty, `total_purchased_cost` = Σ received base_amount,
   `total_remaining_cost` = required − received, `cost_progress` = received/required. PO submit only
   updates per-row `po_qty`, the Purchase Orders log, and excess validation — not the purchased
   totals. Test: `test_purchase_recognized_on_receipt_only`.
8. **Excess purchase UX** — client `purchase_order.js` now shows `frappe.confirm` (required /
   already-ordered / total / excess figures); proceeding forces a required `frappe.prompt` for the
   Excess Purchase Reason, stored on the PO item (custom field made grid-visible via `in_list_view`).
   Server keeps a hard `frappe.throw` guard (a stray `msgprint` that let excess through silently was
   changed back to `throw`).
9. **Purchase History includes PO lines** — `get_purchase_history` UNIONs submitted PO items
   (entry_type `PO`, carrying `excess_purchase_reason`) with submitted PR items (entry_type `PR`).
   History child gained read-only `entry_type` + `reason` fields.

## 6. Environments

- `test.site`: apps frappe, erpnext, ecommerce_ph, doppio, rock101_erp. Test company "PJ"
  (warehouses under "All Warehouses - P"). Tests pass 10/10, ruff clean.
- `rock101.site`: production, developer_mode=1 + live_reload (no bench build needed for JS changes).
  Migrated: new doctypes/tables exist, patch logged, custom fields present, `get_controller` OK.

## 7. Notes / caveats

- The workflow doc (README.md) contains a user guide + mermaid workflow diagram (plan → order →
  excess check → receive → auto-update loop).
- `project_id` cannot be renamed after creation (name == field by design of `field:` autoname).
- Next move (not yet done): commit the work — repo only has the initial "feat: Initialize App"
  commit; `.github/workflows` diffs are pre-existing user changes, leave them alone.
- Test env quirk: `frappe.init`/logger need `sites_path` + the stray log dir
  `/home/aster/frappe-bench/test.site/logs` when running raw python against a site.

## 8. Current file inventory (modified/added)

- `rock101_erp/hooks.py`, `rock101_erp/patches.txt`
- `rock101_erp/controllers/material_planning.py` (+ `__init__.py`)
- `rock101_erp/customizations.py`, `rock101_erp/install.py`
- `rock101_erp/patches/v1_0_add_material_planning_custom_fields.py`
- `rock101_erp/public/js/{purchase_order,purchase_receipt,project_material_planning}.js`
- `rock101_erp/rock101_erp/doctype/{project_material_planning,project_material_planning_item,project_material_planning_history,project_material_planning_purchase_order}/` (json + py, incl. test file)
- `README.md` (user guide + workflow diagram)
