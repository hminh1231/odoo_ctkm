# -*- coding: utf-8 -*-

from odoo import fields, models


class CtkmTag(models.Model):
    _name = 'ctkm.tag'
    _description = 'Nhãn chương trình khuyến mãi'

    name = fields.Char(string='Tên nhãn', required=True, translate=True)
    color = fields.Integer(string='Màu sắc')
