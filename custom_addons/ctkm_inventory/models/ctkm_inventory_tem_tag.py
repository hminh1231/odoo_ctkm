# -*- coding: utf-8 -*-

from odoo import api, fields, models

# Các trường làm thay đổi bảng "Chi tiết tem/tag" của công việc CTKM.
TASK_LINE_TRIGGER_FIELDS = {
    'program_id',
    'material_code',
    'store',
    'quantity',
    'replaced_quantity',
    'date',
}


def _normalize_store_code(value):
    if isinstance(value, dict):
        # hr.store.code.name đọc từ cột jsonb (translate) có thể trả về dict.
        value = next(iter(value.values()), '') if value else ''
    if not isinstance(value, str):
        value = str(value) if value else ''
    value = ' '.join(value.strip().split())
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
    replaced_quantity = fields.Float(
        string='SL đã thay',
        default=0.0,
        help='Số lượng tem/tag đã thay thực tế tại cửa hàng (bước 12).',
    )
    replaced = fields.Boolean(
        string='Đã thay',
        compute='_compute_replaced',
        store=True,
        readonly=True,
        help='Đã thay đủ số lượng tem/tag tại cửa hàng (bước 12).',
    )

    @api.depends('store')
    def _compute_store_key(self):
        for record in self:
            record.store_key = _normalize_store_code(record.store)

    @api.depends('quantity', 'replaced_quantity')
    def _compute_replaced(self):
        for record in self:
            done = record.replaced_quantity or 0.0
            record.replaced = bool(done > 0 and done >= (record.quantity or 0.0))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._ctkm_sync_task_tem_tag_lines()
        return records

    def write(self, vals):
        programs = self.mapped('program_id')
        res = super().write(vals)
        if TASK_LINE_TRIGGER_FIELDS & set(vals):
            programs |= self.mapped('program_id')
            self._ctkm_sync_task_tem_tag_lines(programs.ids)
        return res

    def unlink(self):
        program_ids = self.mapped('program_id').ids
        res = super().unlink()
        self._ctkm_sync_task_tem_tag_lines(program_ids)
        return res

    def _ctkm_sync_task_tem_tag_lines(self, program_ids=None):
        """Cập nhật bảng "Chi tiết tem/tag" của các công việc bước 4 / bước 12."""
        # Ghi ngược từ bảng chi tiết về kho: không dựng lại bảng (tránh vòng lặp).
        if self.env.context.get('ctkm_tem_tag_line_sync'):
            return False
        if program_ids is None:
            program_ids = self.mapped('program_id').ids
        if not program_ids:
            return False
        self.env['ctkm.task'].sudo()._ctkm_sync_tem_tag_lines_for_programs(program_ids)
        return True

    @api.model
    def store_keys_for_user(self, user):
        """Mã/tên cửa hàng (HRM) của một người dùng, đã chuẩn hóa để so khớp Store."""
        user = user.sudo() if user else self.env['res.users']
        if not user:
            return []
        codes = []
        if 'employee_ma_bo_phan_id' in user._fields and user.employee_ma_bo_phan_id:
            codes.append(user.employee_ma_bo_phan_id.code)
        if 'employee_store_id' in user._fields and user.employee_store_id:
            codes.append(user.employee_store_id.code)
        employee = self.env['hr.employee']
        if 'employee_id' in user._fields and user.employee_id:
            employee = user.employee_id.sudo()
        elif user.employee_ids:
            employee = user.employee_ids.sudo()[:1]
        if employee:
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

    @api.model
    def current_user_store_keys(self):
        return self.store_keys_for_user(self.env.user)
