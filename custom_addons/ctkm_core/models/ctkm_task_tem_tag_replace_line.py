# -*- coding: utf-8 -*-

from odoo import api, fields, models


class CtkmTaskTemTagReplaceLine(models.TransientModel):
    """Dòng tạm (transient) hiển thị Mã vật tư của CTKM thuộc cửa hàng nhân viên,
    dùng để đánh dấu 'Đã thay' ở bước 12. Không tham chiếu trực tiếp model
    ctkm.inventory.tem.tag (tránh phụ thuộc load-order giữa module), mà ghi trạng
    thái 'Đã thay' về bản ghi ctkm.inventory.tem.tag thực tế qua search/write."""

    _name = 'ctkm.task.tem.tag.replace.line'
    _description = 'Dòng đánh dấu đã thay tem/tag'
    _rec_name = 'material_code'

    task_id = fields.Many2one('ctkm.task', required=True, ondelete='cascade')
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
            task = line.task_id
            if not (task and task.program_id):
                continue
            tem_tag = self.env['ctkm.inventory.tem.tag']
            store_keys = tem_tag.current_user_store_keys()
            domain = [
                ('program_id', '=', task.program_id.id),
                ('material_code', '=', line.material_code),
            ]
            if line.store:
                domain = domain + [('store', '=', line.store)]
            if store_keys:
                domain = domain + [('store_key', 'in', store_keys)]
            tem_tag.search(domain).sudo().write({'replaced': line.replaced})
