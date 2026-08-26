# -*- coding: utf-8 -*-


def migrate(cr, version):
    """Bước 11/12: dựng lại bảng Chi tiết tem/tag với mọi store của file tổng."""
    from odoo import SUPERUSER_ID, api

    env = api.Environment(cr, SUPERUSER_ID, {})
    if 'ctkm.inventory.tem.tag' not in env:
        return
    program_ids = env['ctkm.inventory.tem.tag'].search([]).mapped('program_id').ids
    if program_ids:
        env['ctkm.task']._ctkm_sync_tem_tag_lines_for_programs(program_ids)
