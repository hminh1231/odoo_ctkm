# -*- coding: utf-8 -*-

from odoo import api, fields, models


class CtkmProgramDetailLine(models.Model):
    _name = 'ctkm.program.detail.line'
    _description = 'Chi tiết chương trình khuyến mãi'
    _order = 'sequence, id'

    program_id = fields.Many2one(
        'ctkm.program', string='Chương trình', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(string='STT', default=10)
    stt = fields.Integer(string='STT', compute='_compute_stt')
    notification_date = fields.Date(string='NGÀY NHẬN THÔNG BÁO')
    notification_file = fields.Char(string='File thông báo')
    store_code_id = fields.Many2one('hr.store.code', string='cửa hàng')

    responsible_employee_id = fields.Many2one('hr.employee', string='Người phụ trách')
    allocated_time = fields.Char(string='Định biên giờ')
    processing_date = fields.Date(string='Ngày xử lý')
    work_content = fields.Char(string='Nội dung CV')
    excel_file_status = fields.Selection(
        [
            ('not_processed', 'Chưa xử lý'),
            ('processed', 'Đã xử lý'),
        ],
        string='file EXcel',
        default='not_processed',
    )
    completion_date = fields.Date(string='Ngày hoàn thành')
    result_ok = fields.Boolean(string='Kết quả')
    manager_confirmed = fields.Boolean(string='Xác nhận quản lý')
    result_note = fields.Char(string='Kết quả')
    support_request = fields.Text(string='yêu cầu hỗ trợ')

    product_name = fields.Char(string='TÊN SP')
    quantity = fields.Float(string='SỐ LƯỢNG', default=1.0)
    tag_confirmed = fields.Boolean(string='Xác nhận tem/tag')
    receive_status = fields.Selection(
        [
            ('not_received', 'Chưa nhận'),
            ('received', 'Đã nhận'),
        ],
        string='Trạng thái',
        default='not_received',
    )
    confirmation_note = fields.Char(string='Xác nhận')
    processing_status = fields.Char(string='Trạng thái')
    note = fields.Text(string='Ghi chú')

    @api.depends('sequence')
    def _compute_stt(self):
        lines = self.sorted('sequence')
        for index, line in enumerate(lines, start=1):
            line.stt = index


class CtkmProgramApproverDetailLine(models.Model):
    _name = 'ctkm.program.approver.detail.line'
    _description = 'Dòng chi tiết CTKM cho approver'
    _order = 'sequence, id'

    program_id = fields.Many2one(
        'ctkm.program', string='Chương trình', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(string='STT', default=10)
    stt = fields.Integer(string='STT', compute='_compute_stt')
    notification_date = fields.Date(string='NGÀY NHẬN THÔNG BÁO')
    notification_file = fields.Char(string='File thông báo')
    store_code_id = fields.Many2one('hr.store.code', string='cửa hàng')
    responsible_employee_id = fields.Many2one('hr.employee', string='Người phụ trách')
    allocated_time = fields.Char(string='Định biên giờ')
    processing_date = fields.Date(string='Ngày xử lý')
    work_content = fields.Char(string='Nội dung CV')
    excel_file_status = fields.Selection(
        [
            ('not_processed', 'Chưa xử lý'),
            ('processed', 'Đã xử lý'),
        ],
        string='file EXcel',
        default='not_processed',
    )
    completion_date = fields.Date(string='Ngày hoàn thành')
    result_ok = fields.Boolean(string='Kết quả')
    manager_confirmed = fields.Boolean(string='Xác nhận quản lý')
    result_note = fields.Char(string='Kết quả')
    support_request = fields.Text(string='yêu cầu hỗ trợ')

    @api.depends('program_id.approver_detail_line_ids.sequence', 'sequence')
    def _compute_stt(self):
        for program in self.mapped('program_id'):
            for index, line in enumerate(program.approver_detail_line_ids.sorted('sequence'), start=1):
                line.stt = index
        for line in self.filtered(lambda line: not line.program_id):
            line.stt = 0


class CtkmProgramStoreDetailLine(models.Model):
    _name = 'ctkm.program.store.detail.line'
    _description = 'Dòng chi tiết CTKM cho cửa hàng'
    _order = 'sequence, id'

    program_id = fields.Many2one(
        'ctkm.program', string='Chương trình', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(string='STT', default=10)
    stt = fields.Integer(string='STT', compute='_compute_stt')
    notification_date = fields.Date(string='NGÀY NHẬN THÔNG BÁO')
    notification_file = fields.Char(string='File thông báo')
    store_code_id = fields.Many2one('hr.store.code', string='cửa hàng')
    product_name = fields.Char(string='TÊN SP')
    quantity = fields.Float(string='SỐ LƯỢNG', default=1.0)
    tag_confirmed = fields.Boolean(string='Xác nhận tem/tag')
    receive_status = fields.Selection(
        [
            ('not_received', 'Chưa nhận'),
            ('received', 'Đã nhận'),
        ],
        string='Trạng thái',
        default='not_received',
    )
    confirmation_note = fields.Char(string='Xác nhận')
    processing_status = fields.Char(string='Trạng thái')
    note = fields.Text(string='Ghi chú')

    @api.depends('program_id.store_detail_line_ids.sequence', 'sequence')
    def _compute_stt(self):
        for program in self.mapped('program_id'):
            for index, line in enumerate(program.store_detail_line_ids.sorted('sequence'), start=1):
                line.stt = index
        for line in self.filtered(lambda line: not line.program_id):
            line.stt = 0
