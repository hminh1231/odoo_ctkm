# -*- coding: utf-8 -*-

from odoo import api, fields, models

# Các bước chuẩn quy trình CTKM (theo bảng công việc).
CTKM_CHECKLIST_DEFAULT_STEPS = [
    'Duyệt CTKM',
    'Lập thông báo CTKM, trình ký',
    'Phát hành thông báo CTKM đến các bộ phận',
    'Đổ BB thay tem/tag(file tổng)',
    'Khai báo CTKM áp giá trên PM Linkq',
    'Lập BB thay tem, bàn giao cho KT kho  Kiểm tra BB thay tem tag',
    'Thiết kế mẫu tem/tag, Bảng nhận diện',
    'KT áp giá lên phần mềm linkq',
    'In tem, Tag',
    'Bàn giao Tem Tag cho CH  Thu hồi tem tag cũ',
    'Nhận tem tag mới',
    'Thay tem Tag',
    'Chụp team gửi lên group / chụp từng con tem',
    'Kiểm tra hình ảnh tem tag',
    'Kế toán áp giá CTKM lên PM Link Q Lập báo cáo cửa hàng đã thay tem tag: cửa hàng nào chưa thay tem Lập báo cáo cửa hàng đã áp giá',
    'Hậu kiểm CTKM Giám sát đi kiểm tra thay tem',
]


class CtkmProgramChecklistLine(models.Model):
    _name = 'ctkm.program.checklist.line'
    _description = 'Bước checklist CTKM'
    _order = 'sequence, id'

    program_id = fields.Many2one(
        'ctkm.program',
        string='Chương trình',
        required=True,
        ondelete='cascade',
        index=True,
    )
    sequence = fields.Integer(string='STT', default=10, required=True)
    name = fields.Char(string='Công việc', required=True)
    state = fields.Selection(
        selection=[
            ('todo', 'Chưa làm'),
            ('progress', 'Đang làm'),
            ('done', 'Hoàn thành'),
        ],
        string='Trạng thái',
        default='todo',
        required=True,
    )
    is_done = fields.Boolean(
        string='Xong',
        compute='_compute_is_done',
        inverse='_inverse_is_done',
        store=False,
    )
    done_date = fields.Date(string='Ngày hoàn thành')
    user_id = fields.Many2one(
        'res.users',
        string='Người phụ trách',
        domain="[('share', '=', False)]",
    )
    note = fields.Char(string='Ghi chú')
    notified = fields.Boolean(
        string='Đã gửi tin việc',
        default=False,
        copy=False,
        help='Đã gửi OdooBot CTKM cho người phụ trách bước này.',
    )
    notified_date = fields.Datetime(
        string='Ngày gửi tin việc',
        copy=False,
        readonly=True,
    )

    @api.depends('state')
    def _compute_is_done(self):
        for line in self:
            line.is_done = line.state == 'done'

    def _inverse_is_done(self):
        today = fields.Date.context_today(self)
        for line in self:
            if line.is_done:
                vals = {'state': 'done'}
                if not line.done_date:
                    vals['done_date'] = today
                line.write(vals)
            elif line.state == 'done':
                line.write({'state': 'todo', 'done_date': False})

    def action_mark_todo(self):
        self.write({'state': 'todo', 'done_date': False})
        return True

    def action_mark_progress(self):
        self.write({'state': 'progress'})
        return True

    def action_mark_done(self):
        today = fields.Date.context_today(self)
        for line in self:
            line.write({
                'state': 'done',
                'done_date': line.done_date or today,
            })
        return True

    def write(self, vals):
        res = super().write(vals)
        if any(f in vals for f in ('state', 'done_date', 'user_id', 'name')) and not self.env.context.get('ctkm_task_sync'):
            Task = self.env['ctkm.task']
            for line in self:
                existing = Task.search([
                    ('program_id', '=', line.program_id.id),
                    ('checklist_line_id', '=', line.id),
                ], limit=1)
                if existing:
                    Task._ctkm_sync_task_from_checklist(line)
                elif line.user_id:
                    line._ctkm_ensure_task()
                    Task._ctkm_sync_task_from_checklist(line)
        return res

    def _ctkm_ensure_task(self):
        """Một bước checklist = một công việc (theo checklist_line_id)."""
        self.ensure_one()
        if not self.user_id or not self.program_id:
            return self.env['ctkm.task']
        Task = self.env['ctkm.task'].sudo()
        task = Task.search([
            ('program_id', '=', self.program_id.id),
            ('checklist_line_id', '=', self.id),
        ], limit=1)
        if task:
            update_vals = {}
            if task.name != self.name:
                update_vals['name'] = self.name
            if task.user_id != self.user_id:
                update_vals['user_id'] = self.user_id.id
            if update_vals and not task.env.context.get('ctkm_task_sync'):
                task.with_context(
                    ctkm_task_sync=True,
                    ctkm_internal_state_write=True,
                ).write(update_vals)
            return task
        # Task mới luôn bắt đầu todo/progress; "Xong" trên checklist không tạo task = done.
        initial_state = self.state if self.state in ('todo', 'progress') else 'todo'
        vals = {
            'program_id': self.program_id.id,
            'user_id': self.user_id.id,
            'process_date': fields.Date.context_today(self),
            'name': self.name,
            'state': initial_state,
            'company_id': self.program_id.company_id.id or self.env.company.id,
            'checklist_line_id': self.id,
        }
        if self.done_date:
            vals['done_date'] = self.done_date
        try:
            with self.env.cr.savepoint():
                return Task.create(vals)
        except Exception:
            return Task.search([
                ('program_id', '=', self.program_id.id),
                ('checklist_line_id', '=', self.id),
            ], limit=1)

