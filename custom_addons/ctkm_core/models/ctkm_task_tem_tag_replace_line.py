# -*- coding: utf-8 -*-

from odoo import api, fields, models


class CtkmTaskTemTagReplaceLine(models.TransientModel):
    """Dòng tạm (transient) hiển thị Mã vật tư của CTKM thuộc cửa hàng nhân viên,
    dùng để đánh dấu 'Đã thay' ở bước 12. Trạng thái 'Đã thay' được ghi về bản ghi
    ctkm.inventory.tem.tag thực tế (field replaced)."""

    _name = 'ctkm.task.tem.tag.replace.line'
    _description = 'Dòng đánh dấu đã thay tem/tag'
    _rec_name = 'material_code'

    task_id = fields.Many2one('ctkm.task', required=True, ondelete='cascade')
    tem_tag_id = fields.Many2one(
        'ctkm.inventory.tem.tag', string='Tem/Tag', required=True, ondelete='cascade'
    )
    material_code = fields.Char(string='Mã vật tư', readonly=True)
    store = fields.Char(string='Store', readonly=True)
    date = fields.Date(string='Date', readonly=True)
    replaced = fields.Boolean(string='Đã thay', default=False)

    @api.model
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_replaced_to_tem_tag()
        return records

    def write(self, vals):
        res = super().write(vals)
        if 'replaced' in vals:
            self._sync_replaced_to_tem_tag()
        return res

    def _sync_replaced_to_tem_tag(self):
        for line in self:
            if line.tem_tag_id:
                line.tem_tag_id.sudo().write({'replaced': line.replaced})
