# -*- coding: utf-8 -*-

from odoo import api, fields, models
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
        return domain

    def _get_default_notify_employees(self):
        self.ensure_one()
        if not self.store_code_id:
            return self.env['hr.employee']
        return self.env['hr.employee'].search(self._get_notify_employee_domain())

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

    @api.onchange('store_code_id')
    def _onchange_store_code_id(self):
        if self.store_code_id and self.store_code_id.mien:
            self.mien = self.store_code_id.mien
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
