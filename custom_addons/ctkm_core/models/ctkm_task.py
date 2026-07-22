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

    # --- Thông tin CTKM (readonly, lấy từ chương trình) ---
    program_name = fields.Char(
        related='program_id.name', string='Tên chương trình', readonly=True,
    )
    program_kanban_state = fields.Selection(
        related='program_id.kanban_state', string='Trạng thái giai đoạn', readonly=True,
    )
    program_stage_id = fields.Many2one(
        related='program_id.stage_id', string='Giai đoạn', readonly=True,
    )
    program_date_begin = fields.Datetime(
        related='program_id.date_begin', string='Ngày bắt đầu', readonly=True,
    )
    program_date_end = fields.Datetime(
        related='program_id.date_end', string='Ngày kết thúc', readonly=True,
    )
    program_notify_code = fields.Char(
        related='program_id.notify_code', string='Mã số thông báo', readonly=True,
    )
    program_hour_quota = fields.Char(
        related='program_id.hour_quota', string='Định biên giờ', readonly=True,
    )
    program_organizer_id = fields.Many2one(
        related='program_id.organizer_id', string='Đơn vị tổ chức', readonly=True,
    )
    program_user_id = fields.Many2one(
        related='program_id.user_id', string='Người phụ trách', readonly=True,
    )
    program_address_id = fields.Many2one(
        related='program_id.address_id', string='Địa điểm', readonly=True,
    )
    program_event_url = fields.Char(
        related='program_id.event_url', string='URL sự kiện', readonly=True,
    )
    program_seats_limited = fields.Boolean(
        related='program_id.seats_limited', string='Giới hạn đăng ký', readonly=True,
    )
    program_seats_max = fields.Integer(
        related='program_id.seats_max', string='Số lượng tối đa', readonly=True,
    )
    program_company_id = fields.Many2one(
        related='program_id.company_id', string='Công ty CTKM', readonly=True,
    )
    program_badge_format = fields.Selection(
        related='program_id.badge_format', string='Kích thước nhãn', readonly=True,
    )
    program_badge_image = fields.Image(
        related='program_id.badge_image', string='Ảnh nhãn', readonly=True,
    )
    program_notify_document_ids = fields.Many2many(
        related='program_id.notify_document_ids',
        string='Tài liệu gửi kèm thông báo',
        readonly=True,
    )
    program_ticket_instructions = fields.Html(
        related='program_id.ticket_instructions',
        string='Hướng dẫn vé',
        readonly=True,
    )
    program_note = fields.Html(
        related='program_id.note', string='Ghi chú chương trình', readonly=True,
    )

    # Ghi chú / tài liệu của người nhận việc (được sửa)
    work_note = fields.Html(string='Ghi chú', sanitize_attributes=False)
    work_document_ids = fields.Many2many(
        'ir.attachment',
        'ctkm_task_work_document_rel',
        'task_id',
        'attachment_id',
        string='Tài liệu',
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
        """Gửi thông báo Discuss cho người hỗ trợ / bàn giao."""
        self.ensure_one()
        partners = self.support_employee_ids.mapped('user_id.partner_id')
        if self.handover_employee_id.user_id.partner_id:
            partners |= self.handover_employee_id.user_id.partner_id
        if not partners:
            raise UserError(_(
                'Chưa chọn người hỗ trợ / bàn giao có tài khoản Odoo để gửi thông báo.'
            ))
        body = _(
            'Bạn được nhờ hỗ trợ công việc CTKM:<br/>'
            '<b>%(content)s</b><br/>'
            'Ngày xử lý: %(process_date)s — Trạng thái: %(state)s'
        ) % {
            'content': self.program_name or self.name or '',
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
                'message': _('Đã thông báo tới %s người.') % len(partners),
                'type': 'success',
                'sticky': False,
            },
        }

    def action_advance_stage(self):
        """Chuyển chương trình KM liên kết sang giai đoạn tiếp theo."""
        self.ensure_one()
        if not self.program_id:
            raise UserError(_('Công việc chưa gắn chương trình khuyến mãi.'))

        program = self.program_id.sudo()
        current = program.stage_id
        Stage = self.env['ctkm.stage'].sudo()

        if current and current.pipe_end:
            raise UserError(_(
                'Chương trình "%(program)s" đã ở giai đoạn kết thúc "%(stage)s".'
            ) % {
                'program': program.display_name,
                'stage': current.display_name,
            })

        domain = [('sequence', '>', current.sequence)] if current else []
        next_stage = Stage.search(domain, order='sequence, id', limit=1)
        if not next_stage and current:
            next_stage = Stage.search(
                [('sequence', '=', current.sequence), ('id', '>', current.id)],
                order='id',
                limit=1,
            )
        if not next_stage:
            raise UserError(_('Không còn giai đoạn tiếp theo để chuyển.'))

        old_name = current.display_name if current else _('(chưa có)')
        program.write({
            'stage_id': next_stage.id,
            'kanban_state': 'normal',
        })
        if self.state != 'done':
            self.state = 'progress'
        self.message_post(
            body=_(
                'Đã chuyển bước chương trình <b>%(program)s</b>: '
                '%(old)s → <b>%(new)s</b>'
            ) % {
                'program': program.display_name,
                'old': old_name,
                'new': next_stage.display_name,
            },
            subtype_xmlid='mail.mt_note',
            body_is_html=True,
        )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Đã chuyển bước'),
                'message': _('%(old)s → %(new)s') % {
                    'old': old_name,
                    'new': next_stage.display_name,
                },
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
                task = Task.search(domain, limit=1)

        action = self.env['ir.actions.act_window']._for_xml_id(
            'ctkm_core.action_ctkm_task_my'
        )
        path = action.get('path') or 'ctkm-my-tasks'
        return {
            'type': 'ir.actions.act_url',
            'url': '/odoo/%s/%s' % (path, task.id),
            'target': 'self',
        }
