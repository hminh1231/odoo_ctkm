# -*- coding: utf-8 -*-

def migrate(cr, version):
    """Gộp các công việc trùng (program_id, notify_line_id, checklist_line_id) thành
    1 công việc chia sẻ trước khi ràng buộc UNIQUE mới được tạo (chạy sau pre-migration).

    Mỗi bước giờ là 1 công việc chung cho nhiều người nhận việc, nên các công việc
    cũ (mỗi người 1 task cùng 1 bước) phải được gộp: giữ task có id nhỏ nhất, xóa các
    task trùng, và đưa TẤT CẢ user_id cũ vào bảng quan hệ user_ids của task được giữ.
    """
    # Tạo sẵn bảng quan hệ user_ids (Odoo sẽ bỏ qua vì đã tồn tại khi cập nhật schema).
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
