import json

import frappe
from frappe import _
from frappe.utils import flt

PLANNING_ITEM_FIELD = "project_material_planning_item"


def get_po_aggregates(planning):
	"""Sum quantities/amounts of submitted Purchase Order Items linked to this planning doc."""
	keys = [row.name for row in planning.items]
	if not keys:
		return {}
	rows = frappe.db.sql(
		f"""
		SELECT poi.{PLANNING_ITEM_FIELD} AS `key`,
			SUM(poi.qty) AS qty,
			SUM(poi.base_amount) AS amount
		FROM `tabPurchase Order Item` poi
		INNER JOIN `tabPurchase Order` po ON po.name = poi.parent
		WHERE po.docstatus = 1
			AND poi.{PLANNING_ITEM_FIELD} IN %(keys)s
		GROUP BY poi.{PLANNING_ITEM_FIELD}
		""",
		{"keys": keys},
		as_dict=1,
	)
	return {row["key"]: row for row in rows}


def get_pr_aggregates(planning):
	"""Sum quantities/amounts of submitted Purchase Receipt Items linked to this planning doc."""
	keys = [row.name for row in planning.items]
	if not keys:
		return {}
	rows = frappe.db.sql(
		f"""
		SELECT pri.{PLANNING_ITEM_FIELD} AS `key`,
			SUM(pri.qty) AS qty,
			SUM(pri.base_amount) AS amount
		FROM `tabPurchase Receipt Item` pri
		INNER JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
		WHERE pr.docstatus = 1
			AND pri.{PLANNING_ITEM_FIELD} IN %(keys)s
		GROUP BY pri.{PLANNING_ITEM_FIELD}
		""",
		{"keys": keys},
		as_dict=1,
	)
	return {row["key"]: row for row in rows}


def get_po_draft_aggregates(planning, exclude_po=None):
	"""Sum quantities/amounts of DRAFT Purchase Order Items linked to this planning doc.
	Pending (unsubmitted) orders count against the requirement to avoid duplicate ordering."""
	keys = [row.name for row in planning.items]
	if not keys:
		return {}
	exclude = "AND po.name != %(exclude)s" if exclude_po else ""
	rows = frappe.db.sql(
		f"""
		SELECT poi.{PLANNING_ITEM_FIELD} AS `key`,
			SUM(poi.qty) AS qty,
			SUM(poi.base_amount) AS amount
		FROM `tabPurchase Order Item` poi
		INNER JOIN `tabPurchase Order` po ON po.name = poi.parent
		WHERE po.docstatus = 0
			AND poi.{PLANNING_ITEM_FIELD} IN %(keys)s
			{exclude}
		GROUP BY poi.{PLANNING_ITEM_FIELD}
		""",
		{"keys": keys, "exclude": exclude_po},
		as_dict=1,
	)
	return {row["key"]: row for row in rows}


def get_purchase_history(planning):
	"""Submitted Purchase Orders and Purchase Receipts linked to this planning doc,
	merged into a single history feed (PO entries carry the excess purchase reason)."""
	keys = [row.name for row in planning.items]
	if not keys:
		return []
	rows = frappe.db.sql(
		f"""
		SELECT posting_date, entry_type, supplier, purchase_order, purchase_receipt,
			item, qty, rate, amount, reason
		FROM (
			SELECT po.transaction_date AS posting_date,
				'PO' AS entry_type,
				po.supplier,
				po.name AS purchase_order,
				NULL AS purchase_receipt,
				poi.item_code AS item,
				poi.qty,
				poi.base_rate AS rate,
				poi.base_amount AS amount,
				poi.excess_purchase_reason AS reason
			FROM `tabPurchase Order Item` poi
			INNER JOIN `tabPurchase Order` po ON po.name = poi.parent
			WHERE po.docstatus = 1
				AND poi.{PLANNING_ITEM_FIELD} IN %(keys)s

			UNION ALL

			SELECT pr.posting_date,
				'PR' AS entry_type,
				pr.supplier,
				pri.purchase_order,
				pr.name AS purchase_receipt,
				pri.item_code AS item,
				pri.qty,
				pri.base_rate AS rate,
				pri.base_amount AS amount,
				NULL AS reason
			FROM `tabPurchase Receipt Item` pri
			INNER JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
			WHERE pr.docstatus = 1
				AND pri.{PLANNING_ITEM_FIELD} IN %(keys)s
		) history
		ORDER BY posting_date, purchase_order, purchase_receipt
		""",
		{"keys": keys},
		as_dict=1,
	)
	return rows


def get_purchase_order_history(planning):
	"""Submitted Purchase Orders linked to this planning doc, for the ordering dashboard."""
	keys = [row.name for row in planning.items]
	if not keys:
		return []
	rows = frappe.db.sql(
		f"""
		SELECT po.transaction_date AS posting_date,
			po.name AS purchase_order,
			po.supplier,
			po.status,
			poi.item_code AS item,
			poi.qty,
			poi.base_rate AS rate,
			poi.base_amount AS amount
		FROM `tabPurchase Order Item` poi
		INNER JOIN `tabPurchase Order` po ON po.name = poi.parent
		WHERE po.docstatus = 1
			AND poi.{PLANNING_ITEM_FIELD} IN %(keys)s
		ORDER BY po.transaction_date, po.name
		""",
		{"keys": keys},
		as_dict=1,
	)
	return rows


def recalculate_planning(doc):
	"""
	Recompute every derived value on a Project Material Planning document from
	submitted Purchase Orders and Purchase Receipts. Idempotent - it never
	increments/decrements, so cancels and amendments reverse automatically.
	"""
	po_data = get_po_aggregates(doc)
	pr_data = get_pr_aggregates(doc)

	total_required_cost = 0.0
	total_received_cost = 0.0
	required_qty_sum = 0.0
	received_qty_sum = 0.0
	remaining_qty_sum = 0.0

	for row in doc.items:
		po = po_data.get(row.name, {})
		pr = pr_data.get(row.name, {})

		row.po_qty = flt(po.get("qty"))
		row.received_qty = flt(pr.get("qty"))
		row.estimated_amount = flt(row.required_qty) * flt(row.estimated_rate)
		row.actual_amount = flt(pr.get("amount"))
		row.actual_rate = flt(row.actual_amount / row.received_qty) if flt(row.received_qty) else 0

		row.remaining_qty = max(flt(row.required_qty) - flt(row.received_qty), 0)
		row.excess_qty = max(flt(row.received_qty) - flt(row.required_qty), 0)
		row.variance_qty = flt(row.received_qty) - flt(row.required_qty)
		row.exceeded = 1 if row.received_qty > flt(row.required_qty) else 0

		total_required_cost += flt(row.estimated_amount)
		total_received_cost += flt(row.actual_amount)
		required_qty_sum += flt(row.required_qty)
		received_qty_sum += flt(row.received_qty)
		remaining_qty_sum += flt(row.remaining_qty)

	doc.set("purchase_orders", get_purchase_order_history(doc))
	doc.set("purchase_history", get_purchase_history(doc))

	doc.total_required_cost = total_required_cost
	doc.total_purchased_cost = total_received_cost
	doc.total_remaining_cost = max(total_required_cost - total_received_cost, 0)

	doc.required_items = required_qty_sum
	doc.purchased_items = received_qty_sum
	doc.remaining_items = remaining_qty_sum

	doc.quantity_progress = flt(received_qty_sum / required_qty_sum * 100) if required_qty_sum else 0
	doc.cost_progress = flt(total_received_cost / total_required_cost * 100) if total_required_cost else 0
	doc.project_progress = flt(doc.quantity_progress)


def update_planning(planning_name):
	"""Recompute and save the planning document (used from PO/PR doc events)."""
	if not planning_name:
		return
	try:
		planning = frappe.get_doc("Project Material Planning", planning_name)
	except frappe.DoesNotExistError:
		return
	recalculate_planning(planning)
	planning.save(ignore_permissions=True)


def validate_purchase_order(doc, method=None):
	"""Server-side excess quantity validation for Purchase Order items (cannot be bypassed)."""
	if not doc.get("project_material_planning") or not doc.get("items"):
		return
	if not frappe.db.exists("Project Material Planning", doc.project_material_planning):
		return

	current = {}
	for item in doc.items:
		key = item.get(PLANNING_ITEM_FIELD)
		if key:
			current[key] = flt(current.get(key, 0)) + flt(item.qty)

	planning = frappe.get_doc("Project Material Planning", doc.project_material_planning)
	item_rows = {row.name: row for row in planning.items}
	submitted = get_po_aggregates(planning)
	drafts = get_po_draft_aggregates(planning, exclude_po=doc.name)

	for item in doc.items:
		key = item.get(PLANNING_ITEM_FIELD)
		if not key:
			continue
		if key not in item_rows:
			frappe.throw(
				_("Row #{0}: Project Material Planning Item {1} does not belong to {2}").format(
					item.idx, key, doc.project_material_planning
				),
				title=_("Invalid Project Material Planning Item"),
			)
		required = flt(item_rows[key].required_qty) if key in item_rows else 0
		already = flt(submitted.get(key, {}).get("qty", 0)) + flt(drafts.get(key, {}).get("qty", 0))
		total = already + flt(current.get(key))
		excess = flt(total - required)
		item.exceeds_project_requirement = 1 if excess > 0 else 0
		item.excess_quantity = max(excess, 0)
		if item.exceeds_project_requirement and not item.get("excess_purchase_reason"):
			frappe.throw(
				_(
					"Row #{0}: Purchase quantity exceeds the required quantity for the project.\n\n"
					"Required Qty: {1}\nAlready Ordered (incl. Drafts): {2}\nNew Total: {3}\nExcess Qty: {4}\n\n"
					"Excess Purchase Reason is mandatory for excess purchases."
				).format(item.idx, required, already, total, excess),
				title=_("Excess Purchase"),
			)


def resolve_purchase_receipt_planning(doc, method=None):
	"""Inherit the project material planning reference from linked Purchase Order items."""
	if not doc.get("items"):
		return

	for item in doc.items:
		if not item.get(PLANNING_ITEM_FIELD) and item.get("purchase_order_item"):
			item.set(
				PLANNING_ITEM_FIELD,
				frappe.db.get_value("Purchase Order Item", item.purchase_order_item, PLANNING_ITEM_FIELD),
			)

	if not doc.get("project_material_planning"):
		for item in doc.items:
			if item.get(PLANNING_ITEM_FIELD):
				doc.project_material_planning = frappe.db.get_value(
					"Project Material Planning Item", item.get(PLANNING_ITEM_FIELD), "parent"
				)
				break


def on_purchase_order_submit(doc, method=None):
	update_planning(doc.get("project_material_planning"))


def on_purchase_order_cancel(doc, method=None):
	update_planning(doc.get("project_material_planning"))


def on_purchase_receipt_submit(doc, method=None):
	update_planning(doc.get("project_material_planning"))


def on_purchase_receipt_cancel(doc, method=None):
	update_planning(doc.get("project_material_planning"))


@frappe.whitelist()
def validate_po_item_excess(planning_item, requested_qty, already_submitted=0, po_name=None):
	"""Whitelisted helper for client-side live feedback on PO item quantity.
	Counts already submitted AND pending draft POs of the same plan against the requirement."""
	row = frappe.db.get_value(
		"Project Material Planning Item",
		planning_item,
		["required_qty", "parent"],
		as_dict=True,
	)
	if not row:
		return {}
	planning = frappe.get_doc("Project Material Planning", row.parent)
	already = (
		flt(already_submitted)
		+ flt(get_po_aggregates(planning).get(planning_item, {}).get("qty", 0))
		+ flt(get_po_draft_aggregates(planning, exclude_po=po_name).get(planning_item, {}).get("qty", 0))
	)
	total = already + flt(requested_qty)
	excess = flt(total - flt(row.required_qty))
	return {
		"required": flt(row.required_qty),
		"already_ordered": already,
		"requested": flt(requested_qty),
		"total": total,
		"excess": max(excess, 0),
		"exceeds": excess > 0,
	}


@frappe.whitelist()
def get_create_po_items(planning_name):
	"""Per-item data for the Create Purchase Order dialog.
	Prefilled qty = remaining (required - received) minus pending draft POs, so duplicates are
	not suggested."""
	planning = frappe.get_doc("Project Material Planning", planning_name)
	submitted = get_po_aggregates(planning)
	drafts = get_po_draft_aggregates(planning)
	out = []
	for row in planning.items:
		out.append(
			{
				"project_material_planning_item": row.name,
				"item_code": row.item,
				"required_qty": flt(row.required_qty),
				"received_qty": flt(row.received_qty),
				"submitted_qty": flt(submitted.get(row.name, {}).get("qty", 0)),
				"draft_po_qty": flt(drafts.get(row.name, {}).get("qty", 0)),
				"remaining_qty": max(flt(row.required_qty) - flt(row.received_qty), 0),
				"estimated_rate": flt(row.estimated_rate),
			}
		)
	return out


@frappe.whitelist()
def validate_po_items_excess(planning_name, items=None):
	"""Whitelisted batch excess check for the create-purchase-order dialog items."""
	if isinstance(items, str):
		items = json.loads(items)
	if not planning_name or not items:
		return []

	planning = frappe.get_doc("Project Material Planning", planning_name)
	item_rows = {row.name: row for row in planning.items}
	submitted = get_po_aggregates(planning)
	drafts = get_po_draft_aggregates(planning)

	out = []
	for entry in items:
		row = item_rows.get(entry.get(PLANNING_ITEM_FIELD))
		if not row and entry.get("item_code"):
			row = next((r for r in planning.items if r.item == entry.get("item_code")), None)
		if not row:
			continue
		requested = flt(entry.get("qty"))
		already = flt(submitted.get(row.name, {}).get("qty", 0)) + flt(drafts.get(row.name, {}).get("qty", 0))
		total = already + requested
		excess = flt(total - flt(row.required_qty))
		if excess > 0:
			out.append(
				{
					"item_code": entry.get("item_code") or row.item,
					PLANNING_ITEM_FIELD: row.name,
					"required": flt(row.required_qty),
					"already_ordered": already,
					"requested": requested,
					"total": total,
					"excess": excess,
				}
			)
	return out


@frappe.whitelist()
def create_purchase_order(planning_name, supplier, schedule_date=None, items=None, company=None):
	"""Create a draft Purchase Order against the selected planning items."""
	if isinstance(items, str):
		items = json.loads(items)
	if not planning_name or not supplier:
		frappe.throw(_("Project Material Planning and Supplier are required."))
	if not items:
		frappe.throw(_("At least one item is required."))

	planning = frappe.get_doc("Project Material Planning", planning_name)
	item_rows = {row.name: row for row in planning.items}
	if not company:
		company = frappe.defaults.get_user_default("company") or frappe.db.get_single_value(
			"Global Defaults", "default_company"
		)

	po = frappe.new_doc("Purchase Order")
	po.supplier = supplier
	po.company = company
	po.project_material_planning = planning_name
	if schedule_date:
		po.schedule_date = schedule_date
		po.transaction_date = schedule_date

	for entry in items:
		row = item_rows.get(entry.get(PLANNING_ITEM_FIELD))
		if not row and entry.get("item_code"):
			row = next((r for r in planning.items if r.item == entry.get("item_code")), None)
		item_code = entry.get("item_code") or (row.item if row else None)
		if not item_code:
			continue
		po.append(
			"items",
			{
				"item_code": item_code,
				"qty": flt(entry.get("qty")),
				"rate": flt(entry.get("rate"))
				if entry.get("rate")
				else flt(row.estimated_rate if row else 0),
				"uom": frappe.db.get_value("Item", item_code, "stock_uom"),
				"warehouse": frappe.db.get_value(
					"Item Default", {"parent": item_code, "company": company}, "default_warehouse"
				),
				"schedule_date": schedule_date,
				"excess_purchase_reason": entry.get("excess_purchase_reason") or "",
				PLANNING_ITEM_FIELD: row.name if row else entry.get(PLANNING_ITEM_FIELD),
			},
		)

	po.insert()
	return po.name
