# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CtkmTaskTemPhotoLine(models.Model):
    """Dòng tem/tag theo cửa hàng cho bước 13 (chụp) và bước 14 (kiểm tra ảnh).

    Mỗi dòng là một cặp (Cửa hàng, Mã vật tư) lấy từ kho Tem/Tag của chương trình
    (bước "Đổ BB thay tem/tag (file tổng)" — tất cả cửa hàng).

    * Bước 13: tick "Đã chụp" khi đã chụp team / từng tem-tag của mã đó.
    * Bước 14: tick "Xác nhận thay" khi đã kiểm tra xong hình ảnh.
    """

    _name = 'ctkm.task.tem.photo.line'
    _description = 'Ảnh / kiểm tra hình ảnh tem/tag'
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
    total_quantity = fields.Float(
        string='Số lượng',
        readonly=True,
        help='SL tem/tag của mã này tại cửa hàng, lấy từ file bước 4.',
    )
    photographed = fields.Boolean(
        string='Đã chụp',
        help='Đã chụp team / từng tem-tag của mã vật tư tại cửa hàng này (bước 13).',
    )
    confirmed = fields.Boolean(
        string='Xác nhận thay',
        help='Đã kiểm tra hình ảnh tem/tag đã thay tại cửa hàng này.',
    )

    def write(self, vals):
        internal = self.env.context.get('ctkm_tem_photo_sync')
        if 'confirmed' in vals and not internal:
            self._check_can_update_confirmed()
        if 'photographed' in vals and not internal:
            self._check_can_update_photographed()
        res = super().write(vals)
        if 'confirmed' in vals and not internal:
            self.env['ctkm.task'].sudo()._ctkm_sync_price_lines_for_programs(
                self.mapped('task_id.program_id')
            )
        if not internal and (
            'confirmed' in vals or 'photographed' in vals
        ):
            self._ctkm_invalidate_program_stage_progress()
        return res

    def _ctkm_invalidate_program_stage_progress(self):
        programs = self.mapped('task_id.program_id')
        if programs:
            programs.invalidate_recordset([
                'stage_progress_json', 'checklist_current_stage_id',
            ])

    def _check_can_update_photographed(self):
        is_manager = self.env.user.has_group('ctkm_core.group_ctkm_manager')
        for line in self:
            task = line.task_id
            if not task.is_tem_photo_task:
                raise UserError(_(
                    'Chỉ bước "Chụp team gửi lên group / chụp từng con tem" '
                    'mới được cập nhật Đã chụp.'
                ))
            if not is_manager and self.env.user not in task.user_ids:
                raise UserError(_(
                    'Chỉ người nhận việc mới được cập nhật Đã chụp.'
                ))
            if (
                not is_manager
                and not task._ctkm_store_visible_to_user(line.store)
            ):
                raise UserError(_(
                    'Bạn chỉ được đánh dấu đã chụp tem/tag của cửa hàng mình.'
                ))

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
            if (
                not is_manager
                and task.is_tem_check_task
                and not task._ctkm_store_visible_to_user(line.store)
            ):
                raise UserError(_(
                    'Bạn chỉ được xác nhận hình ảnh tem/tag của cửa hàng mình.'
                ))
