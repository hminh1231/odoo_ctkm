# -*- coding: utf-8 -*-

from odoo import SUPERUSER_ID, api


_CTKM_DISPATCH_CHAIN = (
    (10, 'is_tem_handover_task'),
    (11, 'is_tem_receive_task'),
    (12, 'is_tem_replace_task'),
    (13, 'is_tem_photo_task'),
    (14, 'is_tem_check_task'),
    (15, 'is_tem_price_task'),
    (16, 'is_tem_postcheck_task'),
)


def migrate(cr, version):
    """Giữ cửa hàng đã có trên bước sau: đánh dấu đã gửi để không bị xóa khi lọc."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    Dispatch = env['ctkm.task.store.dispatch']
    Task = env['ctkm.task']
    programs = env['ctkm.program'].search([])
    for program in programs:
        tasks_by_rank = {}
        for rank, flag in _CTKM_DISPATCH_CHAIN:
            task = Task.search([
                ('program_id', '=', program.id),
                (flag, '=', True),
            ], order='id desc', limit=1)
            if task:
                tasks_by_rank[rank] = task
        for rank in range(10, 16):
            current = tasks_by_rank.get(rank)
            if not current:
                continue
            next_task = tasks_by_rank.get(rank + 1)
            keys = set()
            if next_task:
                keys.update(next_task._ctkm_existing_line_store_keys())
            if current.state == 'done':
                keys.update(current._ctkm_existing_line_store_keys())
            existing = set(current.store_dispatch_ids.mapped('store_key'))
            to_create = []
            for key in keys:
                canon = current._ctkm_dispatch_store_key(key) or key
                if not canon or canon in existing:
                    continue
                existing.add(canon)
                to_create.append({
                    'task_id': current.id,
                    'store_key': canon,
                    'store_label': current._ctkm_store_label_for_key(canon) or canon,
                    'state': 'sent',
                })
            if to_create:
                Dispatch.create(to_create)
