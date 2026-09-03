# -*- coding: utf-8 -*-

from odoo import models


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    def _ctkm_report_child_menus(self):
        """Mọi menu con dưới Báo cáo — chỉ Miền VP được thấy."""
        parent = self.env.ref('ctkm_core.menu_ctkm_report', raise_if_not_found=False)
        if not parent:
            return self.browse()
        return self.sudo().search([
            ('id', 'child_of', parent.id),
            ('id', '!=', parent.id),
        ])

    def _load_menus_blacklist(self):
        res = super()._load_menus_blacklist()
        if self.env.user._ctkm_can_view_ctkm_reports():
            return res
        hidden = list(res)
        hidden.extend(self._ctkm_report_child_menus().ids)
        return hidden
