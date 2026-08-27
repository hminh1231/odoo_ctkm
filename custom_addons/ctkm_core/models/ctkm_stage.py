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
    verifier_ids = fields.Many2many(
        'hr.employee',
        'ctkm_stage_verifier_rel',
        'stage_id',
        'employee_id',
        string='Người kiểm soát',
        domain="[('user_id.share', '=', False)]",
        help='Nhân viên xác nhận bước này. Khi đặt, bước dùng những người này '
             'kiểm soát thay vì quản lý theo organization chart.',
    )
    pipe_end = fields.Boolean(string='Kết thúc')
    fold = fields.Boolean(string='Gộp')
    notify_user_ids = fields.Many2many(
        'hr.employee',
        'ctkm_stage_notify_employee_rel',
        'stage_id',
        'employee_id',
        string='Người thông báo',
        domain="[('active', '=', True)]",
        help='Nhân viên nhận thông báo (qua OdooBot CTKM) khi bước này hoàn thành.',
    )
    notify_content = fields.Html(
        string='Nội dung thông báo',
        sanitize=True,
        help='Nội dung gửi qua OdooBot CTKM khi bước này hoàn thành. '
             'Hỗ trợ định dạng HTML của Odoo (in đậm, danh sách, xuống dòng...).',
    )

    @api.constrains('verifier_ids', 'need_manager_confirm')
    def _check_verifier_needs_confirm(self):
        for stage in self:
            if stage.verifier_ids and not stage.need_manager_confirm:
                raise ValidationError(_(
                    'Chỉ được chọn "Người kiểm soát" khi bật "Cần quản lý xác nhận".'
                ))

    def write(self, vals):
        res = super().write(vals)
        if any(
            f in vals
            for f in ('name', 'sequence', 'user_ids', 'need_manager_confirm', 'verifier_ids')
        ):
            self.env['ctkm.program'].sudo().search([])._ctkm_sync_checklist_from_stages()
        return res

    def unlink(self):
        programs = self.env['ctkm.program'].sudo().search([])
        res = super().unlink()
        programs._ctkm_sync_checklist_from_stages()
        return res
