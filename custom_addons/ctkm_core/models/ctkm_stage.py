# -*- coding: utf-8 -*-

from odoo import api, fields, models


class CtkmStage(models.Model):
    _name = 'ctkm.stage'
    _description = 'Giai đoạn chương trình khuyến mãi'
    _order = 'sequence, id'

    name = fields.Char(string='Tên giai đoạn', required=True, translate=True)
    sequence = fields.Integer(string='Thứ tự', default=10)
    description = fields.Text(string='Mô tả')
    user_id = fields.Many2one(
        'res.users',
        string='Phụ trách',
        domain="[('share', '=', False)]",
    )
    need_manager_confirm = fields.Boolean(
        string='Cần quản lý xác nhận',
        default=True,
    )
    pipe_end = fields.Boolean(string='Kết thúc')
    fold = fields.Boolean(string='Gộp')

    @api.model_create_multi
    def create(self, vals_list):
        recs = super().create(vals_list)
        self.env['ctkm.program'].sudo().search([])._ctkm_sync_checklist_from_stages()
        return recs

    def write(self, vals):
        res = super().write(vals)
        if any(f in vals for f in ('name', 'sequence', 'user_id', 'need_manager_confirm')):
            self.env['ctkm.program'].sudo().search([])._ctkm_sync_checklist_from_stages()
        return res

    def unlink(self):
        programs = self.env['ctkm.program'].sudo().search([])
        res = super().unlink()
        programs._ctkm_sync_checklist_from_stages()
        return res
