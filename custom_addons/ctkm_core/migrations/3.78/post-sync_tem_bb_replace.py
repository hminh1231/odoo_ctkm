# -*- coding: utf-8 -*-


def migrate(cr, version):
    """Recompute step flags and rebuild Tem/Tag detail rows for step 6."""
    from odoo import SUPERUSER_ID, api

    env = api.Environment(cr, SUPERUSER_ID, {})
    tasks = env['ctkm.task'].search([], order='id')
    if tasks:
        tasks._compute_task_step_flags()

    if 'ctkm.inventory.tem.tag' not in env:
        return
    program_ids = env['ctkm.inventory.tem.tag'].search([]).mapped('program_id').ids
    if program_ids:
        env['ctkm.task']._ctkm_sync_tem_tag_lines_for_programs(program_ids)
