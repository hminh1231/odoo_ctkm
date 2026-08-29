# -*- coding: utf-8 -*-

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """ASM theo cột Đã thay bước 12; bỏ tick KT áp giá khi chưa đủ ASM + KTDT."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    price_tasks = env['ctkm.task'].search([('is_tem_price_task', '=', True)])
    if price_tasks:
        price_tasks._ctkm_sync_price_lines()
