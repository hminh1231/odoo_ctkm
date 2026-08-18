# -*- coding: utf-8 -*-


def migrate(cr, version):
    """Rebuild task detail lines after adding CTKM notes from imported Tem/Tag."""
    from odoo import SUPERUSER_ID, api

    env = api.Environment(cr, SUPERUSER_ID, {})
    program_ids = env['ctkm.inventory.tem.tag'].search([]).mapped('program_id').ids
    if program_ids:
        env['ctkm.task']._ctkm_sync_tem_tag_lines_for_programs(program_ids)
