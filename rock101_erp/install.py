import frappe


def after_install():
	from rock101_erp.controllers.material_planning import ensure_planning_workflow
	from rock101_erp.customizations import add_custom_fields

	add_custom_fields()
	ensure_planning_workflow()
