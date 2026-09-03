# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.ctkm_core.models.ctkm_task import _ctkm_normalize_store_key

# Sai số cho phép khi so sánh số lượng (float).
QUANTITY_EPSILON = 0.000001


class CtkmTaskTemTagReplaceLine(models.Model):
    """Dòng tổng hợp Tem/Tag của một công việc (bảng "Chi tiết tem/tag").

    Mỗi dòng gom các bản ghi kho ``ctkm.inventory.tem.tag`` theo (Mã vật tư, Store)
    của chương trình khuyến mãi:

    * Bước 4 (Đổ BB thay tem/tag): xem toàn bộ cửa hàng (cột Store hiển thị).
    * Bước 6 (Lập BB thay tem): chỉ cửa hàng trong "Cửa hàng quản lí" của người
      nhận việc; cột "GHI CHÚ" (ctkm_name) hiển thị nội dung CTKM từ file import.
    * Bước 12 (Thay tem Tag): chỉ cửa hàng khớp mã bộ phận của người đang xem
      (đúng mã; gộp {store}_DDL + {store}_DNA vào mã ngắn khi hồ sơ có cả hai
      và không có mã trần). Nhân viên nhập "Tổng SL đã thay" và số này được
      ghi ngược về kho Tem/Tag.

    Không tham chiếu trực tiếp model ctkm.inventory.tem.tag (tránh phụ thuộc
    load-order giữa module), mà đọc/ghi qua ``self.env`` lúc chạy.
    """

    _name = 'ctkm.task.tem.tag.replace.line'
    _description = 'Chi tiết tem/tag của công việc'
    _rec_name = 'material_code'
    _order = 'store, material_code, id'

    task_id = fields.Many2one(
        'ctkm.task',
        string='Công việc',
        required=True,
        ondelete='cascade',
        index=True,
    )
    material_code = fields.Char(string='Mã vật tư', readonly=True, index=True)
    store = fields.Char(string='Store', readonly=True)
    store_key = fields.Char(
        string='Store Key',
        compute='_compute_store_key',
        store=True,
        index=True,
        readonly=True,
    )
    date = fields.Date(string='Ngày', readonly=True)
    ctkm_name = fields.Char(
        string='GHI CHÚ',
        readonly=True,
        help='Nội dung CTKM lấy từ cột "CTKM" của file Excel import. '
             'Chỉ hiển thị ở bước "Lập BB thay tem".',
    )
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
    received = fields.Boolean(
        string='Đã nhận',
        help='Đã nhận tem/tag mới tại cửa hàng này (bước Nhận tem tag mới).',
    )
    replaced_done = fields.Boolean(
        string='Đã thay',
        help='Đã thay xong tem/tag tại cửa hàng này (bước Thay tem Tag).',
    )

    @api.depends('store')
    def _compute_store_key(self):
        for line in self:
            line.store_key = _ctkm_normalize_store_key(line.store)

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
        if ('replaced_quantity' in vals or 'replaced_done' in vals) and not internal:
            self._check_can_update_replaced()
        if 'received' in vals and not internal:
            self._check_can_update_received()
        res = super().write(vals)
        if 'replaced_quantity' in vals and not internal:
            self._distribute_replaced_quantity()
        if not internal and (
            'replaced_quantity' in vals or 'replaced_done' in vals
        ):
            self.env['ctkm.task'].sudo()._ctkm_sync_price_lines_for_programs(
                self.mapped('task_id.program_id')
            )
        if not internal and (
            'received' in vals
            or 'replaced_done' in vals
            or 'replaced_quantity' in vals
        ):
            programs = self.mapped('task_id.program_id')
            if programs:
                programs.invalidate_recordset([
                    'stage_progress_json', 'checklist_current_stage_id',
                ])
        return res

    def action_toggle_received(self):
        """Tick Đã nhận: đánh dấu cửa hàng đã nhận tem/tag mới.

        Khi Cửa hàng trưởng tick Đã nhận cho TOÀN BỘ tem/tag của một cửa hàng,
        báo Quản lý cửa hàng (Người kiểm soát) của cửa hàng đó qua OdooBot CTKM.
        """
        self._check_can_update_received()
        for line in self:
            received = not line.received
            line.with_context(ctkm_tem_tag_line_sync=True).write({'received': received})
            task = line.task_id
            if received and task and task.is_tem_receive_task:
                store_lines = task.tem_tag_replace_ids.filtered(
                    lambda l: (l.store or '') == (line.store or '')
                )
                if store_lines and all(store_lines.mapped('received')):
                    task._ctkm_notify_store_received(line.store, store_lines)
        return False

    def _check_can_update_received(self):
        """Chỉ người nhận việc bước 'Nhận tem tag mới' / 'Thay tem Tag' được tick."""
        is_ctkm_manager = self.env.user.has_group('ctkm_core.group_ctkm_manager')
        for line in self:
            task = line.task_id
            if not (task.is_tem_receive_task or task.is_tem_replace_task):
                raise UserError(_(
                    'Chỉ bước "Nhận tem tag mới" / "Thay tem Tag" '
                    'mới được cập nhật Đã nhận.'
                ))
            if not is_ctkm_manager and self.env.user not in task.user_ids:
                raise UserError(_(
                    'Chỉ người nhận việc mới được cập nhật Đã nhận.'
                ))
            if not is_ctkm_manager and not task._ctkm_store_visible_to_user(line.store):
                raise UserError(_(
                    'Bạn chỉ được cập nhật tem/tag của cửa hàng mình.'
                ))
        return True

    def _check_can_update_replaced(self):
        """Chỉ người nhận việc bước 'Thay tem Tag' (hoặc CTKM Administrator) được nhập."""
        is_ctkm_manager = self.env.user.has_group('ctkm_core.group_ctkm_manager')
        for line in self:
            task = line.task_id
            if not task.is_tem_replace_task:
                raise UserError(_(
                    'Chỉ bước "Thay tem Tag" mới được cập nhật Tổng SL đã thay / Đã thay.'
                ))
            if not is_ctkm_manager and self.env.user not in task.user_ids:
                raise UserError(_(
                    'Chỉ người nhận việc mới được cập nhật Tổng SL đã thay.'
                ))
            if not is_ctkm_manager and not task._ctkm_store_visible_to_user(line.store):
                raise UserError(_(
                    'Bạn chỉ được cập nhật tem/tag của cửa hàng mình.'
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
