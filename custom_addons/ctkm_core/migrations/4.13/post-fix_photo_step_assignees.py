# -*- coding: utf-8 -*-

import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

_CHECK_STAGE_XMLID = 'ctkm_core.ctkm_stage_14'


def migrate(cr, version):
    """Đồng bộ lại người phụ trách của các bước bị ảnh hưởng bởi cơ chế gán tự động:

    - Bước 13 (Chụp team gửi lên group / chụp từng con tem): Phụ trách =
      Quản lý cửa hàng (hr.store.manager_id) của mọi Store trên biên bản bước 4.
    - Bước 14 (Kiểm tra hình ảnh tem tag): gỡ bỏ Cửa hàng trưởng từng được gán
      tự động bởi cơ chế cũ (11–14), giữ nguyên những người phụ trách khác.

    Chỉ xử lý các CTKM đã hoàn thành bước 4 (đổ BB) – nơi cơ chế cũ từng chạy.
    Mỗi chương trình được xử lý độc lập; lỗi trên một chương trình không làm dừng
    migration của các chương trình còn lại.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    Task = env['ctkm.task']
    import_tasks = Task.search([
        ('is_tem_tag_import_task', '=', True),
        ('state', '=', 'done'),
    ])
    for task in import_tasks:
        program = task.program_id
        if not program:
            continue
        try:
            store_keys = task._ctkm_bb_store_keys()
        except Exception as exc:
            _logger.warning(
                'CTKM 4.13 migration: bỏ qua CTKM %s (bb store keys): %s',
                program.id, exc,
            )
            continue

        # Bước 13: Phụ trách = Quản lý cửa hàng của các Store trên biên bản.
        try:
            task._ctkm_assign_photo_store_managers_after_bb_import()
        except Exception as exc:
            _logger.warning(
                'CTKM 4.13 migration: lỗi gán bước 13 CTKM %s: %s',
                program.id, exc,
            )

        # Bước 14: gỡ Cửa hàng trưởng tự động, giữ người phụ trách khác (nếu có).
        if store_keys:
            try:
                store_mgr_users = task._ctkm_find_store_manager_users(store_keys)
                if store_mgr_users:
                    check_stage_id = task._ctkm_step_stage_id(_CHECK_STAGE_XMLID)
                    check_lines = program.checklist_line_ids.filtered(
                        lambda l: l.stage_id
                        and l.stage_id.id == check_stage_id
                        and l.state != 'done'
                    )
                    for line in check_lines:
                        remaining = line.user_ids - store_mgr_users
                        if remaining.ids != line.user_ids.ids:
                            line.sudo().write({'user_ids': [(6, 0, remaining.ids)]})
            except Exception as exc:
                _logger.warning(
                    'CTKM 4.13 migration: lỗi gỡ bước 14 CTKM %s: %s',
                    program.id, exc,
                )
