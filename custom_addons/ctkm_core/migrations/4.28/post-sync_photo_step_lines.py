# -*- coding: utf-8 -*-

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Bước 13/14: dựng bảng Đã chụp / Xác nhận thay từ file tổng."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    tasks = env['ctkm.task'].search([
        '|',
        ('is_tem_photo_task', '=', True),
        ('is_tem_check_task', '=', True),
    ])
    if tasks:
        tasks._ctkm_sync_tem_photo_lines()
