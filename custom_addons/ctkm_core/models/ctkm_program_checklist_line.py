# -*- coding: utf-8 -*-

from markupsafe import Markup, escape

from odoo import _, api, fields, models


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
    work_percent = fields.Integer(
        string='Tiến độ %',
        compute='_compute_work_percent',
        help='Phần trăm hoàn thành để hiện thanh loading. '
             'Bước 10–15 theo cửa hàng và SL tem/tag từ file bước 4.',
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
    ctkm_notify_sent = fields.Boolean(
        string='Đã gửi thông báo giai đoạn',
        default=False,
        copy=False,
        help='Đã gửi thông báo "Thông báo" (Cấu hình → Thông báo) khi bước này '
             'hoàn thành. Reset khi bước bị mở lại để có thể gửi lại.',
    )
    ctkm_supervisor_note_sent = fields.Boolean(
        string='Đã gửi ghi chú Giám sát',
        default=False,
        copy=False,
        help='Đã gửi tin "Giám sát đã hoàn thành kiểm tra..." tới toàn bộ '
             'Phạm vi thông báo khi bước Hậu kiểm hoàn thành. '
             'Reset khi bước bị mở lại để có thể gửi lại.',
    )

    @api.depends(
        'state',
        'stage_id',
        'program_id.stage_progress_json',
    )
    def _compute_work_percent(self):
        for line in self:
            percent = None
            mapping = line.program_id.stage_progress_json or {}
            if line.stage_id:
                val = mapping.get(str(line.stage_id.id))
                if isinstance(val, dict) and val.get('percent') is not None:
                    try:
                        percent = int(round(float(val['percent'])))
                    except (TypeError, ValueError):
                        percent = None
            if percent is None:
                percent = 100 if line.state == 'done' else 0
            line.work_percent = max(0, min(100, percent))

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
        old_states = {line.id: line.state for line in self}
        res = super().write(vals)
        if 'state' in vals and not self.env.context.get('ctkm_skip_stage_notify'):
            for line in self:
                old = old_states.get(line.id)
                new = line.state
                if new == 'done' and old != 'done':
                    line._ctkm_send_stage_notify()
                    line._ctkm_send_supervisor_check_notify()
                elif old == 'done' and new != 'done':
                    # Bước bị mở lại → cho phép gửi lại lần sau.
                    if line.ctkm_notify_sent:
                        line.sudo().write({'ctkm_notify_sent': False})
                    if line.ctkm_supervisor_note_sent:
                        line.sudo().write({'ctkm_supervisor_note_sent': False})
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

    def _ctkm_send_stage_notify(self):
        """Gửi thông báo (Cấu hình → Thông báo) qua OdooBot CTKM khi bước xong.

        Gửi ``Nội dung thông báo`` của giai đoạn tới mọi nhân viên trong
        ``Người thông báo``. Chỉ gửi 1 lần mỗi lần hoàn thành (cờ
        ``ctkm_notify_sent``), bỏ qua nếu chưa cấu hình hoặc đang đồng bộ.
        """
        self.ensure_one()
        if self.ctkm_notify_sent:
            return
        stage = self.stage_id
        if not stage or not stage.notify_user_ids or not (stage.notify_content or '').strip():
            return
        program = self.program_id
        if not program:
            return
        users = stage.notify_user_ids.mapped('user_id').filtered(
            lambda u: u and u.active and not u.share and u.partner_id
        )
        if not users:
            return
        body = self._ctkm_stage_notify_body(stage, program)
        sent_users = self.env['res.users']
        for user in users:
            try:
                message = program._post_ctkm_bot_discuss_message(user, body)
            except Exception:
                message = self.env['mail.message']
            if message:
                sent_users |= user
        self.sudo().write({'ctkm_notify_sent': True})
        if sent_users:
            program.message_post(
                body=_(
                    'Đã gửi thông báo giai đoạn <b>%(stage)s</b> tới %(users)s '
                    'qua OdooBot CTKM.'
                ) % {
                    'stage': escape(stage.name or ''),
                    'users': escape(', '.join(sent_users.mapped('name'))),
                },
                subtype_xmlid='mail.mt_note',
                body_is_html=True,
            )

    def _ctkm_stage_notify_body(self, stage, program):
        """Nội dung tin: tên CTKM + giai đoạn (để biết ngữ cảnh) + Nội dung thông báo."""
        parts = []
        if program.name:
            parts.append(Markup('<b>%s</b>') % escape(program.name))
        if stage.name:
            parts.append(Markup('Giai đoạn: %s') % escape(stage.name))
        content = stage.notify_content or ''
        if content:
            parts.append(Markup(content))
        return Markup('<br/>').join(parts)

    _CTKM_SUPERVISOR_CHECK_KEYWORDS = ('hậu kiểm', 'hau kiem')

    def _ctkm_is_supervisor_check_step(self):
        """Bước 'Hậu kiểm CTKM Giám sát đi kiểm tra thay tem' (khớp theo tên)."""
        self.ensure_one()
        name = (self.name or '').lower()
        return any(kw in name for kw in self._CTKM_SUPERVISOR_CHECK_KEYWORDS)

    def _ctkm_send_supervisor_check_notify(self):
        """Sau bước Hậu kiểm hoàn thành: gửi OdooBot CTKM tới TOÀN BỘ Phạm vi thông báo.

        Tin: "Giám sát đã hoàn thành kiểm tra với ghi chú là: <Ghi chú bước>".
        Ghi chú lấy từ tab "Ghi chú & Tài liệu" (work_note) của công việc bước này,
        fallback về Ghi chú của chính dòng bước. Chỉ gửi 1 lần mỗi lần hoàn thành
        (cờ ``ctkm_supervisor_note_sent``), bỏ qua nếu chưa cấu hình người nhận.
        """
        self.ensure_one()
        if self.ctkm_supervisor_note_sent:
            return
        if not self._ctkm_is_supervisor_check_step():
            return
        program = self.program_id
        if not program:
            return

        # Ghi chú của bước: ưu tiên work_note (tab "Ghi chú & Tài liệu") của công việc,
        # fallback về Ghi chú trên dòng bước. Luôn sudo: hoàn thành có thể chạy từ
        # form CTKM (người khác) → không bị chặn ACL đọc công việc của Giám sát.
        task = self.env['ctkm.task'].sudo().search([
            ('program_id', '=', program.id),
            ('checklist_line_id', '=', self.id),
        ], limit=1)
        note_html = task.work_note if task else False
        if not note_html:
            note_html = self.note or False
        note_text = program._ctkm_notify_plain_text(note_html) if note_html else ''

        users, skipped = program._ctkm_notify_recipient_users()
        if not users:
            # Không có người nhận hợp lệ → vẫn đánh dấu để không lặp, ghi log.
            self.sudo().write({'ctkm_supervisor_note_sent': True})
            program.message_post(
                body=_(
                    'Bước "%(step)s" đã hoàn thành nhưng Phạm vi thông báo '
                    'chưa có người nhận hợp lệ (%s nhân viên).'
                ) % {
                    'step': escape(self.name or ''),
                    'skipped': len(skipped),
                },
                subtype_xmlid='mail.mt_note',
                body_is_html=True,
            )
            return

        body = self._ctkm_supervisor_check_body(program, note_text)
        sent_users = self.env['res.users']
        for user in users:
            try:
                message = program._post_ctkm_bot_discuss_message(user, body)
            except Exception:
                message = self.env['mail.message']
            if message:
                sent_users |= user
        self.sudo().write({'ctkm_supervisor_note_sent': True})
        if sent_users:
            program.message_post(
                body=_(
                    'Đã gửi ghi chú "Giám sát đã hoàn thành kiểm tra" của bước '
                    '<b>%(step)s</b> tới %(users)s qua OdooBot CTKM.'
                ) % {
                    'step': escape(self.name or ''),
                    'users': escape(', '.join(sent_users.mapped('name'))),
                },
                subtype_xmlid='mail.mt_note',
                body_is_html=True,
            )

    def _ctkm_supervisor_check_body(self, program, note_text):
        """Nội dung tin gửi Phạm vi thông báo khi Giám sát hoàn thành kiểm tra."""
        parts = []
        if program.name:
            parts.append(Markup('<b>%s</b>') % escape(program.name))
        parts.append(Markup('Bước: %s') % escape(self.name or ''))
        if note_text:
            parts.append(
                Markup('Giám sát đã hoàn thành kiểm tra với ghi chú là: %s')
                % escape(note_text)
            )
        else:
            parts.append(Markup('Giám sát đã hoàn thành kiểm tra.'))
        parts.append(program._ctkm_notify_detail_button_markup())
        return Markup('<br/>').join(parts)

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

