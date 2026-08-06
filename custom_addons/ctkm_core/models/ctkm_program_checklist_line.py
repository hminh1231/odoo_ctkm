# -*- coding: utf-8 -*-

from odoo import api, fields, models

# 19 bước chuẩn quy trình CTKM (theo bảng công việc).
CTKM_CHECKLIST_DEFAULT_STEPS = [
    'MKT lập CTKM và duyệt chương trình với BGĐ',
    'Duyệt CTKM',
    'Lập thông báo CTKM, trình ký',
    'Phát hành thông báo CTKM đến các bộ phận',
    'Đổ BB thay tem/tag (file tổng)',
    'Khai báo CTKM áp giá trên PM Linkq',
    'Lập BB thay tem, bàn giao cho KT kho; Kiểm tra BB thay tem tag',
    'Thiết kế mẫu tem/tag, Bảng nhận diện',
    'KT áp giá',
    'In tem, Tag',
    'Bàn giao Tem Tag cho CH; Thu hồi tem tag cũ',
    'Nhận tem tag mới',
    'Thay tem Tag',
    'Chụp tem gửi lên group / chụp từng con tem',
    'Kiểm tra hình ảnh tem tag',
    'Kế toán áp giá CTKM lên PM Link Q; Lập báo cáo cửa hàng đã thay tem tag / chưa thay tem / đã áp giá',
    'Hậu kiểm CTKM; Giám sát đi kiểm tra thay tem',
    'KTDT lập biên bản phạt nếu phát hiện gian lận, sai sót',
    'Tổng hợp báo cáo',
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
