# -*- coding: utf-8 -*-

import re
import unicodedata

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


def _normalize_key(value):
    text = unicodedata.normalize('NFD', (value or '').lower())
    text = ''.join(char for char in text if unicodedata.category(char) != 'Mn')
    return re.sub(r'[^a-z0-9]+', '', text.replace('đ', 'd'))


def classify_print_kind(tem_tag_value):
    """Phân loại dòng kho thành tem hoặc tag theo cột Tem/tag."""
    key = _normalize_key(tem_tag_value)
    if 'tag' in key or key == 'tab':
        return 'tag'
    return 'tem'


def normalize_store_key(value):
    if isinstance(value, dict):
        value = next(iter(value.values()), '') if value else ''
    if not isinstance(value, str):
        value = str(value) if value else ''
    value = ' '.join(value.strip().split())
    return value.upper() if value else False


class CtkmTaskTemPrintLine(models.Model):
    """Dòng cửa hàng của bước 9 (In tem, Tag).

    Gom kho Tem/Tag của CTKM theo cửa hàng: SL tem, SL tag, ô tích đã in.
    Có thể thêm tay bằng cách chọn cửa hàng từ Cấu hình nhân viên (hr.store).
    """

    _name = 'ctkm.task.tem.print.line'
    _description = 'Cửa hàng in tem/tag'
    _rec_name = 'store'
    _order = 'sequence, store, id'

    task_id = fields.Many2one(
        'ctkm.task',
        string='Công việc',
        required=True,
        ondelete='cascade',
        index=True,
    )
    sequence = fields.Integer(string='STT', default=1, readonly=True)
    store_id = fields.Many2one(
        'hr.store',
        string='Tên cửa hàng',
        ondelete='restrict',
        index=True,
        help='Cửa hàng lấy từ Nhân viên → Cấu hình → Cửa hàng.',
    )
    store = fields.Char(string='Tên cửa hàng (kho)', index=True)
    store_key = fields.Char(string='Store Key', index=True)
    store_code = fields.Char(
        string='Mã cửa hàng',
        compute='_compute_store_code',
        help='Mã cửa hàng trên cấu hình nhân viên.',
    )
    tem_quantity = fields.Float(string='SL tem')
    tag_quantity = fields.Float(string='SL tag')
    done = fields.Boolean(
        string='Kết quả',
        help='Tick khi cửa hàng này đã in tem/tag xong.',
    )
    is_manual = fields.Boolean(
        string='Thêm tay',
        default=False,
        help='Dòng do người dùng bấm Tạo dòng, không xóa khi làm mới từ kho.',
    )

    _task_store_uniq = models.Constraint(
        'UNIQUE(task_id, store_key)',
        'Mỗi cửa hàng chỉ có một dòng in tem/tag trên công việc.',
    )

    @api.depends('store_id.code', 'store_key')
    def _compute_store_code(self):
        for line in self:
            line.store_code = line.store_id.code or line.store_key or False

    @api.onchange('store_id')
    def _onchange_store_id(self):
        if not self.store_id:
            return
        vals = self._vals_from_hr_store()
        self.update(vals)

    def _vals_from_hr_store(self):
        self.ensure_one()
        store = self.store_id
        if not store:
            return {}
        store_name = store.name or ''
        store_key = normalize_store_key(store.code or store_name)
        tem_qty, tag_qty = self._quantities_from_inventory(store_key, store_name)
        return {
            'store': store_name or store.code or store_key,
            'store_key': store_key,
            'tem_quantity': tem_qty,
            'tag_quantity': tag_qty,
            'is_manual': True,
        }

    def _quantities_from_inventory(self, store_key, store_name):
        if 'ctkm.inventory.tem.tag' not in self.env:
            return 0.0, 0.0
        program = self.task_id.program_id
        if not program:
            return 0.0, 0.0
        keys = [key for key in (store_key, normalize_store_key(store_name)) if key]
        code = self.store_id.code
        if isinstance(code, dict):
            code = next(iter(code.values()), '') if code else ''
        code = normalize_store_key(code) if code else False
        if code and code not in keys:
            keys.append(code)
        if not keys and not store_name:
            return 0.0, 0.0
        domain = [('program_id', '=', program.id)]
        store_terms = [term for term in (store_key, store_name, code) if term]
        key_domain = [('store_key', 'in', keys)] if keys else []
        for term in store_terms:
            if key_domain:
                key_domain = ['|', ('store', 'ilike', term)] + key_domain
            else:
                key_domain = [('store', 'ilike', term)]
        if not key_domain:
            return 0.0, 0.0
        rows = self.env['ctkm.inventory.tem.tag'].sudo().search(domain + key_domain)
        tem_qty = 0.0
        tag_qty = 0.0
        for row in rows:
            amount = row.quantity or 0.0
            if classify_print_kind(row.tem_tag) == 'tag':
                tag_qty += amount
            else:
                tem_qty += amount
        return tem_qty, tag_qty

    @api.model_create_multi
    def create(self, vals_list):
        internal = self.env.context.get('ctkm_tem_tag_line_sync')
        if not internal:
            self._check_can_edit_print_lines()
        lines = super().create(vals_list)
        if not internal:
            to_fill = lines.filtered('store_id')
            if to_fill:
                for line in to_fill:
                    line.with_context(ctkm_tem_tag_line_sync=True).write(
                        line._vals_from_hr_store()
                    )
            lines._push_to_step10()
        return lines

    def write(self, vals):
        internal = self.env.context.get('ctkm_tem_tag_line_sync')
        if not internal:
            self._check_can_edit_print_lines()
        res = super().write(vals)
        if 'store_id' in vals and not internal:
            for line in self:
                if not line.store_id:
                    continue
                fill = line._vals_from_hr_store()
                # Không ghi đè SL user vừa nhập (list editable gửi kèm store_id).
                if 'tem_quantity' in vals or line.tem_quantity:
                    fill.pop('tem_quantity', None)
                if 'tag_quantity' in vals or line.tag_quantity:
                    fill.pop('tag_quantity', None)
                if fill:
                    line.with_context(ctkm_tem_tag_line_sync=True).write(fill)
        if not internal:
            self._push_to_step10()
        return res

    def unlink(self):
        internal = self.env.context.get('ctkm_tem_tag_line_sync')
        if not internal:
            self._check_can_edit_print_lines()
        programs = self.mapped('task_id.program_id')
        res = super().unlink()
        if not internal and programs:
            self.env['ctkm.task'].sudo().search([
                ('program_id', 'in', programs.ids),
                ('is_tem_handover_task', '=', True),
            ])._ctkm_sync_step10_lines()
        return res

    def _push_to_step10(self):
        """Đẩy danh sách cửa hàng bước 9 sang bảng bước 10 cùng CTKM."""
        programs = self.mapped('task_id.program_id')
        if not programs:
            return
        self.env['ctkm.task'].sudo().search([
            ('program_id', 'in', programs.ids),
            ('is_tem_handover_task', '=', True),
        ])._ctkm_sync_step10_lines()

    def _check_can_edit_print_lines(self):
        is_ctkm_manager = self.env.user.has_group('ctkm_core.group_ctkm_manager')
        for line in self:
            task = line.task_id
            if task and not task.is_tem_print_task:
                raise UserError(_(
                    'Chỉ bước "In tem, Tag" mới được sửa danh sách cửa hàng in.'
                ))
            if task and not is_ctkm_manager and self.env.user not in task.user_ids:
                raise UserError(_(
                    'Chỉ người nhận việc mới được sửa danh sách cửa hàng in tem/tag.'
                ))

    @api.constrains('task_id', 'store_key')
    def _check_unique_store_key(self):
        for line in self:
            if not line.store_key or not line.task_id:
                continue
            duplicate = self.search([
                ('task_id', '=', line.task_id.id),
                ('store_key', '=', line.store_key),
                ('id', '!=', line.id),
            ], limit=1)
            if duplicate:
                raise ValidationError(_(
                    'Cửa hàng "%s" đã có trong danh sách in tem/tag.'
                ) % (line.store or line.store_code or line.store_key))
