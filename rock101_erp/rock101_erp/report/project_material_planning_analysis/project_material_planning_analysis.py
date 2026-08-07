# Copyright (c) 2026, Peter John Alado and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt

EXPENSE_SUBQUERY = """
	SELECT pri.`project_material_planning_item` AS planning_item,
		SUM(COALESCE(pri.base_amount, 0)) AS expense
	FROM `tabPurchase Receipt Item` pri
	INNER JOIN `tabPurchase Receipt` prc ON prc.name = pri.parent
	WHERE prc.docstatus = 1
		AND pri.`project_material_planning_item` IS NOT NULL
	GROUP BY pri.`project_material_planning_item`
"""

COMMON_FILTERS = {
	"project_material_planning": ("pmp.`name`", "="),
	"project": ("pmp.`project`", "="),
	"item": ("pmpi.`item`", "="),
	"date_started": ("pmp.`date_started`", None),
	"expected_date_finish": ("pmp.`date_finished`", None),
}


def execute(filters=None):
	filters = frappe._dict(filters or {})

	columns = get_columns(filters)

	if not frappe.has_permission("Project Material Planning", "read"):
		return columns, [], None, None, [], False

	if filters.get("view_by") == "Item":
		rows = get_item_rows(filters)
	else:
		rows = get_project_rows(filters)

	total_estimated = flt(sum(r["estimated_amount"] for r in rows), 2)
	total_expense = flt(sum(r["expense"] for r in rows), 2)
	report_summary = get_report_summary(total_estimated, total_expense, rows)

	return columns, rows, None, None, report_summary, False


def get_columns(filters):
	currency_column = {
		"fieldname": "currency",
		"label": _("Currency"),
		"fieldtype": "Link",
		"options": "Currency",
		"width": 90,
		"hidden": 1,
	}

	if filters.get("view_by") == "Item":
		return [
			{
				"fieldname": "planning",
				"label": _("Project Material Planning"),
				"fieldtype": "Link",
				"options": "Project Material Planning",
				"width": 170,
			},
			{
				"fieldname": "project",
				"label": _("Project"),
				"fieldtype": "Link",
				"options": "Project",
				"width": 180,
			},
			{"fieldname": "date_started", "label": _("Date Started"), "fieldtype": "Date", "width": 110},
			{
				"fieldname": "expected_date_finish",
				"label": _("Expected Date Finish"),
				"fieldtype": "Date",
				"width": 130,
			},
			{
				"fieldname": "item",
				"label": _("Item"),
				"fieldtype": "Link",
				"options": "Item",
				"width": 140,
			},
			{"fieldname": "description", "label": _("Description"), "fieldtype": "Data", "width": 200},
			{"fieldname": "uom", "label": _("UOM"), "fieldtype": "Link", "options": "UOM", "width": 70},
			{"fieldname": "required_qty", "label": _("Required Qty"), "fieldtype": "Float", "width": 120},
			{"fieldname": "purchased_qty", "label": _("Purchased Qty"), "fieldtype": "Float", "width": 120},
			{"fieldname": "received_qty", "label": _("Received Qty"), "fieldtype": "Float", "width": 120},
			{"fieldname": "remaining_qty", "label": _("Remaining Qty"), "fieldtype": "Float", "width": 140},
			{
				"fieldname": "estimated_rate",
				"label": _("Estimated Rate"),
				"fieldtype": "Currency",
				"options": "currency",
				"width": 140,
			},
			{
				"fieldname": "estimated_amount",
				"label": _("Estimated Amount"),
				"fieldtype": "Currency",
				"options": "currency",
				"width": 140,
			},
			{
				"fieldname": "expense",
				"label": _("Expense"),
				"fieldtype": "Currency",
				"options": "currency",
				"width": 120,
			},
			{
				"fieldname": "variance",
				"label": _("Variance"),
				"fieldtype": "Currency",
				"options": "currency",
				"width": 120,
			},
			{"fieldname": "budget_status", "label": _("Budget Status"), "fieldtype": "Data", "width": 130},
			currency_column,
		]

	return [
		{
			"fieldname": "planning",
			"label": _("Project Material Planning"),
			"fieldtype": "Link",
			"options": "Project Material Planning",
			"width": 170,
		},
		{
			"fieldname": "project",
			"label": _("Project"),
			"fieldtype": "Link",
			"options": "Project",
			"width": 180,
		},
		{"fieldname": "date_started", "label": _("Date Started"), "fieldtype": "Date", "width": 110},
		{
			"fieldname": "expected_date_finish",
			"label": _("Expected Date Finish"),
			"fieldtype": "Date",
			"width": 130,
		},
		{"fieldname": "required_items", "label": _("Required Items"), "fieldtype": "Float", "width": 110},
		{"fieldname": "purchased_items", "label": _("Purchased Items"), "fieldtype": "Float", "width": 110},
		{"fieldname": "remaining_items", "label": _("Remaining Items"), "fieldtype": "Float", "width": 110},
		{
			"fieldname": "estimated_amount",
			"label": _("Estimated Amount"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 130,
		},
		{
			"fieldname": "expense",
			"label": _("Expense"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 120,
		},
		{
			"fieldname": "variance",
			"label": _("Variance"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 120,
		},
		{"fieldname": "cost_progress", "label": _("Cost Progress"), "fieldtype": "Percent", "width": 100},
		{
			"fieldname": "project_progress",
			"label": _("Project Progress"),
			"fieldtype": "Percent",
			"width": 110,
		},
		currency_column,
	]


def get_conditions(filters):
	conditions = []
	params = {}

	for fieldname, (column, operator) in COMMON_FILTERS.items():
		value = filters.get(fieldname)
		if value is None or value == "":
			continue
		if operator == "=":
			params[fieldname] = value
			conditions.append(f"{column} = %({fieldname})s")
		elif isinstance(value, list | tuple) and len(value) == 2:
			if not value[0] and not value[1]:
				continue
			params[f"{fieldname}_start"] = value[0] or None
			params[f"{fieldname}_end"] = value[1] or None
			if value[0] and value[1]:
				conditions.append(f"{column} BETWEEN %({fieldname}_start)s AND %({fieldname}_end)s")
			elif value[0]:
				conditions.append(f"{column} >= %({fieldname}_start)s")
			else:
				conditions.append(f"{column} <= %({fieldname}_end)s")
		else:
			params[fieldname] = value
			conditions.append(f"{column} = %({fieldname})s")

	if filters.status:
		params["status"] = filters.status
		conditions.append("pmp.workflow_state = %(status)s")

	return " AND ".join(conditions) or "1=1", params


def get_item_rows(filters):
	where, params = get_conditions(filters)

	sql = f"""
		SELECT
			pmp.`name` AS planning,
			COALESCE(pmp.project, "") AS project,
			pmp.`date_started` AS date_started,
			pmp.`date_finished` AS expected_date_finish,
			pmp.`currency` AS currency,
			pmpi.`item` AS item,
			pmpi.`description` AS description,
			pmpi.`uom` AS uom,
			COALESCE(pmpi.`required_qty`, 0) AS required_qty,
			COALESCE(pmpi.`po_qty`, 0) AS purchased_qty,
			COALESCE(pmpi.`received_qty`, 0) AS received_qty,
			COALESCE(pmpi.`remaining_qty`, 0) AS remaining_qty,
			COALESCE(pmpi.`estimated_rate`, 0) AS estimated_rate,
			COALESCE(pmpi.`required_qty`, 0) * COALESCE(pmpi.`estimated_rate`, 0) AS estimated_amount,
			COALESCE(exp.expense, 0) AS expense
		FROM `tabProject Material Planning` pmp
		INNER JOIN `tabProject Material Planning Item` pmpi ON pmpi.`parent` = pmp.`name`
		LEFT JOIN ({EXPENSE_SUBQUERY}) exp ON exp.planning_item = pmpi.`name`
		WHERE {where}
		ORDER BY pmp.`name`, pmpi.`item`
	"""

	rows = frappe.db.sql(sql, params, as_dict=1)

	data = []
	for row in rows:
		row["estimated_amount"] = flt(row["estimated_amount"], 2)
		row["expense"] = flt(row["expense"], 2)
		row["variance"] = flt(row["estimated_amount"] - row["expense"], 2)
		row["budget_status"] = get_budget_status(row["estimated_amount"], row["expense"])
		data.append(row)

	return data


def get_project_rows(filters):
	where, params = get_conditions(filters)

	sql = f"""
		SELECT
			pmp.`name` AS planning,
			COALESCE(pmp.project, "") AS project,
			pmp.`date_started` AS date_started,
			pmp.`date_finished` AS expected_date_finish,
			pmp.`currency` AS currency,
			SUM(COALESCE(pmpi.`required_qty`, 0)) AS required_items,
			SUM(COALESCE(pmpi.`received_qty`, 0)) AS purchased_items,
			SUM(COALESCE(pmpi.`remaining_qty`, 0)) AS remaining_items,
			SUM(COALESCE(pmpi.`required_qty`, 0) * COALESCE(pmpi.`estimated_rate`, 0)) AS estimated_amount,
			COALESCE(SUM(exp.expense), 0) AS expense,
			COALESCE(pmp.`cost_progress`, 0) AS cost_progress,
			COALESCE(pmp.`project_progress`, 0) AS project_progress
		FROM `tabProject Material Planning` pmp
		INNER JOIN `tabProject Material Planning Item` pmpi ON pmpi.`parent` = pmp.`name`
		LEFT JOIN ({EXPENSE_SUBQUERY}) exp ON exp.planning_item = pmpi.`name`
		WHERE {where}
		GROUP BY
			pmp.`name`, pmp.`project`, pmp.`date_started`, pmp.`date_finished`,
			pmp.`currency`, pmp.`cost_progress`, pmp.`project_progress`
		ORDER BY pmp.`name`
	"""

	rows = frappe.db.sql(sql, params, as_dict=1)

	data = []
	for row in rows:
		row["estimated_amount"] = flt(row["estimated_amount"], 2)
		row["expense"] = flt(row["expense"], 2)
		row["variance"] = flt(row["estimated_amount"] - row["expense"], 2)
		row["budget_status"] = get_budget_status(row["estimated_amount"], row["expense"])
		data.append(row)

	return data


def get_budget_status(estimated_amount, expense):
	estimated_amount = flt(estimated_amount, 2)
	expense = flt(expense, 2)

	if expense > estimated_amount:
		return "Over Budget"
	if expense < estimated_amount:
		return "Under Budget"
	return "On Budget"


def get_report_summary(total_estimated, total_expense, rows):
	total_difference = flt(total_estimated - total_expense, 2)
	currency = next((r.get("currency") for r in rows if r.get("currency")), None) or (
		frappe.defaults.get_global_default("currency")
	)

	return [
		{
			"label": _("Total Estimated Amount"),
			"value": total_estimated,
			"datatype": "Currency",
			"currency": currency,
			"indicator": "blue",
		},
		{
			"label": _("Total Expense"),
			"value": total_expense,
			"datatype": "Currency",
			"currency": currency,
			"indicator": "orange",
		},
		{
			"label": _("Total Difference"),
			"value": total_difference,
			"datatype": "Currency",
			"currency": currency,
			"indicator": "green" if total_difference >= 0 else "red",
		},
	]
