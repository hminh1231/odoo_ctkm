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
    """Phân loại dòng kho thành tem hoặc tag. Một dòng chỉ thuộc một loại."""
    kinds = classify_tem_tag_kinds(tem_tag_value)
    if 'tag' in kinds and 'tem' not in kinds:
        return 'tag'
    return 'tem'


def kind_from_sheet_name(sheet_name):
    """Sheet TEM → tem, sheet TAG → tag. Tên khác trả về False."""
    key = _normalize_key(sheet_name)
    if not key:
        return False
    if key == 'tem' or (key.startswith('tem') and 'tag' not in key):
        return 'tem'
    if key == 'tag' or key.startswith('tag'):
        return 'tag'
    return False


def classify_tem_tag_kinds(tem_tag_value, sheet_name=None):
    """Một dòng chỉ là tem hoặc tag.

    Ưu tiên tên sheet TEM/TAG. Không dùng giá trị cột 'TEM+TAG' để tích cả hai.
    """
    sheet_kind = kind_from_sheet_name(sheet_name)
    if sheet_kind:
        return {sheet_kind}
    key = _normalize_key(tem_tag_value)
    if not key:
        return set()
    if key in ('tag', 'tab') or (key.startswith('tag') and 'tem' not in key):
        return {'tag'}
    if key == 'tem' or (key.startswith('tem') and 'tag' not in key):
        return {'tem'}
    if 'tag' in key and 'tem' not in key:
        return {'tag'}
    if 'tem' in key and 'tag' not in key:
        return {'tem'}
    return set()


def tem_tag_label_from_kinds(kinds):
    kinds = set(kinds or ())
    if kinds == {'tag'}:
        return 'TAG'
    if kinds == {'tem'}:
        return 'TEM'
    return False


def normalize_store_key(value):
    if isinstance(value, dict):
        value = next(iter(value.values()), '') if value else ''
    if not isinstance(value, str):
        value = str(value) if value else ''
    value = ' '.join(value.strip().split())
    return value.upper() if value else False


def hr_store_lookup_keys(store):
    """Các mã đã chuẩn hóa của một hr.store (code + tên)."""
    keys = []
    for raw in (store.code, store.name):
        key = normalize_store_key(raw)
        if key and key not in keys:
            keys.append(key)
    return keys


def match_hr_store(stores, *candidates):
    """Khớp mã kho (AETL) với hr.store (AETL hoặc LUG_AETL)."""
    wanted = []
    for candidate in candidates:
        key = normalize_store_key(candidate)
        if key and key not in wanted:
            wanted.append(key)
    if not wanted or not stores:
        return stores.browse() if hasattr(stores, 'browse') else False

    exact = {}
    for store in stores:
        for key in hr_store_lookup_keys(store):
            exact.setdefault(key, store)

    for key in wanted:
        if key in exact:
            return exact[key]
        lug_key = 'LUG' + key
        if lug_key in exact:
            return exact[lug_key]

    for key in wanted:
        if len(key) < 3:
            continue
        for code_key, store in exact.items():
            if code_key.endswith(key) and code_key != key:
                return store
    return stores.browse() if hasattr(stores, 'browse') else False


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
        string='Đã in',
        help='Tick khi cửa hàng này đã in tem/tag xong.',
    )
    done_date = fields.Date(
        string='Ngày hoàn thành',
        help='Tự điền ngày khi tick Đã in. Bỏ tick thì xóa; tick lại lấy ngày mới.',
    )
    is_manual = fields.Boolean(
        string='Thêm tay',
        default=False,
        help='Dòng do người dùng bấm Tạo dòng, không xóa khi làm mới từ kho.',
    )
    program_id = fields.Many2one(
        related='task_id.program_id',
        string='Chương trình KM',
        store=True,
        index=True,
    )
    notify_code = fields.Char(
        related='program_id.notify_code',
        string='Số TB',
        store=True,
        index=True,
    )
    program_name = fields.Char(
        related='program_id.name',
        string='Tên CTKM',
    )
    name = fields.Char(
        related='program_id.name',
        string='Tên CTKM',
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
        if 'done' in vals and 'done_date' not in vals:
            vals = dict(vals)
            vals['done_date'] = (
                fields.Date.context_today(self) if vals.get('done') else False
            )
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

    def action_toggle_print_done(self):
        """Tick Đã in: chuyển bảng và ghi/xóa ngày hoàn thành theo lần tick."""
        self._check_can_edit_print_lines()
        today = fields.Date.context_today(self)
        for line in self:
            done = not line.done
            line.with_context(ctkm_tem_tag_line_sync=True).write({
                'done': done,
                'done_date': today if done else False,
            })
        self._push_to_step10()
        return False

    def unlink(self):
        internal = self.env.context.get('ctkm_tem_tag_line_sync')
        if not internal:
            self._check_can_edit_print_lines()
        programs = self.mapped('task_id.program_id')
        res = super().unlink()
        if not internal and programs:
            Task = self.env['ctkm.task'].sudo()
            Task.search([
                ('program_id', 'in', programs.ids),
                ('is_tem_handover_task', '=', True),
            ])._ctkm_sync_step10_lines()
            Task.search([
                ('program_id', 'in', programs.ids),
                ('is_tem_postcheck_task', '=', True),
            ])._ctkm_sync_postcheck_lines()
        return res

    def _push_to_step10(self):
        """Đẩy danh sách cửa hàng bước 9 sang bảng bước 10 và hậu kiểm cùng CTKM."""
        programs = self.mapped('task_id.program_id')
        if not programs:
            return
        Task = self.env['ctkm.task'].sudo()
        Task.search([
            ('program_id', 'in', programs.ids),
            ('is_tem_handover_task', '=', True),
        ])._ctkm_sync_step10_lines()
        Task.search([
            ('program_id', 'in', programs.ids),
            ('is_tem_postcheck_task', '=', True),
        ])._ctkm_sync_postcheck_lines()

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
