# -*- coding: utf-8 -*-

from odoo import api, fields, models


class CtkmTaskTimeLine(models.Model):
    """Dòng thời gian trên tab Chi tiết công việc."""

    _name = 'ctkm.task.time.line'
    _description = 'Thời gian công việc CTKM'
    _order = 'sequence, id'

    task_id = fields.Many2one(
        'ctkm.task',
        string='Công việc',
        required=True,
        ondelete='cascade',
        index=True,
    )
    sequence = fields.Integer(string='STT', default=10)
    name = fields.Char(string='Nội dung')
    date_start = fields.Date(
        string='Ngày bắt đầu',
        default=fields.Date.context_today,
    )
    date_end = fields.Date(string='Ngày hoàn thành')
    total_days = fields.Integer(
        string='Tổng số ngày',
        compute='_compute_total_days',
        store=True,
    )
    total_days_display = fields.Char(
        string='Tổng số ngày',
        compute='_compute_total_days_display',
    )
    is_main = fields.Boolean(
        string='Dòng chính',
        default=False,
        help='Dòng tạo sẵn từ công việc; Hoàn thành sẽ điền ngày hoàn thành.',
    )

    @api.depends('date_start', 'date_end')
    def _compute_total_days(self):
        for line in self:
            if line.date_start and line.date_end:
                line.total_days = max(0, (line.date_end - line.date_start).days)
            else:
                line.total_days = 0

    @api.depends('total_days')
    def _compute_total_days_display(self):
        for line in self:
            line.total_days_display = '%s ngày' % (line.total_days or 0)
