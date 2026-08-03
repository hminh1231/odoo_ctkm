# -*- coding: utf-8 -*-

from odoo import models

_CTKM_BOT_XMLID = "business_discuss_bots.user_bot_ctkm"
_CTKM_RES_MODELS = frozenset({"ctkm.program", "ctkm.task"})


class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    def _ctkm_internal_user_can_read_sudo(self):
        """Gọi trên recordset đã sudo(); không trigger lại _check_access."""
        self.ensure_one()
        user = self.env.user
        if not user or user.share or not user.has_group("base.group_user"):
            return False
        if self.res_model in _CTKM_RES_MODELS:
            return True
        if self.res_model == "discuss.channel":
            bot = self.env.ref(_CTKM_BOT_XMLID, raise_if_not_found=False)
            if bot and self.create_uid.id == bot.id:
                return True
        return False

    def _check_access(self, operation):
        res = super()._check_access(operation)
        if not res or operation != "read":
            return res
        forbidden, error_func = res
        # Dùng sudo() khi đọc metadata để tránh đệ quy ACL.
        allowed_ids = {
            att.id
            for att in forbidden.sudo()
            if att._ctkm_internal_user_can_read_sudo()
        }
        remaining = forbidden.browse([i for i in forbidden.ids if i not in allowed_ids])
        if not remaining:
            return None
        return remaining, error_func
