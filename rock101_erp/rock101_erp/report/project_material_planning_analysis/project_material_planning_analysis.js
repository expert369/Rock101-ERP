// Copyright (c) 2026, Peter John Alado and contributors
// For license information, please see license.txt

frappe.query_reports["Project Material Planning Analysis"] = {
	filters: [
		{
			fieldname: "view_by",
			label: __("View By"),
			fieldtype: "Select",
			options: ["Project", "Item"],
			default: "Project",
			reqd: 1,
		},
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", "Draft", "In Progress", "Finished"],
		},
		{
			fieldname: "project_material_planning",
			label: __("Project Material Planning"),
			fieldtype: "Link",
			options: "Project Material Planning",
			width: 200,
		},
		{
			fieldname: "project",
			label: __("Project"),
			fieldtype: "Link",
			options: "Project",
			width: 200,
		},
		{
			fieldname: "item",
			label: __("Item"),
			fieldtype: "Link",
			options: "Item",
			width: 200,
		},
		{
			fieldname: "date_started",
			label: __("Date Started"),
			fieldtype: "Date",
			width: 120,
		},
		{
			fieldname: "expected_date_finish",
			label: __("Expected Date Finish"),
			fieldtype: "Date",
			width: 120,
		},
	],

	formatter: function (value, row, column, data, default_formatter) {
		if (column.fieldname === "budget_status" && data) {
			var status_classes = {
				"Under Budget": "green",
				"On Budget": "gray",
				"Over Budget": "red",
			};
			var status_class = status_classes[value] || "gray";
			return '<span class="indicator-pill ' + status_class + '">' + value + "</span>";
		}

		if (column.fieldname === "variance" && data) {
			value = default_formatter(value, row, column, data);
			var variance = flt(data.variance);
			if (variance > 0) {
				value = '<span style="color: #28a745;">' + value + "</span>";
			} else if (variance < 0) {
				value = '<span style="color: #dc3545;">' + value + "</span>";
			}
			return value;
		}

		return default_formatter(value, row, column, data);
	},
};
