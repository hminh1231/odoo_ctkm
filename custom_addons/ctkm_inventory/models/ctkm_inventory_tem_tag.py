# -*- coding: utf-8 -*-

from odoo import api, fields, models


def _normalize_store_code(value):
    value = ' '.join((value or '').strip().split())
    return value.upper() if value else False


class CtkmInventoryTemTag(models.Model):
    _name = 'ctkm.inventory.tem.tag'
    _description = 'Kho Tem/Tag CTKM'
    _order = 'date desc, program_id, material_code, store'

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
    tem_tag = fields.Char(string='Tem/tag', index=True)
    store = fields.Char(string='Store', index=True)
    store_key = fields.Char(
        string='Store Key',
        compute='_compute_store_key',
        store=True,
        index=True,
        readonly=True,
    )
    quantity = fields.Float(string='Quantity', default=0.0)
    import_filename = fields.Char(string='File nhập', readonly=True)
    replaced = fields.Boolean(
        string='Đã thay',
        default=False,
        help='Nhân viên đánh dấu đã thay tem/tag thực tế tại cửa hàng (bước 12).',
    )

    @api.depends('store')
    def _compute_store_key(self):
        for record in self:
            record.store_key = _normalize_store_code(record.store)

    @api.model
    def current_user_store_keys(self):
        user = self.env.user.sudo()
        codes = []
        if 'employee_ma_bo_phan_id' in user._fields and user.employee_ma_bo_phan_id:
            codes.append(user.employee_ma_bo_phan_id.code)
        if 'employee_store_id' in user._fields and user.employee_store_id:
            codes.append(user.employee_store_id.code)
        if 'employee_id' in user._fields and user.employee_id:
            employee = user.employee_id.sudo()
            if 'ma_bo_phan' in employee._fields:
                codes.append(employee.ma_bo_phan)
            if 'ma_bo_phan_id' in employee._fields and employee.ma_bo_phan_id:
                codes.append(employee.ma_bo_phan_id.code)
            if 'store_id' in employee._fields and employee.store_id:
                codes.append(employee.store_id.code)
                codes.append(employee.store_id.name)
            if 'current_version_id' in employee._fields and employee.current_version_id:
                version = employee.current_version_id
                if 'store_id' in version._fields and version.store_id:
                    codes.append(version.store_id.code)
                    codes.append(version.store_id.name)

        keys = []
        for code in codes:
            key = _normalize_store_code(code)
            if key and key not in keys:
                keys.append(key)
        return keys
