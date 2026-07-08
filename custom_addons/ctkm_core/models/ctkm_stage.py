# -*- coding: utf-8 -*-

from odoo import fields, models


class CtkmStage(models.Model):
    _name = 'ctkm.stage'
    _description = 'Giai đoạn chương trình khuyến mãi'
    _order = 'sequence, id'

    name = fields.Char(string='Tên giai đoạn', required=True, translate=True)
    sequence = fields.Integer(string='Thứ tự', default=10)
    description = fields.Text(string='Mô tả')
    pipe_end = fields.Boolean(string='Kết thúc')
    fold = fields.Boolean(string='Gộp')
