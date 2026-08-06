frappe.ui.form.on("Purchase Order Item", {
	qty: function (frm, cdt, cdn) {
		check_excess(frm, cdt, cdn);
	},
	project_material_planning_item: function (frm, cdt, cdn) {
		check_excess(frm, cdt, cdn);
	},
	excess_purchase_reason: function () {},
});

let excess_check_timer = null;

function check_excess(frm, cdt, cdn) {
	const item = locals[cdt][cdn];
	if (!item.project_material_planning_item || !item.qty) {
		return;
	}
	clearTimeout(excess_check_timer);
	excess_check_timer = setTimeout(function () {
		frappe.call({
			method: "rock101_erp.controllers.material_planning.validate_po_item_excess",
			args: {
				planning_item: item.project_material_planning_item,
				requested_qty: item.qty,
				po_name: frm.doc.name,
			},
			callback: function (r) {
				if (!r.message || !r.message.exceeds) {
					return;
				}
				if (item.excess_purchase_reason) {
					return;
				}
				frappe.confirm(
					__(
						"The quantity for this item exceeds the required quantity for the project.\n\nAlready Ordered (incl. Drafts): {0}\nNew Quantity: {1}\nTotal: {2}\nExcess: {3}\n\nDo you want to proceed? A reason is required.",
						[
							r.message.already_ordered,
							r.message.requested,
							r.message.total,
							r.message.excess,
						]
					),
					function () {
						frappe.prompt(
							{
								fieldname: "reason",
								label: __("Excess Purchase Reason"),
								fieldtype: "Small Text",
								reqd: 1,
							},
							function (values) {
								frappe.model.set_value(
									cdt,
									cdn,
									"excess_purchase_reason",
									values.reason
								);
								frappe.show_alert({
									message: __("Excess purchase reason recorded."),
									indicator: "green",
								});
							},
							__("Excess Purchase Reason"),
							__("Confirm")
						);
					}
				);
			},
		});
	}, 600);
}
