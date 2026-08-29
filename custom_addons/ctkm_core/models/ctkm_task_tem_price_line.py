# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class CtkmTaskTemPriceLine(models.Model):
    """Dòng cửa hàng của bước 15 (Kế toán áp giá / báo cáo thay tem).

    Tên cửa hàng, SL tem, SL tag lấy từ bước 9 In tem, Tag.
    ASM xác nhận lấy từ cột Đã thay của bước Thay tem Tag.
    KT áp giá chỉ tick khi đã có đủ ASM xác nhận và KTDT xác nhận.
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
        string='ASM xác nhận',
        help='Lấy từ bước Thay tem Tag: mọi mã vật tư của cửa hàng đã tick Đã thay.',
    )
    not_replaced = fields.Boolean(
        string='KTDT xác nhận',
        help='Lấy từ bước Thay tem Tag: cửa hàng còn SL chưa thay.',
    )
    price_applied = fields.Boolean(
        string='KT áp giá',
        help='Chỉ tick được khi cửa hàng đã có đủ ASM xác nhận và KTDT xác nhận.',
    )
    replaced_user_id = fields.Many2one(
        'res.users',
        string='Người ASM xác nhận',
        readonly=True,
        index=True,
    )
    replaced_date = fields.Date(string='Ngày ASM xác nhận', readonly=True)
    not_replaced_user_id = fields.Many2one(
        'res.users',
        string='Người KTDT xác nhận',
        readonly=True,
        index=True,
    )
    not_replaced_date = fields.Date(string='Ngày KTDT xác nhận', readonly=True)
    price_applied_user_id = fields.Many2one(
        'res.users',
        string='Người KT áp giá',
        readonly=True,
        index=True,
    )
    price_applied_date = fields.Date(string='Ngày KT áp giá', readonly=True)
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

    _PREVIOUS_STEP_FIELDS = frozenset({
        'replaced', 'replaced_user_id', 'replaced_date',
        'not_replaced', 'not_replaced_user_id', 'not_replaced_date',
    })

    def write(self, vals):
        internal = self.env.context.get('ctkm_tem_tag_line_sync')
        if not internal:
            vals = {
                key: value for key, value in vals.items()
                if key not in self._PREVIOUS_STEP_FIELDS
            }
            if 'price_applied' in vals:
                self._check_can_edit_price_lines()
                if vals.get('price_applied'):
                    self._check_price_apply_ready()
                vals = self._vals_with_confirm_tracking(vals)
            elif not vals:
                return True
        return super().write(vals)

    def _vals_with_confirm_tracking(self, vals):
        """Tick KT áp giá: ghi người + ngày; bỏ tick thì xóa."""
        vals = dict(vals)
        if 'price_applied' not in vals:
            return vals
        today = fields.Date.context_today(self)
        uid = self.env.uid
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

    def _check_price_apply_ready(self):
        not_ready = self.filtered(
            lambda line: not (line.replaced and line.not_replaced)
        )
        if not not_ready:
            return
        stores = ', '.join(
            line.store or line.store_code or line.store_key or ''
            for line in not_ready
        )
        raise UserError(_(
            'Chưa đủ điều kiện để áp giá.\n'
            'Cần có cả ASM xác nhận và KTDT xác nhận.\n'
            'Cửa hàng chưa đủ điều kiện: %s'
        ) % stores)

    def _check_can_edit_price_lines(self):
        is_ctkm_manager = self.env.user.has_group('ctkm_core.group_ctkm_manager')
        for line in self:
            task = line.task_id
            if task and not task.is_tem_price_task:
                raise UserError(_(
                    'Chỉ bước "Kế toán áp giá" mới được cập nhật KT áp giá.'
                ))
            if task and not is_ctkm_manager and self.env.user not in task.user_ids:
                raise UserError(_(
                    'Chỉ người nhận việc mới được cập nhật KT áp giá.'
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
