# -*- coding: utf-8 -*-

import logging

from markupsafe import Markup, escape

from odoo import _, models
from odoo.exceptions import UserError
from odoo.tools import html2plaintext

_logger = logging.getLogger(__name__)

_CTKM_BOT_XMLID = "business_discuss_bots.user_bot_ctkm"


class CtkmProgramDiscussNotify(models.Model):
    _inherit = "ctkm.program"

    def _ctkm_notify_recipient_users(self):
        self.ensure_one()
        employees = self.notify_line_ids.notify_employee_ids
        users = employees.mapped("user_id").filtered(
            lambda user: user and user.active and not user.share and user.partner_id
        )
        return users, employees.filtered(
            lambda employee: not employee.user_id
            or not employee.user_id.active
            or employee.user_id.share
            or not employee.user_id.partner_id
        )

    def _ctkm_notify_plain_text(self, html_value):
        return html2plaintext(html_value or "").replace("\xa0", " ").strip()

    def _ctkm_notify_message_body(self):
        self.ensure_one()
        lines = [Markup("<b>%s</b>") % escape(self.name or "")]
        if self.user_id:
            lines.append(Markup("Người phụ trách: %s") % escape(self.user_id.name))
        description = self._ctkm_notify_plain_text(self.description)
        if description:
            lines.append(Markup("Mô tả: %s") % escape(description))
        note = self._ctkm_notify_plain_text(self.note)
        if note:
            lines.append(Markup("Ghi chú: %s") % escape(note))
        return Markup("<br/>").join(lines)

    def _ctkm_notify_attachments(self):
        self.ensure_one()
        if not self.badge_image:
            return []
        filename = "%s_badge.png" % (self.name or "ctkm").replace("/", "-")
        return [(filename, self.badge_image)]

    def _post_ctkm_bot_discuss_message(self, recipient_user, body, attachments=None):
        self.ensure_one()
        Message = self.env["mail.message"]
        if not recipient_user or recipient_user.share or not recipient_user.partner_id:
            return Message
        bot_user = self.env.ref(_CTKM_BOT_XMLID, raise_if_not_found=False)
        if not bot_user or not bot_user.partner_id:
            raise UserError(_("Chưa cấu hình OdooBot CTKM trên hệ thống."))
        try:
            chat = (
                self.env["discuss.channel"]
                .sudo()
                .with_user(recipient_user)
                ._get_or_create_chat([bot_user.partner_id.id], pin=True)
            )
            post_vals = {
                "body": body,
                "message_type": "comment",
                "subtype_xmlid": "mail.mt_comment",
                "author_id": bot_user.partner_id.id,
            }
            if attachments:
                post_vals["attachments"] = attachments
            return chat.with_user(bot_user).sudo().message_post(**post_vals)
        except Exception:
            _logger.exception(
                "ctkm_core: OdooBot CTKM DM failed program_id=%s recipient_user_id=%s",
                self.id,
                recipient_user.id,
            )
            return Message

    def action_send_discuss_notification(self):
        for program in self:
            users, skipped_employees = program._ctkm_notify_recipient_users()
            if not users:
                if skipped_employees:
                    raise UserError(
                        _(
                            "Không có người nhận hợp lệ trong phạm vi thông báo. "
                            "Các nhân viên sau chưa có tài khoản nội bộ: %s"
                        )
                        % ", ".join(skipped_employees.mapped("name"))
                    )
                raise UserError(_("Vui lòng chọn ít nhất một người nhận trong phạm vi thông báo."))

            body = program._ctkm_notify_message_body()
            attachments = program._ctkm_notify_attachments()
            sent_users = self.env["res.users"]
            for user in users:
                if program._post_ctkm_bot_discuss_message(user, body, attachments=attachments or None):
                    sent_users |= user

            log_parts = [_("Đã gửi thông báo Discuss tới %s người nhận.") % len(sent_users)]
            if skipped_employees:
                log_parts.append(
                    _("Bỏ qua %s nhân viên chưa có tài khoản nội bộ: %s")
                    % (len(skipped_employees), ", ".join(skipped_employees.mapped("name")))
                )
            if sent_users:
                log_parts.append(_("Người nhận: %s") % ", ".join(sent_users.mapped("name")))
            program.message_post(
                body=Markup("<br/>").join(Markup("%s") % part for part in log_parts),
                subtype_xmlid="mail.mt_note",
            )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Gửi tin thành công"),
                "message": _("OdooBot CTKM đã gửi thông báo tới người nhận trong phạm vi thông báo."),
                "type": "success",
                "sticky": False,
            },
        }
