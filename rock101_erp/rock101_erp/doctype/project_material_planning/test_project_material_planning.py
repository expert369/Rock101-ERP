import frappe
from erpnext.buying.doctype.supplier.test_supplier import create_supplier
from erpnext.stock.doctype.item.test_item import make_item
from erpnext.stock.doctype.warehouse.test_warehouse import create_warehouse
from frappe.model.workflow import apply_workflow
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from rock101_erp.controllers.material_planning import ensure_planning_workflow


class TestProjectMaterialPlanning(FrappeTestCase):
	def setUp(self):
		self.company = "PJ"
		self.warehouse = create_warehouse(
			"Rock101 Test Warehouse",
			company=self.company,
			properties={"parent_warehouse": "All Warehouses - P"},
		)
		self.supplier = create_supplier(supplier_name=frappe.generate_hash(length=8))
		self.cement = self.make_stock_item("Rock101 Cement")
		self.steel = self.make_stock_item("Rock101 Steel Bar")
		ensure_planning_workflow()

	def tearDown(self):
		frappe.db.rollback()

	def make_stock_item(self, item_code):
		item = make_item(item_code)
		if not item.item_defaults or item.item_defaults[0].company != self.company:
			item_default = item.item_defaults[0] if item.item_defaults else item.append("item_defaults", {})
			item_default.company = self.company
			item_default.default_warehouse = self.warehouse
			item.save()
		return item.name

	def make_planning(self, items=None):
		planning = frappe.get_doc(
			{
				"doctype": "Project Material Planning",
				"project_id": "house-test-001",
				"project_name": "Test House",
				"items": items
				or [
					{"item": self.cement, "required_qty": 10, "estimated_rate": 500, "uom": "Nos"},
					{"item": self.steel, "required_qty": 20, "estimated_rate": 250, "uom": "Nos"},
				],
			}
		)
		planning.insert()
		return planning

	def make_purchase_order(self, planning, supplier=None, qty_items=None):
		planning_item_rows = {row.item: row for row in planning.items}
		po = frappe.new_doc("Purchase Order")
		po.supplier = supplier or self.supplier
		po.company = self.company
		po.transaction_date = frappe.utils.today()
		po.schedule_date = frappe.utils.today()
		po.project_material_planning = planning.name
		for item_code, qty in (qty_items or {}).items():
			row = planning_item_rows[item_code]
			po.append(
				"items",
				{
					"item_code": item_code,
					"qty": qty,
					"rate": row.estimated_rate,
					"uom": "Nos",
					"warehouse": self.warehouse,
					"schedule_date": frappe.utils.today(),
					"project_material_planning_item": row.name,
				},
			)
		return po

	def make_purchase_receipt(self, planning, po, qty_items=None):
		po_items = {row.item_code: row for row in po.items}
		planning_item_rows = {row.item: row for row in planning.items}
		pr = frappe.new_doc("Purchase Receipt")
		pr.supplier = po.supplier
		pr.company = self.company
		pr.posting_date = frappe.utils.today()
		for item_code, qty in (qty_items or {}).items():
			po_item = po_items[item_code]
			pr.append(
				"items",
				{
					"item_code": item_code,
					"qty": qty,
					"rate": po_item.rate,
					"uom": "Nos",
					"warehouse": self.warehouse,
					"purchase_order": po.name,
					"purchase_order_item": po_item.name,
					"project_material_planning_item": planning_item_rows[item_code].name,
				},
			)
		return pr

	def test_project_id_uppercased(self):
		planning = self.make_planning()
		self.assertEqual(planning.project_id, "HOUSE-TEST-001")

	def test_initial_recalculate(self):
		planning = self.make_planning()
		rows = {row.item: row for row in planning.items}
		self.assertEqual(flt(rows[self.cement].estimated_amount), 5000)
		self.assertEqual(flt(planning.total_required_cost), 10000)
		self.assertEqual(flt(planning.quantity_progress), 0)
		self.assertEqual(flt(planning.cost_progress), 0)

	def test_po_within_requirement_allowed(self):
		planning = self.make_planning()
		po = self.make_purchase_order(planning, qty_items={self.cement: 5, self.steel: 10})
		po.insert()
		po.submit()

		po.reload()
		cement_item = next(row for row in po.items if row.item_code == self.cement)
		self.assertEqual(cement_item.exceeds_project_requirement, 0)
		self.assertEqual(flt(cement_item.excess_quantity), 0)

		planning.reload()
		row = next(r for r in planning.items if r.item == self.cement)
		self.assertEqual(flt(row.po_qty), 5)
		self.assertEqual(flt(row.received_qty), 0)

	def test_po_excess_requires_reason(self):
		planning = self.make_planning()
		po = self.make_purchase_order(planning, qty_items={self.cement: 11})
		with self.assertRaises(frappe.ValidationError):
			po.insert()

		po = self.make_purchase_order(planning, qty_items={self.cement: 11})
		po.items[0].excess_purchase_reason = "Supplier minimum order quantity is 11 pieces."
		po.insert()
		po.reload()
		self.assertEqual(po.items[0].exceeds_project_requirement, 1)
		self.assertEqual(flt(po.items[0].excess_quantity), 1)
		po.submit()

		planning.reload()
		row = next(r for r in planning.items if r.item == self.cement)
		self.assertEqual(flt(row.po_qty), 11)

		# the excess reason is carried into the planning's purchase history
		po_row = next(r for r in planning.purchase_history if r.entry_type == "PO")
		self.assertEqual(po_row.purchase_order, po.name)
		self.assertEqual(po_row.reason, "Supplier minimum order quantity is 11 pieces.")

	def test_pr_submit_updates_planning(self):
		planning = self.make_planning()
		po = self.make_purchase_order(planning, qty_items={self.cement: 5, self.steel: 10})
		po.insert()
		po.submit()

		pr = self.make_purchase_receipt(planning, po, qty_items={self.cement: 5})
		pr.insert()
		pr.submit()

		planning.reload()
		row = next(r for r in planning.items if r.item == self.cement)
		self.assertEqual(flt(row.received_qty), 5)
		self.assertEqual(flt(row.remaining_qty), 5)
		self.assertEqual(flt(row.actual_amount), 2500)
		self.assertEqual(flt(row.actual_rate), 500)

		self.assertEqual(flt(planning.total_purchased_cost), 2500)
		self.assertEqual(flt(planning.total_remaining_cost), 7500)
		self.assertAlmostEqual(planning.quantity_progress, 5 / 30 * 100, places=4)
		self.assertAlmostEqual(planning.cost_progress, 25, places=2)
		self.assertEqual(flt(planning.purchased_items), 5)
		self.assertEqual(flt(planning.remaining_items), 25)

		# purchase history populated (PO lines + PR lines, typed)
		self.assertEqual(len(planning.purchase_history), 3)
		po_rows = [r for r in planning.purchase_history if r.entry_type == "PO"]
		pr_rows = [r for r in planning.purchase_history if r.entry_type == "PR"]
		self.assertEqual(len(po_rows), 2)
		self.assertEqual(len(pr_rows), 1)
		self.assertEqual(pr_rows[0].purchase_receipt, pr.name)
		self.assertEqual(flt(pr_rows[0].qty), 5)
		self.assertEqual(po_rows[0].purchase_order, po.name)

	def test_pr_cancel_reverses_planning(self):
		planning = self.make_planning()
		po = self.make_purchase_order(planning, qty_items={self.cement: 5, self.steel: 10})
		po.insert()
		po.submit()

		pr = self.make_purchase_receipt(planning, po, qty_items={self.cement: 5})
		pr.insert()
		pr.submit()

		pr.cancel()

		planning.reload()
		row = next(r for r in planning.items if r.item == self.cement)
		self.assertEqual(flt(row.received_qty), 0)
		self.assertEqual(flt(row.remaining_qty), 10)
		self.assertEqual(flt(row.actual_amount), 0)
		self.assertEqual(flt(planning.total_purchased_cost), 0)
		self.assertEqual(flt(planning.quantity_progress), 0)
		self.assertEqual(flt(planning.purchased_items), 0)

		# only the PO lines remain in history after the receipt is cancelled
		self.assertEqual(len(planning.purchase_history), 2)
		self.assertTrue(all(r.entry_type == "PO" for r in planning.purchase_history))

	def test_remaining_floored_at_zero_and_excess_tracked(self):
		planning = self.make_planning()
		po = self.make_purchase_order(
			planning, qty_items={self.cement: 11, self.steel: 20}, supplier=self.supplier
		)
		po.items[0].excess_purchase_reason = "Supplier minimum order quantity."
		po.insert()
		po.submit()

		pr = self.make_purchase_receipt(planning, po, qty_items={self.cement: 11})
		pr.insert()
		pr.submit()

		planning.reload()
		row = next(r for r in planning.items if r.item == self.cement)
		self.assertEqual(flt(row.received_qty), 11)
		self.assertEqual(flt(row.remaining_qty), 0)
		self.assertEqual(flt(row.excess_qty), 1)
		self.assertEqual(row.exceeded, 1)
		self.assertEqual(flt(row.variance_qty), 1)

	def test_multiple_po_pr_recalc_from_source(self):
		planning = self.make_planning()
		po1 = self.make_purchase_order(planning, qty_items={self.cement: 5, self.steel: 10})
		po1.insert()
		po1.submit()

		po2 = self.make_purchase_order(planning, qty_items={self.cement: 5, self.steel: 10})
		po2.insert()
		po2.submit()

		pr1 = self.make_purchase_receipt(planning, po1, qty_items={self.cement: 3})
		pr1.insert()
		pr1.submit()

		pr2 = self.make_purchase_receipt(planning, po2, qty_items={self.cement: 2})
		pr2.insert()
		pr2.submit()

		pr2.cancel()

		planning.reload()
		cement = next(r for r in planning.items if r.item == self.cement)
		steel = next(r for r in planning.items if r.item == self.steel)
		self.assertEqual(flt(cement.po_qty), 10)
		self.assertEqual(flt(cement.received_qty), 3)
		self.assertEqual(flt(steel.po_qty), 20)
		self.assertEqual(flt(planning.purchased_items), 3)
		self.assertEqual(flt(planning.remaining_items), 27)

	def test_purchase_recognized_on_receipt_only(self):
		planning = self.make_planning()
		po = self.make_purchase_order(planning, qty_items={self.cement: 5, self.steel: 10})
		po.insert()
		po.submit()

		planning.reload()
		# On order only: nothing is recognized as purchased yet
		self.assertEqual(flt(planning.purchased_items), 0)
		self.assertEqual(flt(planning.total_purchased_cost), 0)
		self.assertEqual(flt(planning.total_remaining_cost), 10000)
		self.assertEqual(flt(planning.remaining_items), 30)
		self.assertEqual(flt(planning.quantity_progress), 0)
		self.assertEqual(len(planning.purchase_orders), 2)
		first = next(r for r in planning.purchase_orders if r.item == self.cement)
		self.assertEqual(first.purchase_order, po.name)
		self.assertEqual(flt(first.qty), 5)

		# Only a submitted receipt counts as purchased
		pr = self.make_purchase_receipt(planning, po, qty_items={self.cement: 5})
		pr.insert()
		pr.submit()

		planning.reload()
		self.assertEqual(flt(planning.purchased_items), 5)
		self.assertEqual(flt(planning.total_purchased_cost), 2500)
		self.assertEqual(flt(planning.total_remaining_cost), 7500)
		self.assertEqual(flt(planning.remaining_items), 25)
		self.assertAlmostEqual(planning.cost_progress, 25, places=2)

		# Cancelling the receipt reverses the recognition
		pr.cancel()

		planning.reload()
		self.assertEqual(flt(planning.purchased_items), 0)
		self.assertEqual(flt(planning.total_purchased_cost), 0)
		self.assertEqual(flt(planning.total_remaining_cost), 10000)

	def test_create_purchase_order_dialog_flow(self):
		from rock101_erp.controllers.material_planning import create_purchase_order

		planning = self.make_planning()
		row = next(r for r in planning.items if r.item == self.cement)
		po_name = create_purchase_order(
			planning_name=planning.name,
			supplier=self.supplier,
			company=self.company,
			schedule_date=frappe.utils.today(),
			items=[
				{"item_code": self.cement, "qty": 10, "rate": 500, "project_material_planning_item": row.name}
			],
		)
		po = frappe.get_doc("Purchase Order", po_name)
		self.assertEqual(po.docstatus, 0)
		self.assertEqual(po.project_material_planning, planning.name)
		self.assertEqual(po.items[0].project_material_planning_item, row.name)
		frappe.delete_doc("Purchase Order", po_name, force=1)

	def test_create_purchase_order_excess_requires_reason(self):
		from rock101_erp.controllers.material_planning import (
			create_purchase_order,
			validate_po_items_excess,
		)

		planning = self.make_planning()
		row = next(r for r in planning.items if r.item == self.cement)
		entry = {
			"item_code": self.cement,
			"qty": 12,
			"rate": 500,
			"project_material_planning_item": row.name,
		}

		exceeded = validate_po_items_excess(planning.name, [entry])
		self.assertEqual(len(exceeded), 1)
		self.assertEqual(exceeded[0]["required"], 10)
		self.assertEqual(exceeded[0]["total"], 12)
		self.assertEqual(exceeded[0]["excess"], 2)

		with self.assertRaises(frappe.ValidationError):
			create_purchase_order(
				planning_name=planning.name,
				supplier=self.supplier,
				company=self.company,
				schedule_date=frappe.utils.today(),
				items=[dict(entry)],
			)

		po_name = create_purchase_order(
			planning_name=planning.name,
			supplier=self.supplier,
			company=self.company,
			schedule_date=frappe.utils.today(),
			items=[dict(entry, excess_purchase_reason="Client approved rush top-up")],
		)
		po = frappe.get_doc("Purchase Order", po_name)
		self.assertEqual(po.docstatus, 0)
		self.assertEqual(po.items[0].excess_purchase_reason, "Client approved rush top-up")
		self.assertEqual(po.items[0].exceeds_project_requirement, 1)
		self.assertEqual(po.items[0].excess_quantity, 2)
		frappe.delete_doc("Purchase Order", po_name, force=1)

	def test_draft_po_counts_in_excess_check(self):
		from rock101_erp.controllers.material_planning import validate_po_items_excess

		planning = self.make_planning()
		row = next(r for r in planning.items if r.item == self.cement)

		draft = self.make_purchase_order(planning, qty_items={self.cement: 10})
		draft.insert()

		exceeded = validate_po_items_excess(
			planning.name,
			[{"item_code": self.cement, "qty": 1, "project_material_planning_item": row.name}],
		)
		self.assertEqual(len(exceeded), 1)
		self.assertEqual(exceeded[0]["required"], 10)
		self.assertEqual(exceeded[0]["already_ordered"], 10)
		self.assertEqual(exceeded[0]["total"], 11)
		self.assertEqual(exceeded[0]["excess"], 1)

		with self.assertRaises(frappe.ValidationError):
			self.make_purchase_order(planning, qty_items={self.cement: 1}).insert()

		po = self.make_purchase_order(planning, qty_items={self.cement: 1})
		po.items[0].excess_purchase_reason = "Draft order already covers the remaining requirement."
		po.insert()
		self.assertEqual(po.items[0].excess_quantity, 1)

		frappe.delete_doc("Purchase Order", po.name, force=1)
		frappe.delete_doc("Purchase Order", draft.name, force=1)

	def test_workflow_default_state_is_draft(self):
		planning = self.make_planning()
		self.assertEqual(planning.workflow_state, "Draft")
		self.assertEqual(planning.docstatus, 0)
		self.assertIsNone(planning.actual_date_finished)

	def test_workflow_start_moves_to_in_progress(self):
		planning = self.make_planning()
		apply_workflow(planning, "Start")
		planning.reload()
		self.assertEqual(planning.workflow_state, "In Progress")
		self.assertEqual(planning.docstatus, 1)

	def test_auto_finish_and_date_finished_at_100_percent(self):
		planning = self.make_planning()
		apply_workflow(planning, "Start")

		po = self.make_purchase_order(planning, qty_items={self.cement: 10, self.steel: 20})
		po.insert()
		po.submit()

		pr = self.make_purchase_receipt(planning, po, qty_items={self.cement: 10, self.steel: 20})
		pr.insert()
		pr.submit()

		planning.reload()
		self.assertEqual(flt(planning.project_progress), 100)
		self.assertEqual(planning.workflow_state, "Finished")
		self.assertEqual(planning.docstatus, 1)
		self.assertEqual(str(planning.actual_date_finished), frappe.utils.today())

	def test_no_finish_below_100_percent(self):
		planning = self.make_planning()
		apply_workflow(planning, "Start")

		po = self.make_purchase_order(planning, qty_items={self.cement: 5, self.steel: 10})
		po.insert()
		po.submit()

		pr = self.make_purchase_receipt(planning, po, qty_items={self.cement: 5})
		pr.insert()
		pr.submit()

		planning.reload()
		self.assertEqual(planning.workflow_state, "In Progress")
		self.assertIsNone(planning.actual_date_finished)
