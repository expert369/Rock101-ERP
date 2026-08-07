// Copyright (c) 2026, Rock101 ERP and Contributors
// License: GNU General Public License v3. See license.txt

frappe.views.calendar["Project Material Planning"] = {
	field_map: {
		start: "date_started",
		end: "date_finished",
		id: "name",
		title: "project_name",
		progress: "project_progress",
	},
	gantt: true,
	filters: [
		{
			fieldtype: "Link",
			fieldname: "project",
			options: "Project",
			label: __("Project"),
		},
	],
	get_events_method: "frappe.desk.calendar.get_events",
};