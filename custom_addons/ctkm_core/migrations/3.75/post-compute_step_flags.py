# -*- coding: utf-8 -*-

from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    """Tính lại các cờ bước công việc (có thêm is_tem_bb_replace_task cho bước 6)."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    tasks = env['ctkm.task'].search([], order='id')
    if tasks:
        tasks._compute_task_step_flags()
