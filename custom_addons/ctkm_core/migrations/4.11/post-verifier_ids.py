# -*- coding: utf-8 -*-


def migrate(cr, version):
    """Chuyển verifier_id (Many2one) sang verifier_ids (Many2many hr.employee).

    Sau khi đổi kiểu trường, Odoo tạo bảng quan hệ mới và tạm giữ lại cột
    verifier_id cũ (chưa dọn). Migration này copy dữ liệu cũ sang bảng quan
    hệ tương ứng để không mất Người kiểm soát đã cấu hình.
    """
    _copy_column_to_rel(
        cr, 'ctkm_stage', 'verifier_id',
        'ctkm_stage_verifier_rel', 'stage_id', 'employee_id',
    )
    _copy_column_to_rel(
        cr, 'ctkm_program_checklist_line', 'verifier_id',
        'ctkm_checklist_line_verifier_rel', 'line_id', 'employee_id',
    )
    _copy_column_to_rel(
        cr, 'ctkm_task', 'verifier_id',
        'ctkm_task_verifier_rel', 'task_id', 'employee_id',
    )


def _copy_column_to_rel(cr, table, column, rel_table, src_col, dst_col):
    cr.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name=%s AND column_name=%s",
        (table, column),
    )
    if not cr.fetchone():
        return
    cr.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_name=%s",
        (rel_table,),
    )
    if not cr.fetchone():
        return
    cr.execute(
        "INSERT INTO %(rel)s (%(src)s, %(dst)s) "
        "SELECT t.id, t.%(col)s FROM %(tbl)s t "
        "WHERE t.%(col)s IS NOT NULL "
        "  AND NOT EXISTS ("
        "    SELECT 1 FROM %(rel)s r "
        "    WHERE r.%(src)s = t.id AND r.%(dst)s = t.%(col)s)"
        % {
            'rel': rel_table,
            'src': src_col,
            'dst': dst_col,
            'tbl': table,
            'col': column,
        }
    )
