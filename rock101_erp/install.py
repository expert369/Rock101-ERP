import frappe


def after_install():
	from rock101_erp.rock101_erp.customizations import add_custom_fields

	add_custom_fields()
