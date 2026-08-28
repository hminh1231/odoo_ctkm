# -*- coding: utf-8 -*-

import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Đồng bộ Người kiểm soát (Quản lý cửa hàng) cho bước 10 'Bàn giao Tem Tag /
    Thu hồi tem tag cũ' theo từng cửa hàng trên biên bản bước 4.

    Cơ chế này trước chỉ áp dụng bước 11–12. Migration chạy cho mọi CTKM đã hoàn
    thành bước 4 (đổ BB) để tạo lại ctkm.task.store.verifier (no_assignee) cho
    các công việc bước 10 đang mở, đồng nhất với bước 11–12.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    import_tasks = env['ctkm.task'].search([
        ('is_tem_tag_import_task', '=', True),
        ('state', '=', 'done'),
    ])
    for task in import_tasks:
        program = task.program_id
        if not program:
            continue
        try:
            task._ctkm_assign_store_managers_verifier_after_bb_import()
        except Exception as exc:
            _logger.warning(
                'CTKM 4.19 migration: lỗi gán verifier bước 10 CTKM %s: %s',
                program.id, exc,
            )
