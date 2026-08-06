import frappe

CUSTOM_FIELDS = {
	"Purchase Order": [
		{
			"fieldname": "project_material_planning",
			"label": "Project Material Planning",
			"fieldtype": "Link",
			"options": "Project Material Planning",
			"insert_after": "supplier",
		},
	],
	"Purchase Order Item": [
		{
			"fieldname": "project_material_planning_item",
			"label": "Project Material Planning Item",
			"fieldtype": "Link",
			"options": "Project Material Planning Item",
			"insert_after": "item_code",
		},
		{
			"fieldname": "exceeds_project_requirement",
			"label": "Exceeds Project Requirement",
			"fieldtype": "Check",
			"insert_after": "qty",
			"read_only": 1,
		},
		{
			"fieldname": "excess_quantity",
			"label": "Excess Quantity",
			"fieldtype": "Float",
			"insert_after": "exceeds_project_requirement",
			"read_only": 1,
		},
		{
			"fieldname": "excess_purchase_reason",
			"label": "Excess Purchase Reason",
			"fieldtype": "Small Text",
			"insert_after": "excess_quantity",
			"in_list_view": 1,
		},
	],
	"Purchase Receipt": [
		{
			"fieldname": "project_material_planning",
			"label": "Project Material Planning",
			"fieldtype": "Link",
			"options": "Project Material Planning",
			"insert_after": "supplier",
		},
	],
	"Purchase Receipt Item": [
		{
			"fieldname": "project_material_planning_item",
			"label": "Project Material Planning Item",
			"fieldtype": "Link",
			"options": "Project Material Planning Item",
			"insert_after": "item_code",
		},
	],
}


def add_custom_fields():
	for doctype, fields in CUSTOM_FIELDS.items():
		for field in fields:
			if frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": field["fieldname"]}):
				continue
			doc = frappe.new_doc("Custom Field")
			doc.update({"dt": doctype, **field})
			doc.insert(ignore_permissions=True)
