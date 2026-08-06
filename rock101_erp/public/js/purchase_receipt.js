frappe.ui.form.on("Purchase Receipt Item", {
	purchase_order_item: function (frm, cdt, cdn) {
		const item = locals[cdt][cdn];
		if (item.purchase_order_item && !item.project_material_planning_item) {
			frappe.call({
				method: "frappe.client.get_value",
				args: {
					doctype: "Purchase Order Item",
					filters: { name: item.purchase_order_item },
					fieldname: "project_material_planning_item",
				},
				callback: function (r) {
					if (r.message) {
						frappe.model.set_value(
							cdt,
							cdn,
							"project_material_planning_item",
							r.message.project_material_planning_item
						);
					}
				},
			});
		}
	},
});
