# -*- coding: utf-8 -*-


def migrate(cr, version):
    """Dựng lại bảng Chi tiết tem/tag cho bước 11/12 (đủ mọi store file tổng)."""
    from odoo import SUPERUSER_ID, api

    env = api.Environment(cr, SUPERUSER_ID, {})
    if 'ctkm.inventory.tem.tag' not in env:
        return
    program_ids = env['ctkm.inventory.tem.tag'].search([]).mapped('program_id').ids
    if program_ids:
        env['ctkm.task']._ctkm_sync_tem_tag_lines_for_programs(program_ids)
