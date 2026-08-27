# -*- coding: utf-8 -*-

from odoo import api, fields, models


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
    stage_id = fields.Many2one(
        'ctkm.stage',
        string='Giai đoạn',
        ondelete='set null',
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
    user_ids = fields.Many2many(
        'res.users',
        'ctkm_checklist_line_user_rel',
        'line_id',
        'user_id',
        string='Người phụ trách',
        domain="[('share', '=', False)]",
    )
    need_manager_confirm = fields.Boolean(
        string='Cần quản lý xác nhận',
        default=True,
    )
    verifier_ids = fields.Many2many(
        'hr.employee',
        'ctkm_checklist_line_verifier_rel',
        'line_id',
        'employee_id',
        string='Người kiểm soát',
        domain="[('user_id.share', '=', False)]",
        help='Nhân viên xác nhận bước này. Khi đặt, bước dùng những người này '
             'kiểm soát thay vì quản lý theo organization chart.',
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
        if any(f in vals for f in ('state', 'done_date', 'user_ids', 'name', 'need_manager_confirm', 'verifier_ids')) and not self.env.context.get('ctkm_task_sync'):
            Task = self.env['ctkm.task']
            for line in self:
                existing = Task.search([
                    ('program_id', '=', line.program_id.id),
                    ('checklist_line_id', '=', line.id),
                ], limit=1)
                if existing:
                    Task._ctkm_sync_task_from_checklist(line)
                elif line.user_ids:
                    line._ctkm_ensure_task()
                    Task._ctkm_sync_task_from_checklist(line)
        return res

    def _ctkm_ensure_task(self):
        """Một bước checklist = một công việc (theo checklist_line_id)."""
        self.ensure_one()
        if not self.user_ids or not self.program_id:
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
            if task.user_ids != self.user_ids:
                update_vals['user_ids'] = [(6, 0, self.user_ids.ids)]
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
            'user_ids': [(6, 0, self.user_ids.ids)],
            'verifier_ids': [(6, 0, self.verifier_ids.ids)],
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

