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


def migrate(cr, version):
    """Gộp task trùng và copy user_id → bảng Many2many (chạy TRƯỚC khi schema bỏ cột)."""
    if not _has_column(cr, 'ctkm_task', 'user_id'):
        return

    cr.execute("""
        CREATE TABLE IF NOT EXISTS ctkm_task_user_rel (
            task_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            PRIMARY KEY (task_id, user_id)
        )
    """)
    cr.execute(
        "CREATE INDEX IF NOT EXISTS ctkm_task_user_rel_user_id_idx "
        "ON ctkm_task_user_rel (user_id)"
    )
    cr.execute("""
        CREATE TABLE IF NOT EXISTS ctkm_stage_user_rel (
            stage_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            PRIMARY KEY (stage_id, user_id)
        )
    """)
    cr.execute("""
        CREATE TABLE IF NOT EXISTS ctkm_checklist_line_user_rel (
            line_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            PRIMARY KEY (line_id, user_id)
        )
    """)

    cr.execute("""
        SELECT program_id, notify_line_id, checklist_line_id,
               array_agg(id ORDER BY id) AS ids
        FROM ctkm_task
        GROUP BY program_id, notify_line_id, checklist_line_id
        HAVING count(*) > 1
    """)
    for _program_id, _notify_line_id, _checklist_line_id, ids in cr.fetchall():
        ids = list(ids)
        primary = ids[0]
        others = ids[1:]
        cr.execute(
            "SELECT DISTINCT user_id FROM ctkm_task "
            "WHERE id = ANY(%s) AND user_id IS NOT NULL",
            (ids,),
        )
        user_ids = [row[0] for row in cr.fetchall()]
        for uid in user_ids:
            cr.execute(
                "INSERT INTO ctkm_task_user_rel (task_id, user_id) VALUES (%s, %s) "
                "ON CONFLICT DO NOTHING",
                (primary, uid),
            )
        cr.execute("DELETE FROM ctkm_task WHERE id = ANY(%s)", (others,))

    cr.execute("""
        INSERT INTO ctkm_task_user_rel (task_id, user_id)
        SELECT id, user_id FROM ctkm_task WHERE user_id IS NOT NULL
        ON CONFLICT DO NOTHING
    """)
    if _has_column(cr, 'ctkm_stage', 'user_id'):
        cr.execute("""
            INSERT INTO ctkm_stage_user_rel (stage_id, user_id)
            SELECT id, user_id FROM ctkm_stage WHERE user_id IS NOT NULL
            ON CONFLICT DO NOTHING
        """)
    if _has_column(cr, 'ctkm_program_checklist_line', 'user_id'):
        cr.execute("""
            INSERT INTO ctkm_checklist_line_user_rel (line_id, user_id)
            SELECT id, user_id FROM ctkm_program_checklist_line WHERE user_id IS NOT NULL
            ON CONFLICT DO NOTHING
        """)
