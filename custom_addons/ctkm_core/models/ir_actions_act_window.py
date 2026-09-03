# -*- coding: utf-8 -*-

from odoo import _, models
from odoo.exceptions import AccessError

# Action không gắn menu con (alias / form chi tiết) vẫn chặn theo URL.
_EXTRA_RESTRICTED_REPORT_ACTIONS = (
    'ctkm_core.action_ctkm_program_report',
    'ctkm_core.action_ctkm_print_progress_report',
    'ctkm_core.action_ctkm_printed_store_report',
    'ctkm_core.action_ctkm_price_store_report',
    'ctkm_core.action_ctkm_violation_report',
    'ctkm_core.action_ctkm_notify_report_detail',
)


class IrActionsActWindow(models.Model):
    _inherit = 'ir.actions.act_window'

    def _ctkm_restricted_report_action_ids(self):
        ids = set()
        for xmlid in _EXTRA_RESTRICTED_REPORT_ACTIONS:
            action = self.env.ref(xmlid, raise_if_not_found=False)
            if action:
                ids.add(action.id)
        parent = self.env.ref('ctkm_core.menu_ctkm_report', raise_if_not_found=False)
        if parent:
            menus = self.env['ir.ui.menu'].sudo().search([
                ('id', 'child_of', parent.id),
                ('id', '!=', parent.id),
            ])
            for menu in menus:
                action = menu.action
                if action:
                    ids.add(action.id)
        return ids

    def _ctkm_is_restricted_report_action(self):
        return bool(self._ctkm_restricted_report_action_ids().intersection(self.ids))

    def _get_action_dict(self):
        if (
            self._ctkm_is_restricted_report_action()
            and not self.env.user._ctkm_can_view_ctkm_reports()
        ):
            denied = self.env.ref(
                'ctkm_core.action_ctkm_report_access_denied',
                raise_if_not_found=False,
            )
            if denied:
                return denied._get_action_dict()
            raise AccessError(_('Bạn không đủ quyền hạn để xem mục này'))
        return super()._get_action_dict()
