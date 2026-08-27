# -*- coding: utf-8 -*-

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Tính cờ bước Kế toán áp giá và dựng bảng cửa hàng từ bước In tem, Tag."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    tasks = env['ctkm.task'].search([])
    if tasks:
        tasks._compute_task_step_flags()
    price_tasks = env['ctkm.task'].search([('is_tem_price_task', '=', True)])
    if price_tasks:
        price_tasks._ctkm_sync_price_lines()
