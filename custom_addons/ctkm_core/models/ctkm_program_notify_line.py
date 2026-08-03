# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.addons.hr_job_title_vn.models.hr_version import JOB_TITLE_SELECTION
from odoo.exceptions import ValidationError

MIEN_SELECTION = [
    ('Bắc', 'Bắc'),
    ('Nam', 'Nam'),
    ('ĐTT', 'ĐTT'),
    ('VP', 'VP'),
]


class CtkmProgramNotifyLine(models.Model):
    _name = 'ctkm.program.notify.line'
    _description = 'Dòng phạm vi thông báo CTKM'
    _order = 'sequence, id'

    program_id = fields.Many2one(
        'ctkm.program', string='Chương trình', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(string='STT', default=10)
    stt = fields.Integer(
        string='Số thứ tự',
        compute='_compute_stt',
    )
    mien = fields.Selection(
        selection=MIEN_SELECTION,
        string='Miền',
    )
    store_code_id = fields.Many2one(
        'hr.store.code',
        string='Mã cửa hàng',
        domain="['|', ('mien', '=', False), ('mien', '=', mien)]",
    )
    job_title = fields.Selection(
        selection=JOB_TITLE_SELECTION,
        string='Chức vụ',
    )
    job_id = fields.Many2one(
        'hr.job',
        string='Job Position',
    )
    store_code = fields.Char(
        string='Mã CH',
        related='store_code_id.code',
        readonly=True,
    )
    notify_employee_ids = fields.Many2many(
        'hr.employee',
        'ctkm_program_notify_line_employee_rel',
        'line_id',
        'employee_id',
        string='Người nhận thông báo',
    )
    notified = fields.Boolean(
        string='Đã gửi tin',
        default=False,
        copy=False,
        help='Đã gửi OdooBot CTKM cho bước phạm vi này.',
    )
    notified_date = fields.Datetime(
        string='Ngày gửi tin',
        copy=False,
        readonly=True,
    )
    step_label = fields.Char(
        string='Nhãn bước',
        compute='_compute_step_label',
    )
    notify_receipt_date = fields.Date(
        string='Ngày nhận thông báo',
        related='program_id.notify_receipt_date',
        readonly=True,
    )
    notify_file_display = fields.Char(
        string='File thông báo',
        related='program_id.notify_file_display',
        readonly=True,
    )
    responsible_id = fields.Many2one(
        'res.users',
        string='Người phụ trách',
        related='program_id.user_id',
        readonly=True,
    )
    hour_quota = fields.Char(
        string='Định biên giờ',
        related='program_id.hour_quota',
        readonly=True,
    )
    notify_code = fields.Char(
        string='Mã số thông báo',
        related='program_id.notify_code',
        readonly=True,
        store=True,
        index=True,
    )
    scope_display = fields.Char(
        string='Phạm vi áp dụng',
        compute='_compute_scope_display',
    )

    @api.depends('store_code', 'store_code_id', 'mien', 'job_title', 'job_id')
    def _compute_scope_display(self):
        job_title_labels = dict(JOB_TITLE_SELECTION)
        for line in self:
            parts = []
            if line.store_code:
                parts.append(line.store_code)
            elif line.store_code_id:
                parts.append(line.store_code_id.display_name)
            if line.mien:
                parts.append(line.mien)
            if line.job_title:
                parts.append(job_title_labels.get(line.job_title, line.job_title))
            if line.job_id:
                parts.append(line.job_id.name)
            line.scope_display = ' / '.join(parts) if parts else ''

    @api.depends('job_title', 'job_id', 'stt')
    def _compute_step_label(self):
        job_title_labels = dict(JOB_TITLE_SELECTION)
        for line in self:
            label = (
                line.job_id.name
                or job_title_labels.get(line.job_title, line.job_title)
                or _('Bước %s') % (line.stt or line.sequence or '')
            )
            line.step_label = label

    def _get_recipient_users(self):
        """User nội bộ hợp lệ của dòng phạm vi."""
        self.ensure_one()
        employees = self.notify_employee_ids
        users = employees.mapped('user_id').filtered(
            lambda user: user and user.active and not user.share and user.partner_id
        )
        skipped = employees.filtered(
            lambda employee: not employee.user_id
            or not employee.user_id.active
            or employee.user_id.share
            or not employee.user_id.partner_id
        )
        return users, skipped

    def _get_notify_employee_domain(self):
        self.ensure_one()
        domain = [('active', '=', True)]
        if self.mien:
            domain.append(('mien', '=', self.mien))
        if self.store_code_id:
            store_id = self.store_code_id.store_id.id or self.store_code_id.id
            domain = [
                *domain,
                '|',
                ('ma_bo_phan_id', '=', self.store_code_id.id),
                ('store_id', '=', store_id),
            ]
        if self.job_title:
            domain.append(('job_title', '=', self.job_title))
        if self.job_id:
            domain.append(('job_id', '=', self.job_id.id))
        return domain

    def _get_default_notify_employees(self):
        self.ensure_one()
        if not self.store_code_id and not self.job_title and not self.job_id:
            return self.env['hr.employee']
        return self.env['hr.employee'].search(self._get_notify_employee_domain())

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            program_id = vals.get('program_id')
            if program_id and not vals.get('sequence'):
                existing = self.search([('program_id', '=', program_id)])
                vals['sequence'] = (max(existing.mapped('sequence') or [0]) + 10)
            elif program_id and vals.get('sequence') == 10:
                # Nhiều dòng mặc định sequence=10 → tăng dần theo số dòng hiện có
                existing = self.search([('program_id', '=', program_id)])
                if existing:
                    vals['sequence'] = max(existing.mapped('sequence') or [0]) + 10
        return super().create(vals_list)

    @api.depends('program_id.notify_line_ids.sequence', 'sequence')
    def _compute_stt(self):
        for program in self.mapped('program_id'):
            for index, line in enumerate(program.notify_line_ids.sorted('sequence'), start=1):
                line.stt = index
        for line in self.filtered(lambda line: not line.program_id):
            line.stt = 0

    @api.onchange('mien')
    def _onchange_mien(self):
        if self.store_code_id and self.store_code_id.mien and self.store_code_id.mien != self.mien:
            self.store_code_id = False
        if self.mien:
            self.notify_employee_ids = self.notify_employee_ids.filtered(
                lambda employee: employee.mien == self.mien
            )
        else:
            self.notify_employee_ids = False
        if self.store_code_id or self.job_title or self.job_id:
            self.notify_employee_ids = self._get_default_notify_employees()

    @api.onchange('store_code_id')
    def _onchange_store_code_id(self):
        if self.store_code_id and self.store_code_id.mien:
            self.mien = self.store_code_id.mien
        self.notify_employee_ids = self._get_default_notify_employees()

    @api.onchange('job_title')
    def _onchange_job_title(self):
        self.notify_employee_ids = self._get_default_notify_employees()

    @api.onchange('job_id')
    def _onchange_job_id(self):
        self.notify_employee_ids = self._get_default_notify_employees()

    @api.onchange('notify_employee_ids')
    def _onchange_notify_employee_ids(self):
        if self.mien:
            self.notify_employee_ids = self.notify_employee_ids.filtered(
                lambda employee: employee.mien == self.mien
            )

    @api.constrains('mien', 'notify_employee_ids')
    def _check_notify_employee_mien(self):
        for line in self:
            if not line.mien:
                continue
            invalid = line.notify_employee_ids.filtered(lambda employee: employee.mien != line.mien)
            if invalid:
                raise ValidationError(
                    'Nhân viên %s không thuộc miền %s.'
                    % (', '.join(invalid.mapped('name')), line.mien)
                )

    @api.constrains('job_title', 'notify_employee_ids')
    def _check_notify_employee_job_title(self):
        job_title_labels = dict(JOB_TITLE_SELECTION)
        for line in self:
            if not line.job_title:
                continue
            invalid = line.notify_employee_ids.filtered(
                lambda employee: employee.job_title != line.job_title
            )
            if invalid:
                raise ValidationError(
                    'Nhân viên %s không có chức vụ %s.'
                    % (
                        ', '.join(invalid.mapped('name')),
                        job_title_labels.get(line.job_title, line.job_title),
                    )
                )

    @api.constrains('job_id', 'notify_employee_ids')
    def _check_notify_employee_job(self):
        for line in self:
            if not line.job_id:
                continue
            invalid = line.notify_employee_ids.filtered(
                lambda employee: employee.job_id != line.job_id
            )
            if invalid:
                raise ValidationError(
                    'Nhân viên %s không có Job Position %s.'
                    % (', '.join(invalid.mapped('name')), line.job_id.name)
                )
