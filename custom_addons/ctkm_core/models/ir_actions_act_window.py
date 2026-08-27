# -*- coding: utf-8 -*-

from odoo import _, models
from odoo.exceptions import AccessError

_RESTRICTED_REPORT_ACTIONS = (
    'ctkm_core.action_ctkm_program_report',
    'ctkm_core.action_ctkm_print_progress_report',
    'ctkm_core.action_ctkm_printed_store_report',
    'ctkm_core.action_ctkm_price_store_report',
    'ctkm_core.action_ctkm_violation_report',
)


class IrActionsActWindow(models.Model):
    _inherit = 'ir.actions.act_window'

    def _ctkm_is_restricted_report_action(self):
        restricted_ids = set()
        for xmlid in _RESTRICTED_REPORT_ACTIONS:
            action = self.env.ref(xmlid, raise_if_not_found=False)
            if action:
                restricted_ids.add(action.id)
        return bool(restricted_ids.intersection(self.ids))

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
