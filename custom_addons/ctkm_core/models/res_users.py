# -*- coding: utf-8 -*-

from odoo import models
from odoo.addons.hr_employee_hrm_detail.models.hr_employee import _is_vp_mien


class ResUsers(models.Model):
    _inherit = 'res.users'

    def _ctkm_can_view_ctkm_reports(self):
        """True if the user belongs to Miền VP (or is superuser)."""
        self.ensure_one()
        if self._is_superuser():
            return True
        return _is_vp_mien(self.sudo().employee_mien)
