# -*- coding: utf-8 -*-

def migrate(cr, version):
    """Copy dữ liệu từ cột Many2one user_id cũ sang bảng Many2many user_ids mới.

    Chạy ở post-migration: các bảng quan hệ (ctkm_stage_user_rel,
    ctkm_checklist_line_user_rel, ctkm_task_*) đã được tạo bởi cập nhật schema.
    """
    cr.execute("""
        INSERT INTO ctkm_stage_user_rel (stage_id, user_id)
        SELECT id, user_id FROM ctkm_stage WHERE user_id IS NOT NULL
        ON CONFLICT DO NOTHING
    """)
    cr.execute("""
        INSERT INTO ctkm_checklist_line_user_rel (line_id, user_id)
        SELECT id, user_id FROM ctkm_program_checklist_line WHERE user_id IS NOT NULL
        ON CONFLICT DO NOTHING
    """)
    cr.execute("""
        INSERT INTO ctkm_task_user_rel (task_id, user_id)
        SELECT id, user_id FROM ctkm_task WHERE user_id IS NOT NULL
        ON CONFLICT DO NOTHING
    """)
    # Xóa cột Many2one cũ (đã thay bằng user_ids).
    for tbl, col in (
        ('ctkm_stage', 'user_id'),
        ('ctkm_program_checklist_line', 'user_id'),
        ('ctkm_task', 'user_id'),
    ):
        cr.execute(
            'ALTER TABLE "%s" DROP COLUMN IF EXISTS "%s" CASCADE' % (tbl, col)
        )
