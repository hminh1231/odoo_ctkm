# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html2plaintext
from psycopg2 import IntegrityError


class CtkmTask(models.Model):
    _name = 'ctkm.task'
    _description = 'Công việc CTKM'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'process_date desc, id desc'

    process_date = fields.Date(
        string='Ngày xử lý',
        default=fields.Date.context_today,
        tracking=True,
    )
    name = fields.Text(
        string='Nội dung CV',
        required=True,
        tracking=True,
    )
    done_date = fields.Date(string='Ngày hoàn thành', tracking=True)
    state = fields.Selection(
        selection=[
            ('todo', 'Chưa xử lý'),
            ('progress', 'Đang xử lý'),
            ('done', 'Hoàn thành'),
        ],
        string='Trạng thái',
        default='todo',
        required=True,
        tracking=True,
    )
    duration = fields.Char(
        string='Thời gian xử lý',
        help='VD: 2 giờ',
    )
    handover_date = fields.Date(string='Ngày bàn giao', tracking=True)
    handover_employee_id = fields.Many2one(
        'hr.employee',
        string='Người nhận bàn giao',
        tracking=True,
        domain="[('active', '=', True)]",
    )
    manager_confirmed = fields.Boolean(
        string='Xác nhận quản lý',
        tracking=True,
    )
    support_employee_ids = fields.Many2many(
        'hr.employee',
        'ctkm_task_support_employee_rel',
        'task_id',
        'employee_id',
        string='Người hỗ trợ',
        domain="[('active', '=', True)]",
    )
    user_id = fields.Many2one(
        'res.users',
        string='Người tạo',
        default=lambda self: self.env.user,
        required=True,
        index=True,
        tracking=True,
    )
    program_id = fields.Many2one(
        'ctkm.program',
        string='Chương trình KM',
        ondelete='set null',
        index=True,
        tracking=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Công ty',
        default=lambda self: self.env.company,
    )

    _user_program_uniq = models.Constraint(
        'UNIQUE(user_id, program_id)',
        'Bạn đã có công việc cho chương trình này rồi.',
    )

    @api.onchange('state')
    def _onchange_state(self):
        if self.state == 'done' and not self.done_date:
            self.done_date = fields.Date.context_today(self)

    def action_notify_support(self):
        """Gửi thông báo Discuss cho người hỗ trợ."""
        self.ensure_one()
        partners = self.support_employee_ids.mapped('user_id.partner_id')
        if not partners:
            raise UserError(_(
                'Chưa chọn người hỗ trợ có tài khoản Odoo để gửi thông báo.'
            ))
        body = _(
            'Bạn được nhờ hỗ trợ công việc CTKM:<br/>'
            '<b>%(content)s</b><br/>'
            'Ngày xử lý: %(process_date)s — Trạng thái: %(state)s'
        ) % {
            'content': self.name or '',
            'process_date': self.process_date or '',
            'state': dict(self._fields['state'].selection).get(self.state, ''),
        }
        self.message_post(
            body=body,
            partner_ids=partners.ids,
            subtype_xmlid='mail.mt_note',
            body_is_html=True,
        )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Đã gửi thông báo'),
                'message': _('Đã thông báo tới %s người hỗ trợ.') % len(partners),
                'type': 'success',
                'sticky': False,
            },
        }

    @api.model
    def action_open_for_program(self, program_id):
        """Tạo/mở công việc khi bấm nút trong Discuss (không phụ thuộc ACL form CTKM)."""
        program_id = int(program_id or 0)
        if not program_id:
            raise UserError(_('Thiếu mã chương trình khuyến mãi.'))
        program = self.env['ctkm.program'].sudo().browse(program_id)
        if not program.exists():
            raise UserError(_('Không tìm thấy chương trình khuyến mãi.'))

        user = self.env.user
        notified_users = program.notify_line_ids.notify_employee_ids.mapped('user_id')
        allowed = (
            user.has_group('ctkm_core.group_ctkm_user')
            or program.user_id == user
            or user in notified_users
        )
        if not allowed:
            raise UserError(_('Bạn không có quyền mở công việc của chương trình này.'))

        Task = self.sudo()
        domain = [
            ('program_id', '=', program.id),
            ('user_id', '=', user.id),
        ]
        task = Task.search(domain, limit=1)
        if not task:
            content = program.name or _('Công việc CTKM')
            description = html2plaintext(program.description or '').replace('\xa0', ' ').strip()
            if description:
                content = '%s\n%s' % (content, description)
            try:
                with self.env.cr.savepoint():
                    task = Task.create({
                        'program_id': program.id,
                        'user_id': user.id,
                        'process_date': fields.Date.context_today(self),
                        'name': content,
                        'state': 'todo',
                        'company_id': program.company_id.id or self.env.company.id,
                    })
            except IntegrityError:
                # Bấm nút 2 lần liên tiếp / đã có sẵn — mở bản ghi cũ, không báo lỗi.
                task = Task.search(domain, limit=1)

        action = self.env['ir.actions.act_window']._for_xml_id(
            'ctkm_core.action_ctkm_task_my'
        )
        # Redirect full page → navbar CTKM (không giữ navbar Thảo luận).
        path = action.get('path') or 'ctkm-my-tasks'
        return {
            'type': 'ir.actions.act_url',
            'url': '/odoo/%s' % path,
            'target': 'self',
        }
