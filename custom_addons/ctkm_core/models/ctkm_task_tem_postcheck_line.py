# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class CtkmTaskTemPostcheckLine(models.Model):
    """Dòng cửa hàng của bước 16 (Hậu kiểm CTKM).

    Tên cửa hàng, SL tem, SL tag lấy từ bước 9 In tem, Tag.
    Giám sát tick Đã thay đủ tem / Đã thay đủ tag hoặc Chưa thay/thay thiếu.
    """

    _name = 'ctkm.task.tem.postcheck.line'
    _description = 'Cửa hàng hậu kiểm thay tem'
    _rec_name = 'store'
    _order = 'sequence, store, id'

    task_id = fields.Many2one(
        'ctkm.task',
        string='Công việc',
        required=True,
        ondelete='cascade',
        index=True,
    )
    sequence = fields.Integer(string='STT', default=1, readonly=True)
    store_id = fields.Many2one(
        'hr.store',
        string='Tên cửa hàng',
        ondelete='restrict',
        index=True,
        help='Cửa hàng lấy từ Nhân viên → Cấu hình → Cửa hàng.',
    )
    store = fields.Char(string='Tên cửa hàng (kho)', index=True)
    store_key = fields.Char(string='Store Key', index=True)
    store_code = fields.Char(
        string='Mã cửa hàng',
        compute='_compute_store_code',
    )
    print_line_id = fields.Many2one(
        'ctkm.task.tem.print.line',
        string='Dòng in tem/tag',
        ondelete='set null',
        index=True,
        help='Dòng bước 9 tương ứng; SL tem/tag lấy từ đây.',
    )
    tem_quantity = fields.Float(
        string='Số lượng tem',
        compute='_compute_quantities',
        store=True,
        help='Luôn lấy SL tem từ bước In tem, Tag.',
    )
    tag_quantity = fields.Float(
        string='Số lượng tag',
        compute='_compute_quantities',
        store=True,
        help='Luôn lấy SL tag từ bước In tem, Tag.',
    )
    replaced = fields.Boolean(
        string='Đã thay đủ tem',
        help='Giám sát xác nhận cửa hàng đã thay đủ tem.',
    )
    tag_replaced = fields.Boolean(
        string='Đã thay đủ tag',
        help='Giám sát xác nhận cửa hàng đã thay đủ tag.',
    )
    not_replaced = fields.Boolean(
        string='Chưa thay/thay thiếu',
        help='Giám sát xác nhận cửa hàng chưa thay hoặc thay thiếu tem/tag.',
    )

    _task_store_uniq = models.Constraint(
        'UNIQUE(task_id, store_key)',
        'Mỗi cửa hàng chỉ có một dòng hậu kiểm trên công việc.',
    )

    @api.depends('store_id.code', 'store_key')
    def _compute_store_code(self):
        for line in self:
            line.store_code = line.store_id.code or line.store_key or False

    @api.depends(
        'print_line_id.tem_quantity',
        'print_line_id.tag_quantity',
    )
    def _compute_quantities(self):
        for line in self:
            source = line.print_line_id
            line.tem_quantity = (source.tem_quantity or 0.0) if source else 0.0
            line.tag_quantity = (source.tag_quantity or 0.0) if source else 0.0

    def write(self, vals):
        internal = self.env.context.get('ctkm_tem_tag_line_sync')
        if not internal:
            self._check_can_edit_postcheck_lines()
        return super().write(vals)

    def unlink(self):
        if not self.env.context.get('ctkm_tem_tag_line_sync'):
            self._check_can_edit_postcheck_lines()
        return super().unlink()

    def _check_can_edit_postcheck_lines(self):
        is_ctkm_manager = self.env.user.has_group('ctkm_core.group_ctkm_manager')
        for line in self:
            task = line.task_id
            if task and not task.is_tem_postcheck_task:
                raise UserError(_(
                    'Chỉ bước "Hậu kiểm CTKM" mới được cập nhật xác nhận thay tem.'
                ))
            if task and not is_ctkm_manager and self.env.user not in task.user_ids:
                raise UserError(_(
                    'Chỉ người nhận việc mới được cập nhật xác nhận thay tem.'
                ))

    @api.constrains('task_id', 'store_key')
    def _check_unique_store_key(self):
        for line in self:
            if not line.store_key or not line.task_id:
                continue
            duplicate = self.search([
                ('task_id', '=', line.task_id.id),
                ('store_key', '=', line.store_key),
                ('id', '!=', line.id),
            ], limit=1)
            if duplicate:
                raise ValidationError(_(
                    'Cửa hàng "%s" đã có trong bảng hậu kiểm.'
                ) % (line.store or line.store_code or line.store_key))
