# -*- coding: utf-8 -*-

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Tính cờ bước Hậu kiểm và dựng bảng cửa hàng từ bước In tem, Tag."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    tasks = env['ctkm.task'].search([])
    if tasks:
        tasks._compute_task_step_flags()
    postcheck = env['ctkm.task'].search([('is_tem_postcheck_task', '=', True)])
    if postcheck:
        postcheck._ctkm_sync_postcheck_lines()
