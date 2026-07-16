# -*- coding: utf-8 -*-

import base64
import logging

from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html2plaintext, mimetypes

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

    def _ctkm_notify_detail_button_markup(self):
        href = "/odoo/ctkm-my-tasks?ctkm_program_id=%s" % self.id
        return Markup(
            '<div class="o_ctkm_notify_detail mt-2">'
            '<a class="btn btn-primary btn-sm o_ctkm_notify_detail_btn" '
            'href="%s" data-oe-model="ctkm.program" data-oe-id="%s" '
            'data-program-id="%s" contenteditable="false">'
            "Bấm để xem chi tiết"
            "</a>"
            "</div>"
        ) % (escape(href), self.id, self.id)

    def action_open_my_task(self):
        """Delegate: lần đầu bấm nút tạo công việc, ngày xử lý = ngày bấm."""
        self.ensure_one()
        return self.env["ctkm.task"].action_open_for_program(self.id)

    @api.model
    def _ctkm_fix_notify_detail_buttons(self):
        """Cập nhật nút trong tin Discuss cũ để có data-program-id."""
        import re

        Message = self.env["mail.message"].sudo()
        messages = Message.search([("body", "ilike", "o_ctkm_notify_detail_btn")])
        if not messages:
            return True
        pattern = re.compile(
            r'<div class="o_ctkm_notify_detail[^"]*">.*?</div>',
            re.IGNORECASE | re.DOTALL,
        )
        for program in self.sudo().search([]):
            name = (program.name or "").strip()
            if not name:
                continue
            btn_html = str(program._ctkm_notify_detail_button_markup())
            for message in messages:
                body = message.body or ""
                if "o_ctkm_notify_detail_btn" not in body or name not in body:
                    continue
                new_body = pattern.sub(btn_html, body, count=1)
                if new_body != body:
                    message.write({"body": new_body})
        return True

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
        lines.append(self._ctkm_notify_detail_button_markup())
        return Markup("<br/>").join(lines)

    def _ctkm_badge_attachment_values(self, res_model, res_id):
        self.ensure_one()
        if not self.badge_image:
            return None
        raw = base64.b64decode(self.badge_image)
        mime = mimetypes.guess_mimetype(raw, default="image/jpeg") or "image/jpeg"
        ext_map = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/gif": ".gif",
            "image/webp": ".webp",
        }
        ext = ext_map.get(mime, ".jpg")
        filename = "ctkm_%s_badge%s" % (self.id, ext)
        return {
            "name": filename,
            "type": "binary",
            "datas": base64.b64encode(raw),
            "mimetype": mime,
            "res_model": res_model,
            "res_id": res_id,
        }

    def _ctkm_discuss_attachment_ids(self, chat):
        self.ensure_one()
        Attachment = self.env["ir.attachment"].sudo()
        attachment_ids = []
        badge_vals = self._ctkm_badge_attachment_values("discuss.channel", chat.id)
        if badge_vals:
            badge = Attachment.create(badge_vals)
            badge.generate_access_token()
            attachment_ids.append(badge.id)
        for document in self.notify_document_ids:
            discuss_doc = Attachment.create({
                "name": document.name,
                "type": "binary",
                "datas": document.datas,
                "mimetype": document.mimetype or mimetypes.guess_mimetype(
                    document.name or "",
                    default="application/octet-stream",
                ),
                "res_model": "discuss.channel",
                "res_id": chat.id,
            })
            discuss_doc.generate_access_token()
            attachment_ids.append(discuss_doc.id)
        return attachment_ids

    def _post_ctkm_bot_discuss_message(self, recipient_user, body):
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
            attachment_ids = self._ctkm_discuss_attachment_ids(chat)
            if attachment_ids:
                post_vals["attachment_ids"] = attachment_ids
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
            sent_users = self.env["res.users"]
            for user in users:
                if program._post_ctkm_bot_discuss_message(user, body):
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
