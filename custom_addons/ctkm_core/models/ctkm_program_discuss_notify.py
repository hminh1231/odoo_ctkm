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

    def _ctkm_ordered_notify_lines(self):
        self.ensure_one()
        return self.notify_line_ids.sorted(lambda line: (line.sequence, line.id))

    def _ctkm_first_notify_line(self):
        """Dòng phạm vi đầu tiên (STT 1)."""
        return self._ctkm_ordered_notify_lines()[:1]

    def _ctkm_first_unsent_notify_line(self):
        """Dòng phạm vi chưa gửi, theo thứ tự sequence/STT."""
        self.ensure_one()
        return self._ctkm_ordered_notify_lines().filtered(lambda line: not line.notified)[:1]

    def _ctkm_ordered_checklist_lines(self):
        self.ensure_one()
        return self.checklist_line_ids.sorted(lambda line: (line.sequence, line.id))

    def _ctkm_first_pending_checklist_line(self):
        """Bước tiến độ tiếp theo cần giao việc (có người phụ trách, chưa gửi tin, chưa xong)."""
        self.ensure_one()
        return self._ctkm_ordered_checklist_lines().filtered(
            lambda line: line.user_ids and not line.notified and line.state != 'done'
        )[:1]

    def _ctkm_next_checklist_line(self, current_line):
        """Bước tiến độ kế tiếp (có phụ trách, chưa gửi tin) sau bước hiện tại."""
        self.ensure_one()
        if not current_line:
            return self.env['ctkm.program.checklist.line']
        found = False
        for line in self._ctkm_ordered_checklist_lines():
            if found:
                if line.user_ids and not line.notified:
                    return line
                continue
            if line.id == current_line.id:
                found = True
        return self.env['ctkm.program.checklist.line']

    def _ctkm_notify_message_body_for_line(self, notify_line):
        self.ensure_one()
        lines = [Markup("<b>%s</b>") % escape(self.name or "")]
        step = notify_line.step_label or ""
        if step:
            lines.append(Markup("Bước xử lý: <b>%s</b>") % escape(step))
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

    def _ctkm_checklist_work_message_body(self, checklist_line):
        """Tin OdooBot giao việc cho người phụ trách một bước tiến độ."""
        self.ensure_one()
        lines = [
            Markup("<b>%s</b>") % escape(self.name or ""),
            Markup("Công việc của bạn: <b>%s</b>") % escape(
                checklist_line.name or _("Bước tiến độ")
            ),
        ]
        if checklist_line.sequence:
            lines.insert(1, Markup("Bước STT: <b>%s</b>") % checklist_line.sequence)
        if self.user_id:
            lines.append(Markup("Người phụ trách CTKM: %s") % escape(self.user_id.name))
        description = self._ctkm_notify_plain_text(self.description)
        if description:
            lines.append(Markup("Mô tả CTKM: %s") % escape(description))
        if checklist_line.note:
            lines.append(Markup("Ghi chú bước: %s") % escape(checklist_line.note))
        lines.append(Markup(
            "Vui lòng xử lý, bấm <b>Hoàn thành</b>, chờ xác nhận quản lý, "
            "rồi <b>Chuyển tiếp</b> để giao bước sau."
        ))
        lines.append(self._ctkm_notify_detail_button_markup())
        return Markup("<br/>").join(lines)

    def _ctkm_send_notify_line(self, notify_line, handover_note=False, handover_attachments=None):
        """Gửi OdooBot + tạo task cho một dòng phạm vi (giữ cho tương thích Chuyển tiếp cũ)."""
        self.ensure_one()
        users, skipped = notify_line._get_recipient_users()
        if not users:
            if skipped:
                raise UserError(
                    _(
                        "Bước \"%s\" không có người nhận hợp lệ. "
                        "Các nhân viên sau chưa có tài khoản nội bộ: %s"
                    )
                    % (notify_line.step_label or "", ", ".join(skipped.mapped("name")))
                )
            raise UserError(
                _('Bước "%s" chưa có người nhận thông báo.')
                % (notify_line.step_label or "")
            )

        body = self._ctkm_notify_message_body_for_line(notify_line)
        Task = self.env["ctkm.task"]
        sent_users = self.env["res.users"]
        # Bước đầu: kèm ghi chú/file chương trình vào handover để bước sau kế thừa chuỗi
        if not handover_note and self.note:
            handover_note = Markup("<p><b>%s</b></p>%s") % (
                escape(_("Ghi chú chương trình")),
                Markup(self.note),
            )
        if handover_attachments is None:
            handover_attachments = self.notify_document_ids

        for user in users:
            if self._post_ctkm_bot_discuss_message(user, body):
                sent_users |= user
                Task._get_or_create_for_program_user(
                    self,
                    user,
                    notify_line=notify_line,
                    handover_note=handover_note,
                    handover_attachments=handover_attachments,
                )

        notify_line.write({
            "notified": True,
            "notified_date": fields.Datetime.now(),
        })

        log_parts = [
            _("Đã gửi thông báo Discuss tới bước <b>%s</b> (%s người nhận).")
            % (escape(notify_line.step_label or ""), len(sent_users))
        ]
        if skipped:
            log_parts.append(
                _("Bỏ qua %s nhân viên chưa có tài khoản nội bộ: %s")
                % (len(skipped), ", ".join(skipped.mapped("name")))
            )
        if sent_users:
            log_parts.append(_("Người nhận: %s") % ", ".join(sent_users.mapped("name")))
        self.message_post(
            body=Markup("<br/>").join(Markup("%s") % part for part in log_parts),
            subtype_xmlid="mail.mt_note",
        )
        return sent_users

    def _ctkm_send_checklist_step_notify(self, checklist_line, handover_note=False, handover_attachments=None):
        """Gửi OdooBot giao việc + tạo/cập nhật task cho một bước tiến độ.
        Gửi tin cho TẤT CẢ người phụ trách của bước (nhiều người chia sẻ 1 công việc).
        """
        self.ensure_one()
        checklist_line = checklist_line.sudo()
        if not checklist_line or not checklist_line.exists():
            return self.env["res.users"]
        users = checklist_line.user_ids.filtered(
            lambda u: u and not u.share and u.partner_id
        )
        if not users:
            raise UserError(_(
                'Bước "%s" chưa có người phụ trách hợp lệ (cần tài khoản nội bộ).'
            ) % (checklist_line.name or ""))

        if not handover_note and self.note:
            handover_note = Markup("<p><b>%s</b></p>%s") % (
                escape(_("Ghi chú chương trình")),
                Markup(self.note),
            )
        if handover_attachments is None:
            handover_attachments = self.notify_document_ids

        body = self._ctkm_checklist_work_message_body(checklist_line)
        sent_users = self.env["res.users"]
        for user in users:
            if self._post_ctkm_bot_discuss_message(user, body):
                sent_users |= user
        if not sent_users:
            raise UserError(_(
                'Không gửi được OdooBot CTKM tới bước "%s". Thử lại sau.'
            ) % (checklist_line.name or ""))

        task = checklist_line._ctkm_ensure_task()
        if task:
            update_vals = {}
            if handover_note and not task.handover_note:
                update_vals["handover_note"] = handover_note
            if update_vals:
                task.sudo().write(update_vals)
            if handover_attachments and not task.handover_document_ids:
                copies = self.env["ctkm.task"]._duplicate_attachments_for_task(
                    handover_attachments, task
                )
                task.sudo().write({
                    "handover_document_ids": [(6, 0, copies.ids)],
                })
            task._ensure_program_notify_documents()

        checklist_vals = {
            "notified": True,
            "notified_date": fields.Datetime.now(),
        }
        if checklist_line.state == "todo":
            checklist_vals["state"] = "progress"
        checklist_line.with_context(ctkm_task_sync=True).write(checklist_vals)

        self.message_post(
            body=_(
                "Đã giao việc bước <b>%(step)s</b> cho <b>%(user)s</b> qua OdooBot CTKM."
            ) % {
                "step": escape(checklist_line.name or ""),
                "user": escape(", ".join(sent_users.mapped("name")) or ""),
            },
            subtype_xmlid="mail.mt_note",
            body_is_html=True,
        )
        return sent_users

    def action_send_discuss_notification(self):
        """Gửi tin CTKM tới toàn bộ Phạm vi thông báo; khởi động bước tiến độ đầu tiên."""
        for program in self:
            users, skipped = program._ctkm_notify_recipient_users()
            if not users:
                if skipped:
                    raise UserError(_(
                        "Phạm vi thông báo không có người nhận hợp lệ. "
                        "Các nhân viên sau chưa có tài khoản nội bộ: %s"
                    ) % ", ".join(skipped.mapped("name")))
                raise UserError(_(
                    "Vui lòng chọn ít nhất một người nhận trong phạm vi thông báo."
                ))

            all_lines = program._ctkm_ordered_notify_lines()
            if all_lines and all(line.notified for line in all_lines):
                raise UserError(_(
                    "Đã gửi thông báo phạm vi cho chương trình này rồi."
                ))

            body = program._ctkm_notify_message_body()
            sent_users = self.env["res.users"]
            for user in users:
                if program._post_ctkm_bot_discuss_message(user, body):
                    sent_users |= user

            if all_lines:
                all_lines.write({
                    "notified": True,
                    "notified_date": fields.Datetime.now(),
                })

            log_parts = [
                _("Đã gửi thông báo CTKM qua OdooBot tới <b>%s</b> người trong phạm vi.")
                % len(sent_users)
            ]
            if skipped:
                log_parts.append(
                    _("Bỏ qua %s nhân viên chưa có tài khoản nội bộ: %s")
                    % (len(skipped), ", ".join(skipped.mapped("name")))
                )
            if sent_users:
                log_parts.append(_("Người nhận: %s") % ", ".join(sent_users.mapped("name")))
            program.message_post(
                body=Markup("<br/>").join(Markup("%s") % part for part in log_parts),
                subtype_xmlid="mail.mt_note",
            )

            # Khởi động chuỗi tiến độ: chỉ bước đầu (chưa xong, có phụ trách) nhận tin việc
            first_step = program._ctkm_first_pending_checklist_line()
            if first_step:
                program._ctkm_send_checklist_step_notify(first_step)
            elif program.checklist_line_ids.filtered("user_id"):
                program.message_post(
                    body=_(
                        "Không còn bước tiến độ nào cần giao việc "
                        "(đã gửi tin hoặc đã đánh dấu xong)."
                    ),
                    subtype_xmlid="mail.mt_note",
                )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Gửi tin thành công"),
                "message": _(
                    "OdooBot CTKM đã thông báo tới mọi người trong phạm vi. "
                    "Người ở bước tiến độ tiếp theo chỉ nhận tin việc khi "
                    "bước trước hoàn thành và bấm Chuyển tiếp."
                ),
                "type": "success",
                "sticky": False,
            },
        }

    def _ctkm_notify_plain_text(self, html_value):
        return html2plaintext(html_value or "").replace("\xa0", " ").strip()

    def _ctkm_notify_detail_button_markup(self):
        # Không gắn data-oe-model/oe-id — tránh Discuss mở form trong tab Thảo luận.
        href = "/odoo/ctkm.task?ctkm_program_id=%s" % self.id
        return Markup(
            '<div class="o_ctkm_notify_detail mt-2">'
            '<a class="btn btn-primary btn-sm o_ctkm_notify_detail_btn" '
            'href="%s" data-program-id="%s" contenteditable="false">'
            "Bấm để xem chi tiết"
            "</a>"
            "</div>"
        ) % (escape(href), self.id)

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

