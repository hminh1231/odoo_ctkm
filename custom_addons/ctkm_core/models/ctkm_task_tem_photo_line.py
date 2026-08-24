# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import UserError


class CtkmTaskTemPhotoLine(models.Model):
    """Dòng kiểm tra hình ảnh tem/tag (bước "Kiểm tra hình ảnh tem tag").

    Mỗi dòng là một cặp (Cửa hàng, Mã vật tư) lấy từ kho Tem/Tag của chương trình
    (bước "Đổ BB thay tem/tag (file tổng)" — tất cả cửa hàng). Nhân viên tick
    "Xác nhận thay" khi đã kiểm tra xong hình ảnh tại cửa hàng đó.
    """

    _name = 'ctkm.task.tem.photo.line'
    _description = 'Kiểm tra hình ảnh tem/tag'
    _rec_name = 'material_code'
    _order = 'store, material_code, id'

    task_id = fields.Many2one(
        'ctkm.task',
        string='Công việc',
        required=True,
        ondelete='cascade',
        index=True,
    )
    store = fields.Char(string='Cửa hàng', readonly=True, index=True)
    store_key = fields.Char(string='Store Key', readonly=True, index=True)
    material_code = fields.Char(string='Mã vật tư', readonly=True, index=True)
    confirmed = fields.Boolean(
        string='Xác nhận thay',
        help='Đã kiểm tra hình ảnh tem/tag đã thay tại cửa hàng này.',
    )

    def write(self, vals):
        internal = self.env.context.get('ctkm_tem_photo_sync')
        if 'confirmed' in vals and not internal:
            self._check_can_update_confirmed()
        return super().write(vals)

    def _check_can_update_confirmed(self):
        is_manager = self.env.user.has_group('ctkm_core.group_ctkm_manager')
        for line in self:
            task = line.task_id
            if not task.is_tem_check_task:
                raise UserError(_(
                    'Chỉ bước "Kiểm tra hình ảnh tem tag" '
                    'mới được cập nhật Xác nhận thay.'
                ))
            if not is_manager and self.env.user not in task.user_ids:
                raise UserError(_(
                    'Chỉ người nhận việc mới được cập nhật Xác nhận thay.'
                ))
