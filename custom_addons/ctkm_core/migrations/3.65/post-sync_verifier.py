# -*- coding: utf-8 -*-

def migrate(cr, version):
    """Đồng bộ Người kiểm soát (verifier_id) từ bước checklist sang công việc.

    Trước khi sửa trigger write của checklist line, thay đổi verifier_id trên bước
    không được đẩy sang task -> một số task vẫn gửi xác nhận cho quản lý org-chart
    dù đã cấu hình Người kiểm soát. Migration này sửa dữ liệu cũ.
    """
    cr.execute("""
        UPDATE ctkm_task t
        SET verifier_id = c.verifier_id
        FROM ctkm_program_checklist_line c
        WHERE t.checklist_line_id = c.id
          AND t.verifier_id IS DISTINCT FROM c.verifier_id
    """)
