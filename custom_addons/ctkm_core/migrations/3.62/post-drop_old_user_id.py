# -*- coding: utf-8 -*-


def _has_column(cr, table, column):
    cr.execute(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
        """,
        (table, column),
    )
    return bool(cr.fetchone())


def _has_table(cr, table):
    cr.execute("SELECT to_regclass(%s)", ('public.%s' % table,))
    return bool(cr.fetchone()[0])


def migrate(cr, version):
    """Copy nốt user_id nếu cột còn, rồi xóa cột Many2one cũ."""
    if _has_column(cr, 'ctkm_stage', 'user_id') and _has_table(cr, 'ctkm_stage_user_rel'):
        cr.execute("""
            INSERT INTO ctkm_stage_user_rel (stage_id, user_id)
            SELECT id, user_id FROM ctkm_stage WHERE user_id IS NOT NULL
            ON CONFLICT DO NOTHING
        """)
    if (
        _has_column(cr, 'ctkm_program_checklist_line', 'user_id')
        and _has_table(cr, 'ctkm_checklist_line_user_rel')
    ):
        cr.execute("""
            INSERT INTO ctkm_checklist_line_user_rel (line_id, user_id)
            SELECT id, user_id FROM ctkm_program_checklist_line WHERE user_id IS NOT NULL
            ON CONFLICT DO NOTHING
        """)
    if _has_column(cr, 'ctkm_task', 'user_id') and _has_table(cr, 'ctkm_task_user_rel'):
        cr.execute("""
            INSERT INTO ctkm_task_user_rel (task_id, user_id)
            SELECT id, user_id FROM ctkm_task WHERE user_id IS NOT NULL
            ON CONFLICT DO NOTHING
        """)
    for tbl, col in (
        ('ctkm_stage', 'user_id'),
        ('ctkm_program_checklist_line', 'user_id'),
        ('ctkm_task', 'user_id'),
    ):
        if _has_column(cr, tbl, col):
            cr.execute('ALTER TABLE "%s" DROP COLUMN IF EXISTS "%s" CASCADE' % (tbl, col))
