# -*- coding: utf-8 -*-

import base64

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Domain
from odoo.tools import mimetypes

_CTKM_NOTIFY_DOC_EXTENSIONS = frozenset({
    '.pdf', '.doc', '.docx', '.xls', '.xlsx',
})


class CtkmProgram(models.Model):
    _name = 'ctkm.program'
    _description = 'Chương trình khuyến mãi'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_begin, id'

    def _get_default_stage_id(self):
        return self.env['ctkm.stage'].search([], limit=1)

    name = fields.Char(string='Tên chương trình', translate=True, required=True)
    active = fields.Boolean(default=True)
    user_id = fields.Many2one(
        'res.users', string='Người phụ trách', tracking=True,
        default=lambda self: self.env.user)
    company_id = fields.Many2one(
        'res.company', string='Công ty', change_default=True,
        default=lambda self: self.env.company,
        required=False)
    stage_id = fields.Many2one(
        'ctkm.stage', ondelete='restrict', default=_get_default_stage_id,
        tracking=True, copy=False)
    kanban_state = fields.Selection([
        ('normal', 'Đang thực hiện'),
        ('done', 'Sẵn sàng cho giai đoạn tiếp'),
        ('blocked', 'Bị chặn'),
    ], default='normal', copy=False, tracking=True)
    notify_code = fields.Char(string='Mã số thông báo', index=True)
    hour_quota = fields.Char(
        string='Định biên giờ',
        help='Định biên giờ cho chương trình / thông báo.',
    )
    notify_receipt_date = fields.Date(
        string='Ngày nhận thông báo',
        compute='_compute_notify_report_fields',
        help='Lấy thông tin tự động từ người nhập CTKM.',
    )
    notify_file_display = fields.Char(
        string='File thông báo',
        compute='_compute_notify_report_fields',
    )
    notify_scope_display = fields.Char(
        string='Phạm vi áp dụng',
        compute='_compute_notify_report_fields',
    )
    task_ids = fields.One2many(
        'ctkm.task', 'program_id', string='Công việc',
    )
    organizer_id = fields.Many2one(
        'res.partner', string='Đơn vị tổ chức', tracking=True,
        default=lambda self: self.env.company.partner_id,
        check_company=True)
    address_id = fields.Many2one(
        'res.partner', string='Địa điểm', default=lambda self: self.env.company.partner_id.id,
        check_company=True, tracking=True)
    event_url = fields.Char(
        string='URL sự kiện trực tuyến',
        help="Liên kết nơi sự kiện trực tuyến diễn ra.")
    seats_limited = fields.Boolean(string='Giới hạn đăng ký')
    seats_max = fields.Integer(string='Số lượng tối đa')
    date_begin = fields.Datetime(string='Ngày bắt đầu', required=True, tracking=True)
    date_end = fields.Datetime(string='Ngày kết thúc', required=True, tracking=True)
    note = fields.Html(string='Ghi chú')
    description = fields.Html(string='Mô tả', translate=True)
    badge_format = fields.Selection(
        string='Kích thước nhãn',
        selection=[
            ('A4_french_fold', 'A4 gập đôi'),
            ('A6', 'A6'),
            ('four_per_sheet', '4 trên một tờ'),
        ], default='A6', required=True)
    badge_image = fields.Image(
        'Ảnh nền nhãn',
        max_width=1024,
        max_height=1024,
        help='Chỉ dùng file ảnh (JPG, PNG...). PDF/Word/Excel hãy tải ở mục Tài liệu đính kèm.',
    )
    notify_document_ids = fields.Many2many(
        comodel_name='ir.attachment',
        relation='ctkm_program_notify_document_rel',
        column1='program_id',
        column2='attachment_id',
        string='Tài liệu đính kèm',
        help='Tài liệu PDF, Word hoặc Excel gửi kèm thông báo Discuss.',
    )
    ticket_instructions = fields.Html('Hướng dẫn vé', translate=True)
    notify_line_ids = fields.One2many(
        'ctkm.program.notify.line',
        'program_id',
        string='Phạm vi thông báo',
        copy=True,
    )
    checklist_line_ids = fields.One2many(
        'ctkm.program.checklist.line',
        'program_id',
        string='Checklist công việc',
        copy=True,
    )
    checklist_done_count = fields.Integer(
        string='Số bước đã xong',
        compute='_compute_checklist_progress',
    )
    checklist_total_count = fields.Integer(
        string='Tổng số bước',
        compute='_compute_checklist_progress',
    )
    checklist_progress_display = fields.Char(
        string='Tiến độ checklist',
        compute='_compute_checklist_progress',
    )
    checklist_current_step = fields.Char(
        string='Đang ở bước',
        compute='_compute_checklist_progress',
    )
    stage_progress_json = fields.Json(
        string='Tiến độ từng giai đoạn',
        compute='_compute_stage_progress_json',
        help='Map stage_id → {state, percent}. Bước 10–15 có percent (0–100) '
             'theo cửa hàng và SL tem/tag từ file bước 4.',
    )
    checklist_current_stage_id = fields.Many2one(
        'ctkm.stage',
        string='Giai đoạn đang làm',
        compute='_compute_stage_progress_json',
        help='Bước Đang làm, hoặc bước Chưa làm gần nhất — dùng để neo thanh giai đoạn.',
    )
    report_print_pending_ids = fields.Many2many(
        'ctkm.task.tem.print.line',
        compute='_compute_report_print_store_ids',
        string='Cửa hàng cần in tem/tag',
    )
    report_print_done_ids = fields.Many2many(
        'ctkm.task.tem.print.line',
        compute='_compute_report_print_store_ids',
        string='Cửa hàng đã hoàn thành in tem/tag',
    )
    report_price_replaced_ids = fields.Many2many(
        'ctkm.task.tem.price.line',
        compute='_compute_report_price_store_ids',
        string='Cửa hàng đã xác nhận thay tem',
    )
    report_price_not_replaced_ids = fields.Many2many(
        'ctkm.task.tem.price.line',
        compute='_compute_report_price_store_ids',
        string='Cửa hàng đã xác nhận chưa thay tem',
    )
    report_price_applied_ids = fields.Many2many(
        'ctkm.task.tem.price.line',
        compute='_compute_report_price_store_ids',
        string='Cửa hàng đã xác nhận áp giá',
    )

    @api.depends(
        'create_date', 'date_begin', 'notify_document_ids.name',
        'notify_line_ids.store_code', 'notify_line_ids.store_code_id',
    )
    def _compute_notify_report_fields(self):
        for program in self:
            # Ngày nhận TB: ưu tiên ngày tạo (người nhập CTKM), fallback ngày bắt đầu.
            if program.create_date:
                program.notify_receipt_date = fields.Datetime.context_timestamp(
                    program, program.create_date
                ).date()
            elif program.date_begin:
                program.notify_receipt_date = fields.Datetime.context_timestamp(
                    program, program.date_begin
                ).date()
            else:
                program.notify_receipt_date = False
            files = program.notify_document_ids.mapped('name')
            program.notify_file_display = ', '.join(files) if files else ''
            scopes = [
                code for code in program.notify_line_ids.mapped('store_code') if code
            ]
            if not scopes:
                scopes = [
                    line.store_code_id.display_name
                    for line in program.notify_line_ids
                    if line.store_code_id
                ]
            program.notify_scope_display = ', '.join(scopes) if scopes else ''

    @api.depends('task_ids.print_store_ids.done', 'task_ids.is_tem_print_task')
    def _compute_report_print_store_ids(self):
        Line = self.env['ctkm.task.tem.print.line']
        for program in self:
            lines = Line.search([('program_id', '=', program.id)])
            program.report_print_pending_ids = lines.filtered(lambda line: not line.done)
            program.report_print_done_ids = lines.filtered(lambda line: line.done)

    @api.depends(
        'task_ids.is_tem_price_task',
        'task_ids.price_store_ids.replaced',
        'task_ids.price_store_ids.not_replaced',
        'task_ids.price_store_ids.price_applied',
    )
    def _compute_report_price_store_ids(self):
        Line = self.env['ctkm.task.tem.price.line']
        for program in self:
            lines = Line.search([('program_id', '=', program.id)])
            program.report_price_replaced_ids = lines.filtered('replaced')
            program.report_price_not_replaced_ids = lines.filtered('not_replaced')
            program.report_price_applied_ids = lines.filtered('price_applied')

    @api.depends(
        'checklist_line_ids.state',
        'checklist_line_ids.sequence',
        'checklist_line_ids.name',
    )
    def _compute_checklist_progress(self):
        for program in self:
            lines = program.checklist_line_ids.sorted(lambda line: (line.sequence, line.id))
            total = len(lines)
            done = len(lines.filtered(lambda line: line.state == 'done'))
            program.checklist_total_count = total
            program.checklist_done_count = done
            program.checklist_progress_display = (
                _('Đã xong %s/%s') % (done, total) if total else _('Chưa có checklist')
            )
            current = lines.filtered(lambda line: line.state != 'done')[:1]
            if current:
                program.checklist_current_step = '%s. %s' % (current.sequence, current.name)
            elif total:
                program.checklist_current_step = _('Đã hoàn thành tất cả bước')
            else:
                program.checklist_current_step = False

    @api.depends(
        'checklist_line_ids.state',
        'checklist_line_ids.stage_id',
        'checklist_line_ids.sequence',
        'checklist_line_ids.name',
        'task_ids.is_tem_handover_task',
        'task_ids.handover_store_ids.done',
        'task_ids.handover_store_ids.store_key',
        'task_ids.collect_store_ids.done',
        'task_ids.collect_store_ids.store_key',
        'task_ids.is_tem_receive_task',
        'task_ids.is_tem_replace_task',
        'task_ids.tem_tag_replace_ids.received',
        'task_ids.tem_tag_replace_ids.replaced_done',
        'task_ids.tem_tag_replace_ids.replaced_quantity',
        'task_ids.tem_tag_replace_ids.total_quantity',
        'task_ids.tem_tag_replace_ids.store',
        'task_ids.tem_tag_replace_ids.store_key',
        'task_ids.is_tem_photo_task',
        'task_ids.is_tem_check_task',
        'task_ids.tem_photo_check_ids.photographed',
        'task_ids.tem_photo_check_ids.confirmed',
        'task_ids.tem_photo_check_ids.store',
        'task_ids.tem_photo_check_ids.store_key',
        'task_ids.tem_photo_check_ids.total_quantity',
        'task_ids.is_tem_price_task',
        'task_ids.price_store_ids.replaced',
        'task_ids.price_store_ids.not_replaced',
        'task_ids.price_store_ids.price_applied',
        'task_ids.price_store_ids.store_key',
        'task_ids.is_tem_print_task',
        'task_ids.print_store_ids.tem_quantity',
        'task_ids.print_store_ids.tag_quantity',
        'task_ids.print_store_ids.store_key',
    )
    def _compute_stage_progress_json(self):
        stages = self.env['ctkm.stage'].search([])
        stages_by_name = {stage.name: stage for stage in stages}
        for program in self:
            mapping = {}
            progress_stage = False
            todo_stage = False
            last_stage = False
            stores_map = program._ctkm_step4_store_qty_map()
            sudo_tasks = program.sudo().task_ids
            lines = program.checklist_line_ids.sorted(
                lambda line: (line.sequence, line.id)
            )
            for line in lines:
                stage = line.stage_id
                if not stage and line.name:
                    stage = stages_by_name.get(line.name)
                if not stage:
                    continue
                state = line.state or 'todo'
                percent = program._ctkm_stage_work_percent(
                    stage, line, stores_map, sudo_tasks,
                )
                entry = {'state': state}
                if percent is not None:
                    entry['percent'] = percent
                mapping[str(stage.id)] = entry
                last_stage = stage
                if state == 'progress' and not progress_stage:
                    progress_stage = stage
                elif state == 'todo' and not todo_stage:
                    todo_stage = stage
            program.stage_progress_json = mapping
            program.checklist_current_stage_id = (
                progress_stage or todo_stage or last_stage
            )

    _CTKM_STORE_PERCENT_SEQUENCES = frozenset(range(10, 16))

    def _ctkm_step4_store_qty_map(self):
        """Cửa hàng + SL tem/tag từ file bước 4 (kho Tem/Tag), fallback bước In.

        Trả về ``{store_key: {'qty', 'tem', 'tag', 'keys'}}``. Mỗi cửa hàng
        một phần bằng nhau trên thanh trạng thái; SL dùng để cân trọng số.
        """
        self.ensure_one()
        from odoo.addons.ctkm_core.models.ctkm_task_tem_print_line import (
            classify_tem_tag_kinds,
            normalize_store_key,
        )
        Task = self.env['ctkm.task']
        result = {}

        def _bucket(store_key, store_name):
            key = store_key or normalize_store_key(store_name)
            if not key:
                return False
            canon = Task._ctkm_store_canonical_key(key, store_name) or key
            info = result.setdefault(canon, {
                'qty': 0.0,
                'tem': 0.0,
                'tag': 0.0,
                'keys': set(),
            })
            info['keys'].update(filter(None, (key, canon, normalize_store_key(store_name))))
            return canon

        if 'ctkm.inventory.tem.tag' in self.env:
            rows = self.env['ctkm.inventory.tem.tag'].sudo().search([
                ('program_id', '=', self.id),
            ])
            for rec in rows:
                bucket = _bucket(rec.store_key, rec.store)
                if not bucket:
                    continue
                amount = rec.quantity or 0.0
                result[bucket]['qty'] += amount
                kinds = classify_tem_tag_kinds(rec.tem_tag)
                if 'tag' in kinds:
                    result[bucket]['tag'] += amount
                if 'tem' in kinds or not kinds:
                    result[bucket]['tem'] += amount
        if result:
            return result

        print_lines = self.env['ctkm.task.tem.print.line'].sudo().search([
            ('program_id', '=', self.id),
        ])
        for line in print_lines:
            bucket = _bucket(line.store_key, line.store)
            if not bucket:
                continue
            tem = line.tem_quantity or 0.0
            tag = line.tag_quantity or 0.0
            result[bucket]['tem'] += tem
            result[bucket]['tag'] += tag
            result[bucket]['qty'] += tem + tag
        return result

    def _ctkm_match_store_bucket(self, stores_map, *values):
        """Khớp mã cửa hàng trên dòng công việc với bucket từ file bước 4."""
        if not stores_map:
            return False
        Task = self.env['ctkm.task']
        aliases = Task._ctkm_store_key_aliases(*values)
        if not aliases:
            return False
        for bucket, info in stores_map.items():
            if bucket in aliases or aliases & info.get('keys', set()):
                return bucket
        canon = Task._ctkm_store_canonical_key(*values)
        return canon if canon in stores_map else False

    def _ctkm_weighted_store_percent(self, stores_map, store_ratios):
        """50% theo số cửa hàng + 50% theo SL tem/tag. 10 CH xong 1 CH → 10%."""
        n = len(stores_map)
        if not n:
            return 0
        store_part = sum(store_ratios.get(key, 0.0) for key in stores_map) / n
        total_qty = sum(info['qty'] for info in stores_map.values())
        if total_qty > 0:
            qty_part = sum(
                store_ratios.get(key, 0.0) * stores_map[key]['qty']
                for key in stores_map
            ) / total_qty
        else:
            qty_part = store_part
        return int(round(100.0 * (0.5 * store_part + 0.5 * qty_part)))

    def _ctkm_group_lines_by_store(self, stores_map, lines, *key_fields):
        grouped = {key: [] for key in stores_map}
        for line in lines:
            values = [line[field] for field in key_fields if field in line._fields]
            bucket = self._ctkm_match_store_bucket(stores_map, *values)
            if bucket:
                grouped[bucket].append(line)
        return grouped

    def _ctkm_tick_qty_ratio(self, lines, tick_field, qty_field, qty_done_field=None):
        """Tỷ lệ 0–1: 50% số dòng đã tick + 50% sản lượng."""
        if not lines:
            return 0.0
        tick = sum(1.0 for line in lines if line[tick_field]) / len(lines)
        qty_total = sum(line[qty_field] or 0.0 for line in lines)
        if qty_done_field:
            qty_done = sum(line[qty_done_field] or 0.0 for line in lines)
        else:
            qty_done = sum(
                (line[qty_field] or 0.0) for line in lines if line[tick_field]
            )
        qty = (qty_done / qty_total) if qty_total else tick
        return 0.5 * tick + 0.5 * qty

    def _ctkm_stage_work_percent(self, stage, checklist_line, stores_map, tasks=None):
        """% công việc bước 10–15; bước khác trả về None."""
        sequence = stage.sequence or checklist_line.sequence or 0
        if sequence not in self._CTKM_STORE_PERCENT_SEQUENCES:
            return None
        if checklist_line.state == 'done':
            return 100
        if not stores_map:
            return 0
        tasks = tasks if tasks is not None else self.sudo().task_ids
        ratios = self._ctkm_stage_store_ratios(sequence, stores_map, tasks)
        return self._ctkm_weighted_store_percent(stores_map, ratios)

    def _ctkm_stage_store_ratios(self, sequence, stores_map, tasks):
        """Tỷ lệ hoàn thành 0–1 của từng cửa hàng, theo việc thật của bước."""
        empty = {key: 0.0 for key in stores_map}
        if sequence == 10:
            return self._ctkm_step10_store_ratios(tasks, stores_map) or empty
        if sequence == 11:
            lines = tasks.filtered('is_tem_receive_task').tem_tag_replace_ids
            grouped = self._ctkm_group_lines_by_store(
                stores_map, lines, 'store_key', 'store',
            )
            return {
                key: self._ctkm_tick_qty_ratio(
                    grouped[key], 'received', 'total_quantity',
                )
                for key in stores_map
            }
        if sequence == 12:
            lines = tasks.filtered('is_tem_replace_task').tem_tag_replace_ids
            grouped = self._ctkm_group_lines_by_store(
                stores_map, lines, 'store_key', 'store',
            )
            return {
                key: self._ctkm_tick_qty_ratio(
                    grouped[key], 'replaced_done', 'total_quantity',
                    'replaced_quantity',
                )
                for key in stores_map
            }
        if sequence == 13:
            lines = tasks.filtered('is_tem_photo_task').tem_photo_check_ids
            grouped = self._ctkm_group_lines_by_store(
                stores_map, lines, 'store_key', 'store',
            )
            return {
                key: self._ctkm_tick_qty_ratio(
                    grouped[key], 'photographed', 'total_quantity',
                )
                for key in stores_map
            }
        if sequence == 14:
            lines = tasks.filtered('is_tem_check_task').tem_photo_check_ids
            grouped = self._ctkm_group_lines_by_store(
                stores_map, lines, 'store_key', 'store',
            )
            return {
                key: self._ctkm_tick_qty_ratio(
                    grouped[key], 'confirmed', 'total_quantity',
                )
                for key in stores_map
            }
        if sequence == 15:
            return self._ctkm_step15_store_ratios(tasks, stores_map) or empty
        return empty

    def _ctkm_step10_store_ratios(self, tasks, stores_map):
        """Bàn giao 50% + thu hồi 50% (nếu có dòng thu); không có thu thì 100% giao."""
        handover_tasks = tasks.filtered('is_tem_handover_task')
        handover = handover_tasks.handover_store_ids
        collect = handover_tasks.collect_store_ids
        handover_g = self._ctkm_group_lines_by_store(
            stores_map, handover, 'store_key', 'store',
        )
        collect_g = self._ctkm_group_lines_by_store(
            stores_map, collect, 'store_key', 'store',
        )
        has_collect = bool(collect)
        ratios = {}
        for key in stores_map:
            h_lines = handover_g.get(key) or []
            if h_lines:
                handover_ratio = sum(1.0 for line in h_lines if line.done) / len(h_lines)
            else:
                handover_ratio = 0.0
            if not has_collect:
                ratios[key] = handover_ratio
                continue
            c_lines = collect_g.get(key) or []
            if c_lines:
                collect_ratio = sum(1.0 for line in c_lines if line.done) / len(c_lines)
            else:
                collect_ratio = 1.0
            ratios[key] = 0.5 * handover_ratio + 0.5 * collect_ratio
        return ratios

    def _ctkm_step15_store_ratios(self, tasks, stores_map):
        """ASM/KTDT (báo cáo) 50% + KT áp giá 50%."""
        lines = tasks.filtered('is_tem_price_task').price_store_ids
        grouped = self._ctkm_group_lines_by_store(
            stores_map, lines, 'store_key', 'store',
        )
        ratios = {}
        for key in stores_map:
            slines = grouped.get(key) or []
            if not slines:
                ratios[key] = 0.0
                continue
            reported = 1.0 if any(
                line.replaced or line.not_replaced for line in slines
            ) else 0.0
            applied = 1.0 if all(line.price_applied for line in slines) else (
                sum(1.0 for line in slines if line.price_applied) / len(slines)
            )
            ratios[key] = 0.5 * reported + 0.5 * applied
        return ratios

    def _ctkm_default_checklist_vals(self):
        stages = self.env['ctkm.stage'].search([], order='sequence, id')
        if stages:
            return [
                {
                    'stage_id': stage.id,
                    'sequence': stage.sequence,
                    'name': stage.name,
                    'state': 'todo',
                    'user_ids': [(6, 0, stage.user_ids.ids)],
                    'need_manager_confirm': stage.need_manager_confirm,
                    'verifier_ids': [(6, 0, stage.verifier_ids.ids)],
                }
                for stage in stages
            ]
        return [
            {'sequence': index, 'name': name, 'state': 'todo'}
            for index, name in enumerate([
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
            ], start=1)
        ]

    def _ctkm_sync_checklist_from_stages(self):
        """Đồng bộ 'Tiến độ thực hiện' của mỗi CTKM theo các bước (Giai đoạn) hiện tại.

        Mỗi bước trong 'Cấu hình -> Giai đoạn' sẽ tương ứng với một dòng checklist
        trong 'Tiến độ thực hiện' của từng chương trình (khớp theo stage_id, fallback
        theo tên). Tiến độ (state/done_date) của các dòng đã khớp được giữ nguyên.
        """
        Checklist = self.env['ctkm.program.checklist.line']
        stages = self.env['ctkm.stage'].search([], order='sequence, id')
        stage_ids = stages.ids
        for program in self:
            lines = program.checklist_line_ids
            by_stage = {line.stage_id.id: line for line in lines if line.stage_id}
            by_name = {}
            for line in lines:
                if not line.stage_id and line.name not in by_name:
                    by_name[line.name] = line

            to_unlink = self.env['ctkm.program.checklist.line']
            created = []
            for stage in stages:
                line = by_stage.get(stage.id)
                if not line and stage.name in by_name:
                    line = by_name.pop(stage.name)
                if line:
                    line.write({
                        'stage_id': stage.id,
                        'sequence': stage.sequence,
                        'name': stage.name,
                        'user_ids': [(6, 0, stage.user_ids.ids)],
                        'need_manager_confirm': stage.need_manager_confirm,
                        'verifier_ids': [(6, 0, stage.verifier_ids.ids)],
                    })
                else:
                    created.append({
                        'program_id': program.id,
                        'stage_id': stage.id,
                        'sequence': stage.sequence,
                        'name': stage.name,
                        'state': 'todo',
                        'user_ids': [(6, 0, stage.user_ids.ids)],
                        'need_manager_confirm': stage.need_manager_confirm,
                        'verifier_ids': [(6, 0, stage.verifier_ids.ids)],
                    })

            # Gỡ các dòng không còn tương ứng với giai đoạn nào.
            for line in lines:
                if line.stage_id and line.stage_id.id not in stage_ids:
                    to_unlink |= line
            for line in by_name.values():
                to_unlink |= line
            if to_unlink:
                to_unlink.unlink()
            if created:
                Checklist.create(created)
                program.ctkm_ensure_checklist_tasks()
        return True

    def _ctkm_ensure_checklist_lines(self):
        """Tạo các bước mặc định nếu chương trình chưa có checklist."""
        Checklist = self.env['ctkm.program.checklist.line']
        today = fields.Date.context_today(self)
        for program in self:
            if program.checklist_line_ids:
                continue
            vals_list = [
                {**vals, 'program_id': program.id}
                for vals in program._ctkm_default_checklist_vals()
            ]
            if vals_list:
                lines = Checklist.create(vals_list)
                for line in lines.sorted('sequence')[:3]:
                    # 3 bước đầu tự động xong khi tạo CTKM → không gửi thông báo giai đoạn.
                    line.with_context(ctkm_skip_stage_notify=True).write({
                        'state': 'done',
                        'done_date': today,
                    })
        return True

    def ctkm_ensure_checklist_tasks(self):
        """Đảm bảo mỗi bước checklist có người phụ trách thì có công việc tương ứng."""
        for program in self:
            for line in program.checklist_line_ids.filtered(lambda l: l.user_ids):
                line._ctkm_ensure_task()
        return True


    def action_reset_checklist_defaults(self):
        """Xóa checklist hiện tại và tạo lại các bước chuẩn."""
        self.ensure_one()
        self.checklist_line_ids.unlink()
        self._ctkm_ensure_checklist_lines()
        return True

    def action_open_notify_code_detail(self):
        """Mở trang chi tiết theo mã số thông báo (từ báo cáo pivot)."""
        self.ensure_one()
        return self._action_open_notify_code_detail(self.notify_code)

    @api.model
    def action_open_notify_code_detail_by_code(self, notify_code, domain=None):
        """Gọi từ JS pivot khi bấm mã số thông báo."""
        return self._action_open_notify_code_detail(notify_code, domain=domain)

    @api.model
    def _action_open_notify_code_detail(self, notify_code, domain=None):
        code = (notify_code or '').strip()
        program_domain = Domain(domain or [])
        if code:
            program_domain &= Domain('notify_code', '=', code)
        elif not program_domain:
            raise ValidationError(_('Thiếu mã số thông báo.'))

        programs = self.search(program_domain)
        if not code and programs:
            code = (programs[:1].notify_code or '').strip()
        if not code:
            raise ValidationError(_('Thiếu mã số thông báo.'))

        report = self.env['ctkm.notify.report'].sudo().get_or_create_for_code(code)
        form_view = self.env.ref(
            'ctkm_core.view_ctkm_notify_report_form',
            raise_if_not_found=False,
        )
        return {
            'type': 'ir.actions.act_window',
            'name': code,
            'res_model': 'ctkm.notify.report',
            'res_id': report.id,
            'view_mode': 'form',
            'views': [(form_view.id, 'form')] if form_view else [(False, 'form')],
            'target': 'current',
            'context': {'ctkm_notify_detail': True},
            # Đường dẫn rõ ràng, tránh kẹt URL list cũ notify.line
            'path': 'ctkm-notify-detail',
        }

    @api.constrains('badge_image')
    def _check_badge_image(self):
        for record in self:
            if not record.badge_image:
                continue
            raw = base64.b64decode(record.badge_image)
            mime = mimetypes.guess_mimetype(raw, default='') or ''
            if not mime.startswith('image/'):
                raise ValidationError(
                    _(
                        'Ảnh nền nhãn chỉ chấp nhận file ảnh (JPG, PNG...). '
                        'Để gửi PDF, Word hoặc Excel, hãy dùng mục "Tài liệu đính kèm".'
                    )
                )

    @api.constrains('notify_document_ids')
    def _check_notify_documents(self):
        for record in self:
            for attachment in record.notify_document_ids:
                filename = (attachment.name or '').lower()
                if '.' not in filename:
                    raise ValidationError(
                        _('Tài liệu đính kèm phải có phần mở rộng hợp lệ (PDF, Word, Excel).')
                    )
                extension = '.' + filename.rsplit('.', 1)[-1]
                if extension not in _CTKM_NOTIFY_DOC_EXTENSIONS:
                    raise ValidationError(
                        _('Chỉ chấp nhận tài liệu PDF, Word hoặc Excel: %s')
                        % attachment.name
                    )

    @api.model_create_multi
    def create(self, vals_list):
        programs = super().create(vals_list)
        programs._ctkm_link_notify_documents()
        programs._ctkm_ensure_checklist_lines()
        return programs

    def write(self, vals):
        res = super().write(vals)
        if 'notify_document_ids' in vals:
            self._ctkm_link_notify_documents()
        return res

    def _ctkm_link_notify_documents(self):
        for program in self:
            program.notify_document_ids.write({
                'res_model': program._name,
                'res_id': program.id,
            })

    @api.constrains('date_begin', 'date_end')
    def _check_closing_date(self):
        for record in self:
            if record.date_end < record.date_begin:
                raise ValidationError(_('Ngày kết thúc không thể trước ngày bắt đầu.'))
