# -*- coding: utf-8 -*-
"""ctkm.task.tem.tag.replace.line: TransientModel -> Model.

Bảng cũ là bảng tạm (transient) chứa các dòng rác của phiên làm việc trước.
Xóa sạch trước khi module dựng lại bảng "Chi tiết tem/tag" từ kho Tem/Tag.
"""


def migrate(cr, version):
    cr.execute(
        """
        SELECT 1
          FROM information_schema.tables
         WHERE table_name = 'ctkm_task_tem_tag_replace_line'
        """
    )
    if cr.fetchone():
        cr.execute('DELETE FROM ctkm_task_tem_tag_replace_line')
