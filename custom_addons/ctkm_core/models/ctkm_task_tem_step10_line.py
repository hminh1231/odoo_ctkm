# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .ctkm_task_tem_print_line import normalize_store_key


class CtkmTaskTemStep10Line(models.Model):
    """Dòng cửa hàng của bước 10: bàn giao tem/tag hoặc thu tem/tag."""

    _name = 'ctkm.task.tem.step10.line'
    _description = 'Cửa hàng bàn giao / thu tem-tag'
    _rec_name = 'store'
    _order = 'sequence, store, id'

    task_id = fields.Many2one(
        'ctkm.task',
        string='Công việc',
        required=True,
        ondelete='cascade',
        index=True,
    )
    line_type = fields.Selection(
        selection=[
            ('handover', 'Bàn giao tem/tag'),
            ('collect', 'Thu tem/tag'),
        ],
        string='Loại bảng',
        required=True,
        index=True,
        default='handover',
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
    )
    print_line_id = fields.Many2one(
        'ctkm.task.tem.print.line',
        string='Dòng in tem/tag',
        ondelete='set null',
        index=True,
        help='Dòng bước 9 tương ứng; SL bàn giao lấy từ đây.',
    )
    material_code = fields.Char(
        string='Mã sản phẩm',
        index=True,
        help='Mã vật tư thu hồi (bước Thu tem/tag).',
    )
    tem_quantity = fields.Float(string='SL tem')
    tag_quantity = fields.Float(string='SL tag')
    handover_tem_quantity = fields.Float(
        string='SL tem',
        compute='_compute_handover_qty',
        help='Luôn lấy SL tem từ bước In tem, Tag.',
    )
    handover_tag_quantity = fields.Float(
        string='SL tag',
        compute='_compute_handover_qty',
        help='Luôn lấy SL tag từ bước In tem, Tag.',
    )
    done = fields.Boolean(string='Đã in')
    is_manual = fields.Boolean(string='Thêm tay', default=False)

    _task_type_store_uniq = models.Constraint(
        'UNIQUE(task_id, line_type, store_key, material_code)',
        'Mỗi cửa hàng chỉ có một dòng trên mỗi bảng bước 10 (theo Mã sản phẩm).',
    )

    @api.depends('store_id.code', 'store_key')
    def _compute_store_code(self):
        for line in self:
            line.store_code = line.store_id.code or line.store_key or False

    @api.depends(
        'print_line_id.tem_quantity',
        'print_line_id.tag_quantity',
        'tem_quantity',
        'tag_quantity',
    )
    def _compute_handover_qty(self):
        for line in self:
            source = line.print_line_id
            if source:
                line.handover_tem_quantity = source.tem_quantity or 0.0
                line.handover_tag_quantity = source.tag_quantity or 0.0
            else:
                line.handover_tem_quantity = line.tem_quantity or 0.0
                line.handover_tag_quantity = line.tag_quantity or 0.0

    @api.onchange('store_id')
    def _onchange_store_id(self):
        if not self.store_id:
            return
        self.update(self._vals_from_hr_store(fill_quantity=False))

    def _vals_from_hr_store(self, fill_quantity=False):
        self.ensure_one()
        store = self.store_id
        if not store:
            return {}
        store_name = store.name or ''
        store_key = normalize_store_key(store.code or store_name)
        vals = {
            'store': store_name or store.code or store_key,
            'store_key': store_key,
            'is_manual': True,
        }
        if fill_quantity:
            vals['tem_quantity'] = 0.0
            vals['tag_quantity'] = 0.0
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        internal = self.env.context.get('ctkm_tem_tag_line_sync')
        if not internal:
            self._check_can_edit_step10_lines()
        lines = super().create(vals_list)
        if not internal:
            for line in lines.filtered('store_id'):
                line.with_context(ctkm_tem_tag_line_sync=True).write(
                    line._vals_from_hr_store(fill_quantity=False)
                )
        return lines

    def write(self, vals):
        internal = self.env.context.get('ctkm_tem_tag_line_sync')
        if not internal:
            self._check_can_edit_step10_lines()
            if 'tem_quantity' in vals or 'tag_quantity' in vals:
                if self.filtered(lambda line: line.line_type == 'handover'):
                    raise UserError(_(
                        'Số lượng bảng Bàn giao tem/tag lấy từ bước 9, không sửa tay được.'
                    ))
        res = super().write(vals)
        if not internal and 'done' in vals:
            programs = self.mapped('task_id.program_id')
            if programs:
                programs.invalidate_recordset([
                    'stage_progress_json', 'checklist_current_stage_id',
                ])
        if 'store_id' in vals and not internal:
            for line in self:
                if line.store_id:
                    line.with_context(ctkm_tem_tag_line_sync=True).write(
                        line._vals_from_hr_store(fill_quantity=False)
                    )
        return res

    def unlink(self):
        if not self.env.context.get('ctkm_tem_tag_line_sync'):
            self._check_can_edit_step10_lines()
        return super().unlink()

    def action_toggle_step10_done(self):
        """Tick Đã in: đánh dấu cửa hàng đã bàn giao / thu xong."""
        self._check_can_edit_step10_lines()
        for line in self:
            done = not line.done
            line.with_context(ctkm_tem_tag_line_sync=True).write({'done': done})
        return False

    def _check_can_edit_step10_lines(self):
        is_ctkm_manager = self.env.user.has_group('ctkm_core.group_ctkm_manager')
        for line in self:
            task = line.task_id
            if task and not task.is_tem_handover_task:
                raise UserError(_(
                    'Chỉ bước "Bàn giao Tem Tag / Thu hồi tem tag cũ" '
                    'mới được sửa bảng này.'
                ))
            if task and not is_ctkm_manager and self.env.user not in task.user_ids:
                raise UserError(_(
                    'Chỉ người nhận việc mới được sửa bảng bàn giao / thu tem-tag.'
                ))

    @api.constrains('task_id', 'line_type', 'store_key')
    def _check_unique_store_key(self):
        for line in self:
            if not line.store_key or not line.task_id:
                continue
            duplicate = self.search([
                ('task_id', '=', line.task_id.id),
                ('line_type', '=', line.line_type),
                ('store_key', '=', line.store_key),
                ('id', '!=', line.id),
            ], limit=1)
            if duplicate:
                raise ValidationError(_(
                    'Cửa hàng "%s" đã có trong bảng này.'
                ) % (line.store or line.store_code or line.store_key))
