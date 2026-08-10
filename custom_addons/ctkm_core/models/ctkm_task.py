# -*- coding: utf-8 -*-

import logging
import re
import unicodedata

from markupsafe import Markup, escape
from psycopg2 import IntegrityError

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html2plaintext

_logger = logging.getLogger(__name__)

# Nhận diện bước công việc theo tên (đã bỏ dấu / bỏ ký tự đặc biệt) để không phụ
# thuộc vào khoảng trắng hay lỗi chính tả nhỏ khi đặt tên giai đoạn.
TEM_TAG_IMPORT_TASK_MARKERS = ('dobbthaytemtag',)
TEM_PHOTO_TASK_MARKERS = ('chuptemguilengroup', 'chupteamguilengroup')
TEM_REPLACE_TASK_MARKERS = ('thaytemtag',)


def normalize_step_key(value):
    """Chuẩn hóa tên bước: chữ thường, bỏ dấu, chỉ giữ chữ và số."""
    text = unicodedata.normalize('NFD', (value or '').lower())
    text = ''.join(char for char in text if unicodedata.category(char) != 'Mn')
    return re.sub(r'[^a-z0-9]+', '', text.replace('đ', 'd'))


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
            ('waiting_confirm', 'Chờ xác nhận'),
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
    can_confirm_as_manager = fields.Boolean(
        string='Được phép xác nhận quản lý',
        compute='_compute_can_confirm_as_manager',
    )
    checklist_need_manager_confirm = fields.Boolean(
        string='Checklist cần quản lý xác nhận',
        compute='_compute_checklist_need_manager_confirm',
    )
    is_task_assignee = fields.Boolean(
        string='Là người nhận việc',
        compute='_compute_is_task_assignee',
    )
    is_current_stage_task = fields.Boolean(
        string='Bước hiện tại',
        compute='_compute_is_current_stage_task',
        search='_search_is_current_stage_task',
        help='True khi công việc thuộc bước (giai đoạn) hiện tại của CTKM, '
             'tức là đến lượt xử lý lúc này (không phải bước tương lai).',
    )
    is_tem_tag_import_task = fields.Boolean(
        string='Bước import Tem/Tag',
        compute='_compute_task_step_flags',
        help='Công việc thuộc bước "Đổ BB thay tem/tag (file tổng)".',
    )
    is_tem_photo_task = fields.Boolean(
        string='Bước chụp ảnh tem/tag',
        compute='_compute_task_step_flags',
    )
    is_tem_replace_task = fields.Boolean(
        string='Bước thay tem/tag',
        compute='_compute_task_step_flags',
    )
    tem_tag_replace_ids = fields.One2many(
        'ctkm.task.tem.tag.replace.line',
        'task_id',
        compute='_compute_tem_tag_replace_ids',
        string='Tem/Tag đã thay',
        help='Tem/Tag của CTKM này thuộc cửa hàng của nhân viên, để đánh dấu "Đã thay".',
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
        string='Người nhận việc',
        default=lambda self: self.env.user,
        required=True,
        index=True,
        tracking=True,
    )
    program_id = fields.Many2one(
        'ctkm.program',
        string='Chương trình KM',
        ondelete='cascade',
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
    # Binary qua sudo (không đi ACL attachment của program).
    program_badge_image = fields.Image(
        string='Ảnh nhãn',
        compute='_compute_program_badge_image',
        readonly=True,
    )
    # Bản copy gắn task — nhân viên đọc được mà không cần quyền program attachment.
    program_notify_document_ids = fields.Many2many(
        'ir.attachment',
        'ctkm_task_program_document_rel',
        'task_id',
        'attachment_id',
        string='Tài liệu gửi kèm thông báo',
        readonly=True,
        copy=False,
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

    detail_tem_tag_file = fields.Binary(string='File Excel Tem/Tag')
    detail_tem_tag_filename = fields.Char(string='Tên file Excel')
    detail_tem_photo_ids = fields.Many2many(
        'ir.attachment',
        'ctkm_task_detail_tem_photo_rel',
        'task_id',
        'attachment_id',
        string='Ảnh tem/tag',
    )

    # Bước phạm vi thông báo (Gửi tin tuần tự theo STT dòng)
    notify_line_id = fields.Many2one(
        'ctkm.program.notify.line',
        string='Bước phạm vi',
        ondelete='set null',
        index=True,
        copy=False,
    )
    checklist_line_id = fields.Many2one(
        'ctkm.program.checklist.line',
        string='Bước checklist',
        ondelete='set null',
        index=True,
        copy=False,
    )
    notify_step_label = fields.Char(
        related='notify_line_id.step_label',
        string='Bước xử lý',
        readonly=True,
    )
    checklist_step_name = fields.Char(
        string='Tên bước checklist',
        related='checklist_line_id.name',
        readonly=True,
    )
    forwarded = fields.Boolean(
        string='Đã chuyển tiếp bước',
        default=False,
        copy=False,
        tracking=True,
    )
    # Ghi chú / file nhận từ chương trình + bước trước (readonly)
    handover_note = fields.Html(
        string='Ghi chú nhận từ bước trước',
        sanitize_attributes=False,
        readonly=True,
        copy=False,
    )
    handover_document_ids = fields.Many2many(
        'ir.attachment',
        'ctkm_task_handover_document_rel',
        'task_id',
        'attachment_id',
        string='Tài liệu nhận từ bước trước',
        readonly=True,
        copy=False,
    )

    _user_program_line_uniq = models.Constraint(
        'UNIQUE(user_id, program_id, notify_line_id, checklist_line_id)',
        'Bạn đã có công việc cho bước phạm vi / bước checklist này rồi.',
    )

    @api.depends_context('uid')
    def _compute_can_confirm_as_manager(self):
        for task in self:
            task.can_confirm_as_manager = task._user_can_confirm_as_manager(self.env.user)

    @api.depends('program_id', 'program_id.badge_image')
    def _compute_program_badge_image(self):
        for task in self:
            task.program_badge_image = task.program_id.sudo().badge_image or False

    @api.depends('user_id')
    @api.depends_context('uid')
    def _compute_is_task_assignee(self):
        uid = self.env.user.id
        for task in self:
            task.is_task_assignee = task.user_id.id == uid

    @api.depends('user_id', 'state', 'manager_confirmed')
    @api.depends_context('uid')
    def _compute_is_current_stage_task(self):
        for task in self:
            program = task.program_id
            current_stage = program.stage_id if program else False
            task_stage = task.program_stage_id
            if not task_stage and task.checklist_line_id:
                task_stage = task.checklist_line_id.stage_id
            is_current_stage = bool(
                current_stage and task_stage and task_stage.id == current_stage.id
            )
            is_actionable = task.state in ('todo', 'progress', 'waiting_confirm')
            # "Bước hiện tại": bước đang ở giai đoạn hiện tại CỦA CTKM, hoặc bước
            # nhân viên cần xử lý (chưa xong) — không hiện các bước tương lai đã xong.
            task.is_current_stage_task = is_current_stage or (
                is_actionable and bool(task_stage or not current_stage)
            )

    def _search_is_current_stage_task(self, operator, value):
        if operator in ('=', True) and value:
            progs = self.env['ctkm.program'].search([])
            stage_ids = progs.filtered('stage_id').mapped('stage_id').ids
            domain = [('user_id', '=', self.env.uid)]
            if stage_ids:
                domain = domain + [('checklist_line_id.stage_id', 'in', stage_ids)]
            domain = domain + [('state', 'in', ('todo', 'progress', 'waiting_confirm'))]
            return domain
        if operator in ('=', False) and not value:
            progs = self.env['ctkm.program'].search([])
            stage_ids = progs.filtered('stage_id').mapped('stage_id').ids
            domain = [('user_id', '=', self.env.uid)]
            if stage_ids:
                domain = domain + [('checklist_line_id.stage_id', 'in', stage_ids)]
            domain = domain + [('state', 'not in', ('todo', 'progress', 'waiting_confirm'))]
            return domain
        # Các tổ hợp hiếm: lọc bằng Python qua compute.
        candidates = self.search([('user_id', '=', self.env.uid)])
        matching = candidates.filtered(lambda t: t.is_current_stage_task == value)
        return [('id', 'in', matching.ids)]

    @api.depends('checklist_line_id', 'checklist_line_id.need_manager_confirm')
    def _compute_checklist_need_manager_confirm(self):
        for task in self:
            task.checklist_need_manager_confirm = (
                task.checklist_line_id.need_manager_confirm
                if task.checklist_line_id
                else True
            )

    @api.depends('name', 'checklist_step_name')
    def _compute_task_step_flags(self):
        for task in self:
            keys = [
                key
                for key in (
                    normalize_step_key(task.name),
                    normalize_step_key(task.checklist_step_name),
                )
                if key
            ]
            task.is_tem_tag_import_task = any(
                marker in key for key in keys for marker in TEM_TAG_IMPORT_TASK_MARKERS
            )
            task.is_tem_photo_task = any(
                marker in key for key in keys for marker in TEM_PHOTO_TASK_MARKERS
            )
            task.is_tem_replace_task = any(
                marker in key for key in keys for marker in TEM_REPLACE_TASK_MARKERS
            )

    @api.depends('program_id', 'user_id')
    def _compute_tem_tag_replace_ids(self):
        for task in self:
            task.tem_tag_replace_ids = [(5, 0, 0)]
            if not (task.program_id and task.user_id):
                continue
            tem_tag = task.env['ctkm.inventory.tem.tag']
            domain = [('program_id', '=', task.program_id.id)]
            store_keys = tem_tag.current_user_store_keys()
            if store_keys:
                domain = domain + [('store_key', 'in', store_keys)]
            rows = tem_tag.search(domain, order='date desc, material_code, store')
            lines = []
            for row in rows:
                lines.append((0, 0, {
                    'material_code': row.material_code,
                    'store': row.store,
                    'date': row.date,
                    'replaced': row.replaced,
                }))
            task.tem_tag_replace_ids = lines

    def _get_worker_employee(self):
        """Nhân viên gắn với người tạo công việc."""
        self.ensure_one()
        employee = self.user_id.sudo().employee_id
        if employee:
            return employee
        return self.env['hr.employee'].sudo().search(
            [('user_id', '=', self.user_id.id)], limit=1
        )

    def _get_org_chart_manager_user(self):
        """Quản lý trực tiếp theo org chart (parent_id)."""
        self.ensure_one()
        employee = self._get_worker_employee()
        manager = employee.parent_id.sudo() if employee else self.env['hr.employee']
        user = manager.user_id
        if user and user.active and not user.share and user.partner_id:
            return user
        return self.env['res.users']

    def _user_can_confirm_as_manager(self, user):
        """Chỉ quản lý org-chart (hoặc CTKM Administrator) được xác nhận."""
        self.ensure_one()
        if not user or user.share:
            return False
        if user.has_group('ctkm_core.group_ctkm_manager'):
            return True
        manager_user = self._get_org_chart_manager_user()
        return bool(manager_user and manager_user.id == user.id)

    def _ctkm_task_form_url(self):
        self.ensure_one()
        menu = self.env.ref('ctkm_core.menu_ctkm_my_tasks', raise_if_not_found=False)
        app_menu_id = False
        if menu:
            app_menu = menu
            while app_menu.parent_id:
                app_menu = app_menu.parent_id
            app_menu_id = app_menu.id
        # Dùng model path (ctkm.task), không dùng action path (ctkm-my-tasks)
        # để tránh webclient gọi RPC với model sai.
        url = '/odoo/ctkm.task/%s' % self.id
        if app_menu_id:
            url = '%s?menu_id=%s' % (url, app_menu_id)
        return url, app_menu_id

    def _ctkm_manager_confirm_button_markup(self):
        self.ensure_one()
        href = '/odoo/ctkm.task/%s' % self.id
        return Markup(
            '<div class="o_ctkm_notify_detail mt-2">'
            '<a class="btn btn-primary btn-sm o_ctkm_manager_confirm_btn" '
            'href="%s" data-task-id="%s" contenteditable="false">'
            'Bấm để xác nhận hoàn thành'
            '</a>'
            '</div>'
        ) % (escape(href), self.id)

    def _ctkm_manager_confirm_message_body(self):
        self.ensure_one()
        worker_name = self.user_id.name or ''
        program_name = self.program_name or self.name or ''
        lines = [
            Markup('<b>Yêu cầu xác nhận hoàn thành công việc CTKM</b>'),
            Markup('Nhân viên <b>%s</b> đã bấm Hoàn thành.') % escape(worker_name),
            Markup('Công việc: <b>%s</b>') % escape(program_name),
            Markup(
                'Vui lòng vào form và tick <b>Xác nhận quản lý</b> '
                'để hoàn tất trạng thái.'
            ),
            self._ctkm_manager_confirm_button_markup(),
        ]
        return Markup('<br/>').join(lines)

    def _ctkm_worker_confirmed_button_markup(self):
        self.ensure_one()
        href = '/odoo/ctkm.task/%s' % self.id
        return Markup(
            '<div class="o_ctkm_notify_detail mt-2">'
            '<a class="btn btn-primary btn-sm o_ctkm_task_open_btn" '
            'href="%s" data-task-id="%s" contenteditable="false">'
            'Bấm để xem công việc'
            '</a>'
            '</div>'
        ) % (escape(href), self.id)

    def _ctkm_worker_manager_confirmed_message_body(self, manager_user=None):
        self.ensure_one()
        manager_user = manager_user or self.env.user
        program_name = self.program_name or self.name or ''
        lines = [
            Markup('<b>Quản lý đã xác nhận hoàn thành công việc CTKM</b>'),
            Markup('Quản lý <b>%s</b> đã xác nhận.') % escape(manager_user.name or ''),
            Markup('Công việc: <b>%s</b>') % escape(program_name),
            Markup('Trạng thái công việc đã chuyển sang <b>Hoàn thành</b>.'),
            self._ctkm_worker_confirmed_button_markup(),
        ]
        return Markup('<br/>').join(lines)

    def _post_ctkm_bot_dm(self, recipient_user, body):
        """Gửi DM Discuss từ OdooBot CTKM tới một user."""
        self.ensure_one()
        Message = self.env['mail.message']
        if not recipient_user or recipient_user.share or not recipient_user.partner_id:
            return Message
        bot_user = self.env.ref(
            'business_discuss_bots.user_bot_ctkm', raise_if_not_found=False
        )
        if not bot_user or not bot_user.partner_id:
            raise UserError(_('Chưa cấu hình OdooBot CTKM trên hệ thống.'))
        try:
            chat = (
                self.env['discuss.channel']
                .sudo()
                .with_user(recipient_user)
                ._get_or_create_chat([bot_user.partner_id.id], pin=True)
            )
            return chat.with_user(bot_user).sudo().message_post(
                body=body,
                message_type='comment',
                subtype_xmlid='mail.mt_comment',
                author_id=bot_user.partner_id.id,
            )
        except Exception:
            _logger.exception(
                'ctkm_core: OdooBot CTKM DM failed task_id=%s recipient_user_id=%s',
                self.id,
                recipient_user.id,
            )
            return Message

    def _notify_org_manager_confirm(self):
        """Gửi tin OdooBot CTKM tới quản lý org-chart để xác nhận."""
        self.ensure_one()
        manager_user = self._get_org_chart_manager_user()
        if not manager_user:
            raise UserError(_(
                'Không tìm thấy quản lý trực tiếp trên organization chart '
                '(hoặc quản lý chưa có tài khoản Odoo). '
                'Không thể gửi yêu cầu xác nhận.'
            ))
        if manager_user == self.user_id:
            raise UserError(_(
                'Quản lý trực tiếp trùng với người làm việc. '
                'Vui lòng kiểm tra lại organization chart.'
            ))
        posted = self._post_ctkm_bot_dm(
            manager_user, self._ctkm_manager_confirm_message_body()
        )
        if not posted:
            raise UserError(_(
                'Không gửi được thông báo Discuss tới quản lý %s.'
            ) % manager_user.name)
        self.message_post(
            body=_(
                'Đã gửi yêu cầu xác nhận tới quản lý <b>%s</b> qua OdooBot CTKM.'
            ) % manager_user.name,
            subtype_xmlid='mail.mt_note',
            body_is_html=True,
        )
        return manager_user

    def _notify_worker_manager_confirmed(self, manager_user=None):
        """Gửi tin OdooBot CTKM cho người nhận việc khi quản lý đã xác nhận."""
        self.ensure_one()
        worker = self.user_id
        if not worker or worker.share or not worker.partner_id:
            return self.env['res.users']
        manager_user = manager_user or self.env.user
        # Tránh spam nếu người nhận việc chính là người xác nhận.
        if worker == manager_user:
            return worker
        posted = self._post_ctkm_bot_dm(
            worker,
            self._ctkm_worker_manager_confirmed_message_body(manager_user),
        )
        if not posted:
            _logger.warning(
                'ctkm_core: cannot notify worker task_id=%s user_id=%s',
                self.id,
                worker.id,
            )
            return self.env['res.users']
        self.message_post(
            body=_(
                'Đã thông báo cho <b>%s</b> rằng quản lý đã xác nhận '
                '(qua OdooBot CTKM).'
            ) % worker.name,
            subtype_xmlid='mail.mt_note',
            body_is_html=True,
        )
        return worker

    @api.onchange('state')
    def _onchange_state(self):
        if self.state in ('waiting_confirm', 'done') and not self.done_date:
            self.done_date = fields.Date.context_today(self)

    def write(self, vals):
        vals = dict(vals)
        # Đồng bộ từ checklist / nút workflow dùng context nội bộ.
        internal = (
            self.env.context.get('ctkm_internal_state_write')
            or self.env.context.get('ctkm_task_sync')
        )
        user_set_state = 'state' in vals

        if user_set_state and not internal:
            raise UserError(_(
                'Không thể đổi trạng thái trực tiếp. '
                'Dùng nút Hoàn thành hoặc Xác nhận quản lý.'
            ))

        if 'manager_confirmed' in vals and not internal:
            for task in self:
                if not task._user_can_confirm_as_manager(self.env.user):
                    raise UserError(_(
                        'Chỉ quản lý trực tiếp (theo organization chart) '
                        'mới được bấm Xác nhận quản lý.'
                    ))

        if vals.get('manager_confirmed'):
            for task in self:
                next_state = vals.get('state', task.state)
                if next_state not in ('waiting_confirm', 'done'):
                    raise UserError(_(
                        'Chỉ xác nhận quản lý được sau khi đã bấm Hoàn thành.'
                    ))
            vals['state'] = 'done'
        elif 'manager_confirmed' in vals and not vals['manager_confirmed']:
            next_state = vals.get('state')
            if next_state is None or next_state == 'done':
                vals['state'] = 'waiting_confirm'

        if 'state' in vals and vals['state'] not in ('waiting_confirm', 'done'):
            vals['manager_confirmed'] = False

        if vals.get('state') == 'done' and not internal:
            for task in self:
                confirmed = (
                    vals['manager_confirmed']
                    if 'manager_confirmed' in vals
                    else task.manager_confirmed
                )
                if not confirmed:
                    raise UserError(_(
                        'Trạng thái Hoàn thành chỉ khi đã bấm Hoàn thành '
                        'và có Xác nhận quản lý.'
                    ))

        newly_confirmed = self.browse()
        if vals.get('manager_confirmed'):
            newly_confirmed = self.filtered(lambda t: not t.manager_confirmed)

        res = super().write(vals)

        if newly_confirmed:
            manager_user = self.env.user
            for task in newly_confirmed:
                task._notify_worker_manager_confirmed(manager_user)

        if 'checklist_line_id' in vals or 'state' in vals or 'done_date' in vals:
            self._ctkm_sync_checklist_from_task(
                checklist_line_id=vals.get('checklist_line_id'),
                state=vals.get('state'),
                done_date=vals.get('done_date'),
            )

        return res

    def action_mark_done(self):
        """Người làm việc báo hoàn thành → gửi tin quản lý xác nhận."""
        notified = self.browse()
        already_waiting = self.browse()
        directly_done = self.browse()
        for task in self:
            if task.user_id != self.env.user and not self.env.user.has_group(
                'ctkm_core.group_ctkm_manager'
            ):
                raise UserError(_(
                    'Chỉ người nhận việc mới được bấm Hoàn thành.'
                ))
            if task.state == 'done':
                already_waiting |= task
                continue
            checklist = task.checklist_line_id
            need_confirm = (
                task.checklist_need_manager_confirm
                if checklist
                else True
            )
            if not need_confirm:
                # Không cần xác nhận quản lý: nhân viên bấm Hoàn thành là xong,
                # không tìm quản lý trên org chart và không gửi tin xác nhận.
                task.with_context(ctkm_internal_state_write=True).write({
                    'state': 'done',
                    'manager_confirmed': False,
                    'done_date': task.done_date or fields.Date.context_today(task),
                })
                directly_done |= task
                continue
            if task.state == 'waiting_confirm' and not task.manager_confirmed:
                already_waiting |= task
                continue
            manager_user = task._get_org_chart_manager_user()
            if not manager_user:
                raise UserError(_(
                    'Không tìm thấy quản lý trực tiếp trên organization chart '
                    '(hoặc quản lý chưa có tài khoản Odoo).'
                ))
            vals = {
                'state': 'waiting_confirm',
                'manager_confirmed': False,
            }
            if not task.done_date:
                vals['done_date'] = fields.Date.context_today(task)
            task.with_context(ctkm_internal_state_write=True).write(vals)
            task._notify_org_manager_confirm()
            notified |= task

        if directly_done:
            title = _('Đã hoàn thành')
            message = _('Công việc đã được đánh dấu Hoàn thành (không cần xác nhận quản lý).')
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': title,
                    'message': message,
                    'type': 'success',
                    'sticky': False,
                },
            }

        if notified:
            title = _('Đã gửi hoàn thành')
            message = _(
                'Đã bấm Hoàn thành. OdooBot CTKM đã gửi yêu cầu xác nhận '
                'tới quản lý trực tiếp.'
            )
        else:
            title = _('Đã xử lý')
            message = _('Công việc này đã ở trạng thái hoàn thành.')
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': title,
                'message': message,
                'type': 'success' if notified else 'warning',
                'sticky': False,
            },
        }

    def action_manager_confirm(self):
        """Quản lý xác nhận hoàn thành → thông báo cho người nhận việc."""
        for task in self:
            if not task._user_can_confirm_as_manager(self.env.user):
                raise UserError(_(
                    'Chỉ quản lý trực tiếp (theo organization chart) '
                    'mới được xác nhận hoàn thành.'
                ))
            if task.state not in ('waiting_confirm', 'done'):
                raise UserError(_(
                    'Chỉ xác nhận được sau khi nhân viên đã bấm Hoàn thành.'
                ))
            if task.manager_confirmed and task.state == 'done':
                continue
            task.with_context(ctkm_internal_state_write=True).write({
                'manager_confirmed': True,
                'state': 'done',
            })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Đã xác nhận'),
                'message': _(
                    'Đã xác nhận quản lý. OdooBot CTKM đã thông báo '
                    'cho người nhận việc.'
                ),
                'type': 'success',
                'sticky': False,
            },
        }

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
        """Chuyển tiếp → giao việc bước tiến độ tiếp theo (kèm ghi chú/file)."""
        self.ensure_one()
        if self.state != 'done':
            raise UserError(_(
                'Chỉ chuyển tiếp được sau khi đã bấm Hoàn thành '
                '(trạng thái công việc phải là Hoàn thành).'
            ))
        if self.checklist_need_manager_confirm and not self.manager_confirmed:
            raise UserError(_(
                'Cần có Xác nhận quản lý trước khi chuyển tiếp.'
            ))
        if self.forwarded:
            raise UserError(_('Công việc này đã chuyển tiếp rồi.'))
        if not self.program_id:
            raise UserError(_('Công việc chưa gắn chương trình khuyến mãi.'))

        program = self.program_id.sudo()
        current_checklist = self.checklist_line_id.sudo()
        current_notify = self.notify_line_id.sudo()
        step_label = (
            current_checklist.name
            or current_notify.step_label
            or _('(không xác định)')
        )
        self.write({'forwarded': True})
        self.message_post(
            body=_('Đã bấm <b>Chuyển tiếp</b> cho bước <b>%s</b>.')
            % escape(step_label),
            subtype_xmlid='mail.mt_note',
            body_is_html=True,
        )

        # Ưu tiên chuỗi Tiến độ thực hiện
        if current_checklist:
            return self._ctkm_advance_checklist_step(program, current_checklist)

        # Tương thích task cũ gắn Phạm vi thông báo
        if current_notify:
            return self._ctkm_advance_notify_line_step(program, current_notify)

        return self._ctkm_advance_program_stage(program)

    def _ctkm_advance_checklist_step(self, program, current_line):
        """Sau Chuyển tiếp: gửi tin việc cho bước tiến độ kế tiếp."""
        self.ensure_one()
        next_line = program._ctkm_next_checklist_line(current_line)
        if next_line:
            handover_note, handover_docs = self._ctkm_collect_handover_from_checklist(
                program, current_line
            )
            sent = program.sudo()._ctkm_send_checklist_step_notify(
                next_line,
                handover_note=handover_note,
                handover_attachments=handover_docs.sudo() if handover_docs else handover_docs,
            )
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Đã chuyển bước'),
                    'message': _(
                        'Đã gửi OdooBot CTKM giao việc bước "%(step)s" cho %(user)s, '
                        'kèm ghi chú và tài liệu đã đẩy qua.'
                    ) % {
                        'step': next_line.name or '',
                        'user': sent.name if sent else (next_line.user_id.name or ''),
                    },
                    'type': 'success',
                    'sticky': False,
                },
            }
        return self._ctkm_advance_program_stage(program)

    def _ctkm_advance_notify_line_step(self, program, current_line):
        """Giữ luồng Chuyển tiếp theo phạm vi thông báo (task cũ)."""
        self.ensure_one()
        siblings = self.sudo().search([
            ('program_id', '=', program.id),
            ('notify_line_id', '=', current_line.id),
        ])
        pending = siblings.filtered(
            lambda t: not t.forwarded or t.state != 'done' or not t.manager_confirmed
        )
        if pending:
            names = ', '.join(pending.mapped('user_id.name'))
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Đã chuyển tiếp phần của bạn'),
                    'message': _(
                        'Chờ các người còn lại hoàn tất bước "%(step)s": %(names)s'
                    ) % {
                        'step': current_line.step_label or '',
                        'names': names,
                    },
                    'type': 'warning',
                    'sticky': False,
                },
            }

        lines = program.notify_line_ids.sorted(lambda l: (l.sequence, l.id))
        next_line = self.env['ctkm.program.notify.line']
        found_current = False
        for line in lines:
            if found_current:
                next_line = line
                break
            if line.id == current_line.id:
                found_current = True

        if next_line:
            handover_note, handover_docs = self._ctkm_collect_handover_from_line(
                program, current_line
            )
            sent = program.sudo()._ctkm_send_notify_line(
                next_line,
                handover_note=handover_note,
                handover_attachments=handover_docs.sudo() if handover_docs else handover_docs,
            )
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Đã chuyển bước'),
                    'message': _(
                        'Đã gửi OdooBot CTKM tới bước "%(step)s" (%(count)s người), '
                        'kèm ghi chú và tài liệu đã đẩy qua.'
                    ) % {
                        'step': next_line.step_label or '',
                        'count': len(sent),
                    },
                    'type': 'success',
                    'sticky': False,
                },
            }

        return self._ctkm_advance_program_stage(program)

    def _ctkm_advance_program_stage(self, program):
        """Chuyển giai đoạn CTKM khi hết bước phạm vi / task không gắn dòng."""
        self.ensure_one()
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
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Hoàn tất các bước phạm vi'),
                    'message': _(
                        'Đã chuyển tiếp hết các bước người nhận. '
                        'Không còn giai đoạn chương trình tiếp theo.'
                    ),
                    'type': 'success',
                    'sticky': False,
                },
            }

        old_name = current.display_name if current else _('(chưa có)')
        program.write({
            'stage_id': next_stage.id,
            'kanban_state': 'normal',
        })
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
    def _task_content_from_program(self, program):
        content = program.name or _('Công việc CTKM')
        description = html2plaintext(program.description or '').replace('\xa0', ' ').strip()
        if description:
            content = '%s\n%s' % (content, description)
        return content

    @api.model
    def _duplicate_attachments_for_task(self, attachments, task, description_prefix=None):
        """Copy file để bước sau / nhân viên đọc được (ACL theo task mới).

        Luôn sudo: người bấm Chuyển tiếp không có quyền ghi attachment
        lên task của người bước tiếp theo.
        """
        Attachment = self.env['ir.attachment'].sudo()
        copies = Attachment
        for att in attachments.sudo():
            vals = {
                'res_model': 'ctkm.task',
                'res_id': task.id,
                'name': att.name,
            }
            if description_prefix:
                vals['description'] = '%s%s' % (description_prefix, att.id)
            copies |= att.copy(vals)
        return copies

    def _ensure_program_notify_documents(self):
        """Copy tài liệu CTKM vào task để nhân viên không bị chặn ACL program."""
        for task in self.sudo():
            program = task.program_id
            if not program or not task.id:
                continue
            Attachment = self.env['ir.attachment'].sudo()
            copies = Attachment
            for doc in program.notify_document_ids:
                marker = 'ctkm_program_doc:%s' % doc.id
                existing = Attachment.search([
                    ('res_model', '=', 'ctkm.task'),
                    ('res_id', '=', task.id),
                    ('description', '=', marker),
                ], limit=1)
                if not existing:
                    existing = doc.copy({
                        'res_model': 'ctkm.task',
                        'res_id': task.id,
                        'name': doc.name,
                        'description': marker,
                    })
                copies |= existing
            task.program_notify_document_ids = [(6, 0, copies.ids)]

    @api.model
    def _ctkm_collect_handover_from_line(self, program, notify_line):
        """Gom ghi chú/file chương trình + task đã chuyển tiếp của bước phạm vi."""
        program.ensure_one()
        note_parts = []
        docs = self.env['ir.attachment']
        tasks = self.sudo().search([
            ('program_id', '=', program.id),
            ('notify_line_id', '=', notify_line.id),
            ('forwarded', '=', True),
        ], order='id')
        # Handover đã có trên bước này (gồm chương trình + bước trước hơn)
        if tasks and tasks[0].handover_note:
            note_parts.append(Markup(tasks[0].handover_note))
            docs |= tasks[0].handover_document_ids
        elif program.note:
            note_parts.append(
                Markup('<p><b>%s</b></p>%s')
                % (escape(_('Ghi chú chương trình')), Markup(program.note))
            )
        if not tasks or not tasks[0].handover_document_ids:
            docs |= program.notify_document_ids

        for task in tasks:
            step = task.notify_step_label or _('Bước trước')
            worker = task.user_id.name or ''
            if task.work_note:
                note_parts.append(
                    Markup('<p><b>%s</b></p>%s')
                    % (
                        escape(_('Ghi chú từ %s (%s)') % (worker, step)),
                        Markup(task.work_note),
                    )
                )
            docs |= task.work_document_ids
        handover_note = Markup('<hr/>').join(note_parts) if note_parts else False
        return handover_note, docs

    @api.model
    def _ctkm_collect_handover_from_checklist(self, program, checklist_line):
        """Gom ghi chú/file từ bước tiến độ đã chuyển tiếp."""
        program.ensure_one()
        note_parts = []
        docs = self.env['ir.attachment']
        tasks = self.sudo().search([
            ('program_id', '=', program.id),
            ('checklist_line_id', '=', checklist_line.id),
            ('forwarded', '=', True),
        ], order='id')
        if tasks and tasks[0].handover_note:
            note_parts.append(Markup(tasks[0].handover_note))
            docs |= tasks[0].handover_document_ids
        elif program.note:
            note_parts.append(
                Markup('<p><b>%s</b></p>%s')
                % (escape(_('Ghi chú chương trình')), Markup(program.note))
            )
        if not tasks or not tasks[0].handover_document_ids:
            docs |= program.notify_document_ids

        for task in tasks:
            step = task.checklist_step_name or _('Bước trước')
            worker = task.user_id.name or ''
            if task.work_note:
                note_parts.append(
                    Markup('<p><b>%s</b></p>%s')
                    % (
                        escape(_('Ghi chú từ %s (%s)') % (worker, step)),
                        Markup(task.work_note),
                    )
                )
            docs |= task.work_document_ids
        handover_note = Markup('<hr/>').join(note_parts) if note_parts else False
        return handover_note, docs

    def _ctkm_sync_checklist_from_task(self, checklist_line_id=None, state=None, done_date=None):
        """Đồng bộ trạng thái/ngày xong từ công việc về bước checklist."""
        self.ensure_one()
        checklist = self.checklist_line_id
        if not checklist and checklist_line_id:
            checklist = self.env['ctkm.program.checklist.line'].browse(checklist_line_id)
        if not checklist or not checklist.exists():
            return
        vals = {}
        if state:
            mapped = {'todo': 'todo', 'progress': 'progress', 'waiting_confirm': 'progress', 'done': 'done'}
            vals['state'] = mapped.get(state, state)
        if done_date:
            vals['done_date'] = done_date
        if vals and not self.env.context.get('ctkm_task_sync'):
            checklist.sudo().with_context(ctkm_task_sync=True).write(vals)

    @api.model
    def _ctkm_sync_task_from_checklist(self, checklist):
        """Đồng bộ công việc từ bước checklist (gán người / tiến độ trên CTKM).

        Trạng thái Hoàn thành của task vẫn đi qua nút Hoàn thành / Xác nhận quản lý.
        Checklist chỉ đẩy todo/progress; cột Xong cập nhật done_date, không ép task = done.
        """
        if not checklist or not checklist.exists():
            return self.browse()
        Task = self.sudo()
        task = Task.search([
            ('program_id', '=', checklist.program_id.id),
            ('checklist_line_id', '=', checklist.id),
        ], limit=1)
        if not task:
            return self.browse()
        vals = {}
        if checklist.user_id and task.user_id != checklist.user_id:
            vals['user_id'] = checklist.user_id.id
        if checklist.state in ('todo', 'progress'):
            if task.state not in ('waiting_confirm', 'done'):
                vals['state'] = checklist.state
        if checklist.done_date and task.done_date != checklist.done_date:
            vals['done_date'] = checklist.done_date
        if checklist.name and task.name != checklist.name:
            vals['name'] = checklist.name
        if vals and not task.env.context.get('ctkm_task_sync'):
            task.with_context(
                ctkm_task_sync=True,
                ctkm_internal_state_write=True,
            ).write(vals)
        # Nếu đang chờ xác nhận quản lý mà giờ không còn cần, tự động hoàn thành.
        if not checklist.need_manager_confirm and task.state == 'waiting_confirm':
            task.with_context(
                ctkm_task_sync=True,
                ctkm_internal_state_write=True,
            ).write({
                'state': 'done',
                'manager_confirmed': False,
                'done_date': task.done_date or fields.Date.context_today(task),
            })
        return task

    @api.model
    def _get_or_create_for_program_user(
        self, program, user, notify_line=None,
        handover_note=False, handover_attachments=None,
    ):
        """Mỗi người + mỗi bước phạm vi có 1 công việc riêng."""
        program.ensure_one()
        if not user or not user.exists():
            return self.browse()
        Task = self.sudo()
        domain = [
            ('program_id', '=', program.id),
            ('user_id', '=', user.id),
        ]
        if notify_line:
            domain.append(('notify_line_id', '=', notify_line.id))
        else:
            domain.append(('notify_line_id', '=', False))
        task = Task.search(domain, limit=1)
        if not task and not notify_line:
            checklist = program.checklist_line_ids.filtered(
                lambda l: l.user_id == user
            )[:1]
            if checklist:
                task = Task.search([
                    ('program_id', '=', program.id),
                    ('user_id', '=', user.id),
                    ('checklist_line_id', '=', checklist.id),
                ], limit=1)
        if task:
            vals = {}
            if handover_note and not task.handover_note:
                vals['handover_note'] = handover_note
            if vals:
                task.write(vals)
            if handover_attachments and not task.handover_document_ids:
                copies = self._duplicate_attachments_for_task(handover_attachments, task)
                task.handover_document_ids = [(6, 0, copies.ids)]
            task._ensure_program_notify_documents()
            return task
        vals = {
            'program_id': program.id,
            'user_id': user.id,
            'process_date': fields.Date.context_today(self),
            'name': self._task_content_from_program(program),
            'state': 'todo',
            'company_id': program.company_id.id or self.env.company.id,
            'notify_line_id': notify_line.id if notify_line else False,
            'handover_note': handover_note or False,
        }
        if not notify_line:
            checklist = program.checklist_line_ids.filtered(
                lambda l: l.user_id == user
            )[:1]
            if checklist:
                vals['checklist_line_id'] = checklist.id
                vals['name'] = checklist.name
        try:
            with self.env.cr.savepoint():
                task = Task.create(vals)
        except IntegrityError:
            task = Task.search(domain, limit=1)
            if task:
                task._ensure_program_notify_documents()
            return task
        if handover_attachments:
            copies = self._duplicate_attachments_for_task(handover_attachments, task)
            task.handover_document_ids = [(6, 0, copies.ids)]
        task._ensure_program_notify_documents()
        return task

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
        checklist_users = program.checklist_line_ids.mapped('user_id')
        allowed = (
            user.has_group('ctkm_core.group_ctkm_user')
            or program.user_id == user
            or user in notified_users
            or user in checklist_users
        )
        if not allowed:
            raise UserError(_('Bạn không có quyền mở công việc của chương trình này.'))

        # Ưu tiên task checklist đã giao việc / mới nhất của user
        Task = self.sudo()
        task = Task.search([
            ('program_id', '=', program.id),
            ('user_id', '=', user.id),
            ('checklist_line_id', '!=', False),
            ('forwarded', '=', False),
        ], order='id desc', limit=1)
        if not task:
            task = Task.search([
                ('program_id', '=', program.id),
                ('user_id', '=', user.id),
            ], order='id desc', limit=1)
        if not task:
            checklist = program.checklist_line_ids.filtered(
                lambda l: l.user_id == user and l.notified
            ).sorted(lambda l: (l.sequence, l.id))[:1]
            if checklist:
                task = checklist._ctkm_ensure_task()
        if not task:
            line = program.notify_line_ids.filtered(
                lambda l: user in l.notify_employee_ids.mapped('user_id') and l.notified
            )[:1]
            if not line:
                line = program.notify_line_ids.filtered(
                    lambda l: user in l.notify_employee_ids.mapped('user_id')
                ).sorted(lambda l: (l.sequence, l.id))[:1]
            task = self._get_or_create_for_program_user(
                program, user, notify_line=line or None
            )
        if not task:
            raise UserError(_('Không tạo được công việc CTKM.'))

        task._ensure_program_notify_documents()
        url, app_menu_id = task._ctkm_task_form_url()
        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'self',
            'task_id': task.id,
            'menu_id': app_menu_id,
        }

    @api.model
    def action_open_for_manager_confirm(self, task_id):
        """Mở form công việc để quản lý xác nhận (từ tin OdooBot CTKM)."""
        task_id = int(task_id or 0)
        if not task_id:
            raise UserError(_('Thiếu mã công việc CTKM.'))
        task = self.sudo().browse(task_id)
        if not task.exists():
            raise UserError(_('Không tìm thấy công việc CTKM.'))
        user = self.env.user
        allowed = (
            task._user_can_confirm_as_manager(user)
            or task.user_id == user
            or user.has_group('ctkm_core.group_ctkm_manager')
        )
        if not allowed:
            raise UserError(_(
                'Bạn không có quyền mở công việc này để xác nhận.'
            ))
        task._ensure_program_notify_documents()
        url, app_menu_id = task._ctkm_task_form_url()
        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'self',
            'task_id': task.id,
            'menu_id': app_menu_id,
        }

    def action_open_tem_tag_import(self):
        self.ensure_one()
        if not self.program_id:
            raise UserError(_('Công việc chưa gắn chương trình khuyến mãi.'))
        if not self.is_tem_tag_import_task:
            raise UserError(_('Công việc này không phải bước import Tem/Tag.'))
        action = self.env.ref('ctkm_inventory.action_ctkm_inventory_import_wizard', raise_if_not_found=False)
        if not action:
            raise UserError(_('Module Kho Tem/Tag chưa cài đặt.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Import Tem/Tag'),
            'res_model': 'ctkm.inventory.import.wizard',
            'view_mode': 'form',
            'view_id': self.env.ref('ctkm_inventory.view_ctkm_inventory_import_wizard_form').id,
            'target': 'new',
            'context': {
                'default_program_id': self.program_id.id,
                'ctkm_import_task_id': self.id,
            },
        }
