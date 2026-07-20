# -*- coding: utf-8 -*-

from odoo import api, fields, models


class CtkmNotifyReport(models.Model):
    _name = 'ctkm.notify.report'
    _description = 'Báo cáo chi tiết mã thông báo'
    _rec_name = 'notify_code'
    _order = 'notify_code, id'

    notify_code = fields.Char(string='Mã số thông báo', required=True, index=True)
    line_ids = fields.Many2many(
        'ctkm.program.notify.line',
        compute='_compute_line_ids',
        string='Chi tiết phạm vi',
    )
    program_ids = fields.Many2many(
        'ctkm.program',
        compute='_compute_line_ids',
        string='Chương trình',
    )

    # BẢNG BÁO CÁO TEM — số liệu để trống, gắn thuật toán sau
    tem_qty_need = fields.Char(string='TEM — Tổng CH SL cần làm BB')
    tem_qty_done = fields.Char(string='TEM — Tổng SL đã làm')
    tem_qty_pending = fields.Char(string='TEM — Tổng SL chưa làm')

    # BẢNG BÁO CÁO TAG — số liệu để trống, gắn thuật toán sau
    tag_qty_need = fields.Char(string='TAG — Tổng CH SL cần làm BB')
    tag_qty_done = fields.Char(string='TAG — Tổng SL đã làm')
    tag_qty_pending = fields.Char(string='TAG — Tổng SL chưa làm')

    _notify_code_uniq = models.Constraint(
        'UNIQUE(notify_code)',
        'Mã số thông báo đã có báo cáo chi tiết.',
    )

    @api.depends('notify_code')
    def _compute_line_ids(self):
        Program = self.env['ctkm.program']
        for report in self:
            if not report.notify_code:
                report.program_ids = Program
                report.line_ids = self.env['ctkm.program.notify.line']
                continue
            programs = Program.search([('notify_code', '=', report.notify_code)])
            report.program_ids = programs
            report.line_ids = programs.notify_line_ids

    @api.model
    def get_or_create_for_code(self, notify_code):
        code = (notify_code or '').strip()
        if not code:
            return self.browse()
        report = self.search([('notify_code', '=', code)], limit=1)
        if not report:
            report = self.create({'notify_code': code})
        return report
