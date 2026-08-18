# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

# Sai số cho phép khi so sánh số lượng (float).
QUANTITY_EPSILON = 0.000001


class CtkmTaskTemTagReplaceLine(models.Model):
    """Dòng tổng hợp Tem/Tag của một công việc (bảng "Chi tiết tem/tag").

    Mỗi dòng gom các bản ghi kho ``ctkm.inventory.tem.tag`` theo (Mã vật tư, Store)
    của chương trình khuyến mãi:

    * Bước 4 (Đổ BB thay tem/tag): xem toàn bộ cửa hàng (cột Store hiển thị).
    * Bước 12 (Thay tem Tag): chỉ cửa hàng của nhân viên nhận việc (ẩn cột Store),
      nhân viên nhập "Tổng SL đã thay" và số này được ghi ngược về kho Tem/Tag.

    Không tham chiếu trực tiếp model ctkm.inventory.tem.tag (tránh phụ thuộc
    load-order giữa module), mà đọc/ghi qua ``self.env`` lúc chạy.
    """

    _name = 'ctkm.task.tem.tag.replace.line'
    _description = 'Chi tiết tem/tag của công việc'
    _rec_name = 'material_code'
    _order = 'material_code, store, id'

    task_id = fields.Many2one(
        'ctkm.task',
        string='Công việc',
        required=True,
        ondelete='cascade',
        index=True,
    )
    material_code = fields.Char(string='Mã vật tư', readonly=True, index=True)
    store = fields.Char(string='Store', readonly=True)
    date = fields.Date(string='Ngày', readonly=True)
    total_quantity = fields.Float(string='Tổng SL', readonly=True)
    replaced_quantity = fields.Float(string='Tổng SL đã thay')
    remaining_quantity = fields.Float(
        string='Tổng SL chưa thay',
        compute='_compute_remaining_quantity',
        store=True,
        readonly=True,
    )
    is_tem = fields.Boolean(
        string='Tem',
        readonly=True,
        help='Mã vật tư lấy từ sheet TEM của file tổng.',
    )
    is_tag = fields.Boolean(
        string='Tag',
        readonly=True,
        help='Mã vật tư lấy từ sheet TAG của file tổng.',
    )

    @api.depends('total_quantity', 'replaced_quantity')
    def _compute_remaining_quantity(self):
        for line in self:
            remaining = (line.total_quantity or 0.0) - (line.replaced_quantity or 0.0)
            line.remaining_quantity = remaining if remaining > 0 else 0.0

    @api.constrains('replaced_quantity', 'total_quantity')
    def _check_replaced_quantity(self):
        for line in self:
            replaced = line.replaced_quantity or 0.0
            if replaced < -QUANTITY_EPSILON:
                raise ValidationError(_('Tổng SL đã thay không được là số âm.'))
            if replaced > (line.total_quantity or 0.0) + QUANTITY_EPSILON:
                raise ValidationError(_(
                    'Mã vật tư %(code)s: Tổng SL đã thay (%(replaced)s) không được '
                    'lớn hơn Tổng SL (%(total)s).'
                ) % {
                    'code': line.material_code or '',
                    'replaced': line.replaced_quantity,
                    'total': line.total_quantity,
                })

    def write(self, vals):
        # Sync nội bộ (dựng lại bảng từ kho Tem/Tag) không cần kiểm tra quyền
        # và cũng không ghi ngược về kho (tránh vòng lặp).
        internal = self.env.context.get('ctkm_tem_tag_line_sync')
        if 'replaced_quantity' in vals and not internal:
            self._check_can_update_replaced()
        res = super().write(vals)
        if 'replaced_quantity' in vals and not internal:
            self._distribute_replaced_quantity()
        return res

    def _check_can_update_replaced(self):
        """Chỉ người nhận việc bước 'Thay tem Tag' (hoặc CTKM Administrator) được nhập."""
        is_ctkm_manager = self.env.user.has_group('ctkm_core.group_ctkm_manager')
        for line in self:
            task = line.task_id
            if not task.is_tem_replace_task:
                raise UserError(_(
                    'Chỉ bước "Thay tem Tag" mới được cập nhật Tổng SL đã thay.'
                ))
            if not is_ctkm_manager and self.env.user not in task.user_ids:
                raise UserError(_(
                    'Chỉ người nhận việc mới được cập nhật Tổng SL đã thay.'
                ))

    def _tem_tag_domain(self):
        """Domain tìm các bản ghi kho Tem/Tag thuộc dòng tổng hợp này."""
        self.ensure_one()
        return [
            ('program_id', '=', self.task_id.program_id.id),
            ('material_code', '=', self.material_code or False),
            ('store', '=', self.store or False),
        ]

    def _distribute_replaced_quantity(self):
        """Phân bổ 'Tổng SL đã thay' về từng bản ghi kho Tem/Tag của dòng."""
        if 'ctkm.inventory.tem.tag' not in self.env:
            return
        tem_tag = self.env['ctkm.inventory.tem.tag'].sudo()
        for line in self:
            if not (line.task_id and line.task_id.program_id):
                continue
            rows = tem_tag.search(line._tem_tag_domain(), order='date, id')
            if not rows:
                continue
            remaining = max(line.replaced_quantity or 0.0, 0.0)
            for row in rows:
                quantity = row.quantity or 0.0
                taken = min(quantity, remaining) if quantity > 0 else 0.0
                remaining -= taken
                if abs((row.replaced_quantity or 0.0) - taken) > QUANTITY_EPSILON:
                    row.with_context(ctkm_tem_tag_line_sync=True).write({
                        'replaced_quantity': taken,
                    })
            if remaining > QUANTITY_EPSILON:
                # Dư (dữ liệu kho lệch so với bảng tổng hợp): dồn vào dòng cuối.
                last = rows[-1]
                last.with_context(ctkm_tem_tag_line_sync=True).write({
                    'replaced_quantity': (last.replaced_quantity or 0.0) + remaining,
                })
