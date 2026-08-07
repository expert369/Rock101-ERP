// Copyright (c) 2026, Peter John Alado and contributors
// For license information, please see license.txt

frappe.ui.form.on("Project Material Planning", {
	refresh: function (frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("Create Purchase Order"), function () {
				frm.trigger("create_purchase_order");
			});
		}
	},
	create_purchase_order: function (frm) {
		frappe.call({
			method: "rock101_erp.controllers.material_planning.get_create_po_items",
			args: { planning_name: frm.doc.name },
			freeze: true,
			callback: function (r) {
				const planned = r.message || [];
				const available = planned.filter(
					(d) => Math.max(d.remaining_qty - d.draft_po_qty, 0) > 0
				);
				const source = available.length ? available : planned;
                console.log(source);
                
				const data = source.map((d) => ({
					item_code: d.item_code,
					qty: Math.max(d.remaining_qty - d.draft_po_qty - d.submitted_qty, 0),
					rate: d.estimated_rate,
					project_material_planning_item: d.project_material_planning_item,
				}));

				if (!data.length) {
					frappe.msgprint(__("No items available for purchase."));
					return;
				}

				open_create_po_dialog(frm, data);
			},
		});
	},
});

function open_create_po_dialog(frm, data) {
	const dialog = new frappe.ui.Dialog({
		title: __("Create Purchase Order"),
		size: "extra-large",
		fields: [
			{
				fieldtype: "Link",
				fieldname: "supplier",
				label: __("Supplier"),
				options: "Supplier",
				reqd: 1,
			},
			{
				fieldtype: "Date",
				fieldname: "schedule_date",
				label: __("Schedule Date"),
			},
			{
				fieldtype: "Table",
				fieldname: "items",
				label: __("Items"),
				cannot_add_rows: 1,
				fields: [
					{
						fieldtype: "Link",
						fieldname: "item_code",
						label: __("Item"),
						options: "Item",
						in_list_view: 1,
						columns: 2,
						read_only: 1,
					},
					{
						fieldtype: "Float",
						fieldname: "qty",
						label: __("Qty"),
						reqd: 1,
						in_list_view: 1,
						columns: 1,
					},
					{
						fieldtype: "Currency",
						fieldname: "rate",
						label: __("Rate"),
						in_list_view: 1,
						columns: 1,
					},
				],
				data: data,
			},
		],
		primary_action: function (values) {
			const items = (values.items || []).filter((d) => d.item_code && flt(d.qty) > 0);
			if (!items.length) {
				frappe.msgprint(__("At least one item with a quantity is required."));
				return;
			}

			const proceed = (payload) => {
				frappe.call({
					method: "rock101_erp.controllers.material_planning.create_purchase_order",
					args: {
						planning_name: frm.doc.name,
						supplier: values.supplier,
						schedule_date: values.schedule_date,
						items: payload,
					},
					freeze: true,
					callback: function (r) {
						dialog.hide();
						if (r.message) {
							frappe.set_route("Form", "Purchase Order", r.message);
						}
					},
				});
			};

			frappe.call({
				method: "rock101_erp.controllers.material_planning.validate_po_items_excess",
				args: {
					planning_name: frm.doc.name,
					items: items,
				},
				callback: function (r) {
					const exceeded = r.message || [];
					if (!exceeded.length) {
						proceed(items);
						return;
					}

					const lines = exceeded
						.map((d) =>
							__(
								"{0}: Required {1}, Already Ordered (incl. Drafts) {2}, New Total {3}, Excess {4}",
								[d.item_code, d.required, d.already_ordered, d.total, d.excess]
							)
						)
						.join("\n");

					frappe.confirm(
						__(
							"The following quantities exceed the required quantity for the project:\n\n{0}\n\nDo you want to proceed? A reason is required.",
							[lines]
						),
						function () {
							frappe.prompt(
								{
									fieldname: "reason",
									label: __("Excess Purchase Reason"),
									fieldtype: "Small Text",
									reqd: 1,
								},
								function (vals) {
									const payload = items.map((d) =>
										Object.assign({}, d, {
											excess_purchase_reason: vals.reason,
										})
									);
									proceed(payload);
								},
								__("Excess Purchase Reason"),
								__("Confirm")
							);
						}
					);
				},
			});
		},
	});

	dialog.show();
}
