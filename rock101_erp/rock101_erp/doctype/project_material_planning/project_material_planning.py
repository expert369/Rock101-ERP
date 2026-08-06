import frappe
from frappe.model.document import Document
from frappe.utils import flt

from rock101_erp.controllers.material_planning import recalculate_planning


class ProjectMaterialPlanning(Document):
	def before_insert(self):
		self.normalize_project_id()

	def before_validate(self):
		self.normalize_project_id()
		if not self.currency:
			self.currency = frappe.db.get_single_value("Global Defaults", "default_currency")

	def normalize_project_id(self):
		if self.project_id:
			self.project_id = self.project_id.strip().upper()

	def validate(self):
		self.normalize_project_id()
		if self.items:
			for row in self.items:
				if row.estimated_rate:
					row.estimated_amount = flt(row.required_qty) * flt(row.estimated_rate)
		recalculate_planning(self)
