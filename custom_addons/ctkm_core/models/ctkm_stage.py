# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class CtkmStage(models.Model):
    _name = 'ctkm.stage'
    _description = 'Giai đoạn chương trình khuyến mãi'
    _order = 'sequence, id'

    name = fields.Char(string='Tên giai đoạn', required=True, translate=True)
    sequence = fields.Integer(string='Thứ tự', default=10)
    description = fields.Text(string='Mô tả')
    user_ids = fields.Many2many(
        'res.users',
        'ctkm_stage_user_rel',
        'stage_id',
        'user_id',
        string='Phụ trách',
        domain="[('share', '=', False)]",
    )
    need_manager_confirm = fields.Boolean(
        string='Cần quản lý xác nhận',
        default=True,
    )
    verifier_id = fields.Many2one(
        'hr.employee',
        string='Người kiểm soát',
        domain="[('user_id.share', '=', False)]",
        help='Nhân viên xác nhận bước này. Khi đặt, bước dùng người này kiểm soát '
             'thay vì quản lý theo organization chart.',
    )
    pipe_end = fields.Boolean(string='Kết thúc')
    fold = fields.Boolean(string='Gộp')

    @api.constrains('verifier_id', 'need_manager_confirm')
    def _check_verifier_needs_confirm(self):
        for stage in self:
            if stage.verifier_id and not stage.need_manager_confirm:
                raise ValidationError(_(
                    'Chỉ được chọn "Người kiểm soát" khi bật "Cần quản lý xác nhận".'
                ))

    def write(self, vals):
        res = super().write(vals)
        if any(
            f in vals
            for f in ('name', 'sequence', 'user_ids', 'need_manager_confirm', 'verifier_id')
        ):
            self.env['ctkm.program'].sudo().search([])._ctkm_sync_checklist_from_stages()
        return res

    def unlink(self):
        programs = self.env['ctkm.program'].sudo().search([])
        res = super().unlink()
        programs._ctkm_sync_checklist_from_stages()
        return res
