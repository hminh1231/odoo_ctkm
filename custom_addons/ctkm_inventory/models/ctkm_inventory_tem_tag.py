# -*- coding: utf-8 -*-

from odoo import fields, models


class CtkmInventoryTemTag(models.Model):
    _name = 'ctkm.inventory.tem.tag'
    _description = 'Kho Tem/Tag CTKM'
    _order = 'date desc, program_id, material_code'

    date = fields.Date(string='Date', required=True, index=True)
    material_code = fields.Char(string='Mã vật tư', required=True, index=True)
    promo_price = fields.Float(string='Giá KM')
    program_id = fields.Many2one(
        'ctkm.program',
        string='CTKM',
        required=True,
        ondelete='cascade',
        index=True,
    )
    imported_ctkm_name = fields.Char(
        string='CTKM trên file',
        help='Tên CTKM đọc từ file Excel, dùng để đối chiếu khi tên trên file khác bản ghi CTKM.',
    )
    tem_tag = fields.Char(string='Tem/tag', index=True)
    quantity = fields.Float(string='Quantity', default=0.0)
    import_filename = fields.Char(string='File nhập', readonly=True)
