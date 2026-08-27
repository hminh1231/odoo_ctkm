# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class CtkmTaskTemPriceLine(models.Model):
    """Dòng cửa hàng của bước 15 (Kế toán áp giá / báo cáo thay tem).

    Tên cửa hàng, SL tem, SL tag lấy từ bước 9 In tem, Tag.
    Kế toán tick xác nhận đã thay / chưa thay tem-tag và đã áp giá.
    """

    _name = 'ctkm.task.tem.price.line'
    _description = 'Cửa hàng kế toán áp giá'
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
        store=True,
    )
    print_line_id = fields.Many2one(
        'ctkm.task.tem.print.line',
        string='Dòng in tem/tag',
        ondelete='set null',
        index=True,
        help='Dòng bước 9 tương ứng; SL tem/tag lấy từ đây.',
    )
    tem_quantity = fields.Float(
        string='SL tem',
        compute='_compute_quantities',
        store=True,
        help='Tổng SL tem lấy từ bước In tem, Tag.',
    )
    tag_quantity = fields.Float(
        string='SL tag',
        compute='_compute_quantities',
        store=True,
        help='Tổng SL tag lấy từ bước In tem, Tag.',
    )
    replaced = fields.Boolean(
        string='Xác nhận thay tem/tag',
        help='Kế toán xác nhận cửa hàng đã thay tem/tag.',
    )
    not_replaced = fields.Boolean(
        string='Xác nhận chưa thay tem/tag',
        help='Kế toán xác nhận cửa hàng chưa thay tem/tag.',
    )
    price_applied = fields.Boolean(
        string='Xác nhận đã áp giá',
        help='Kế toán xác nhận đã áp giá CTKM trên PM Link Q cho cửa hàng này.',
    )
    replaced_user_id = fields.Many2one(
        'res.users',
        string='Người xác nhận thay tem',
        readonly=True,
        index=True,
    )
    replaced_date = fields.Date(string='Ngày xác nhận thay tem', readonly=True)
    not_replaced_user_id = fields.Many2one(
        'res.users',
        string='Người xác nhận chưa thay',
        readonly=True,
        index=True,
    )
    not_replaced_date = fields.Date(string='Ngày xác nhận chưa thay', readonly=True)
    price_applied_user_id = fields.Many2one(
        'res.users',
        string='Người xác nhận áp giá',
        readonly=True,
        index=True,
    )
    price_applied_date = fields.Date(string='Ngày xác nhận áp giá', readonly=True)
    program_id = fields.Many2one(
        related='task_id.program_id',
        string='Chương trình KM',
        store=True,
        index=True,
    )
    notify_code = fields.Char(
        related='program_id.notify_code',
        string='Số TB',
        store=True,
        index=True,
    )
    name = fields.Char(
        related='program_id.name',
        string='Tên CTKM',
        store=True,
    )

    _task_store_uniq = models.Constraint(
        'UNIQUE(task_id, store_key)',
        'Mỗi cửa hàng chỉ có một dòng kế toán áp giá trên công việc.',
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
            self._check_can_edit_price_lines()
            vals = self._vals_with_confirm_tracking(vals)
        return super().write(vals)

    def _vals_with_confirm_tracking(self, vals):
        """Tick xác nhận: ghi người + ngày; bỏ tick thì xóa. Thay / chưa thay loại trừ nhau."""
        vals = dict(vals)
        today = fields.Date.context_today(self)
        uid = self.env.uid
        if vals.get('replaced') and 'not_replaced' not in vals:
            vals['not_replaced'] = False
        elif vals.get('not_replaced') and 'replaced' not in vals:
            vals['replaced'] = False
        if 'replaced' in vals:
            if vals.get('replaced'):
                vals.setdefault('replaced_user_id', uid)
                vals.setdefault('replaced_date', today)
                vals['not_replaced_user_id'] = False
                vals['not_replaced_date'] = False
            else:
                vals.setdefault('replaced_user_id', False)
                vals.setdefault('replaced_date', False)
        if 'not_replaced' in vals:
            if vals.get('not_replaced'):
                vals.setdefault('not_replaced_user_id', uid)
                vals.setdefault('not_replaced_date', today)
                vals['replaced_user_id'] = False
                vals['replaced_date'] = False
            else:
                vals.setdefault('not_replaced_user_id', False)
                vals.setdefault('not_replaced_date', False)
        if 'price_applied' in vals:
            if vals.get('price_applied'):
                vals.setdefault('price_applied_user_id', uid)
                vals.setdefault('price_applied_date', today)
            else:
                vals.setdefault('price_applied_user_id', False)
                vals.setdefault('price_applied_date', False)
        return vals

    def unlink(self):
        if not self.env.context.get('ctkm_tem_tag_line_sync'):
            self._check_can_edit_price_lines()
        return super().unlink()

    def _check_can_edit_price_lines(self):
        is_ctkm_manager = self.env.user.has_group('ctkm_core.group_ctkm_manager')
        for line in self:
            task = line.task_id
            if task and not task.is_tem_price_task:
                raise UserError(_(
                    'Chỉ bước "Kế toán áp giá" mới được cập nhật xác nhận '
                    'thay tem/tag và áp giá.'
                ))
            if task and not is_ctkm_manager and self.env.user not in task.user_ids:
                raise UserError(_(
                    'Chỉ người nhận việc mới được cập nhật xác nhận '
                    'thay tem/tag và áp giá.'
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
                    'Cửa hàng "%s" đã có trong bảng kế toán áp giá.'
                ) % (line.store or line.store_code or line.store_key))
