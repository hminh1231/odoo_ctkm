# -*- coding: utf-8 -*-

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Chỉ đổ cửa hàng xuống bước kế tiếp của những lần đã Gửi dữ liệu."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    Task = env['ctkm.task']
    synced = Task.browse()
    for task in Task.search([('store_dispatch_ids', '!=', False)]):
        rank = task._ctkm_dispatch_rank()
        if rank < 10:
            continue
        nxt = task._ctkm_program_task_by_rank(rank + 1)
        if not nxt or nxt in synced:
            continue
        nxt._ctkm_sync_after_upstream_dispatch()
        line = nxt.checklist_line_id
        if line and line.state == 'todo' and line.user_ids:
            line.with_context(ctkm_task_sync=True).write({'state': 'progress'})
        synced |= nxt
