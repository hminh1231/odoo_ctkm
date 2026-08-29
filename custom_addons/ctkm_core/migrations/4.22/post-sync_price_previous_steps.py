# -*- coding: utf-8 -*-

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Đồng bộ ASM / KTDT / KT áp giá bước 15 từ dữ liệu bước trước."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    price_tasks = env['ctkm.task'].search([('is_tem_price_task', '=', True)])
    if price_tasks:
        price_tasks._ctkm_sync_price_lines()
