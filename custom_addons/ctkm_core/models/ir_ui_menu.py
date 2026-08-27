# -*- coding: utf-8 -*-

from odoo import models

_CTKM_REPORT_MENUS = (
    'ctkm_core.menu_ctkm_progress_report',
    'ctkm_core.menu_ctkm_report_printed_stores',
    'ctkm_core.menu_ctkm_report_violations',
)


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    def _load_menus_blacklist(self):
        res = super()._load_menus_blacklist()
        if self.env.user._ctkm_can_view_ctkm_reports():
            return res
        hidden = list(res)
        for xmlid in _CTKM_REPORT_MENUS:
            menu = self.env.ref(xmlid, raise_if_not_found=False)
            if menu:
                hidden.append(menu.id)
        return hidden
