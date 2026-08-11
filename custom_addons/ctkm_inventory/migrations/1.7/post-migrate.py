# -*- coding: utf-8 -*-
"""Chuyển cờ 'Đã thay' (boolean) sang 'SL đã thay' (số lượng).

Các dòng đã được đánh dấu đã thay trước đây coi như đã thay đủ số lượng.
Sau đó dựng lại bảng "Chi tiết tem/tag" cho các công việc bước 4 / bước 12.
"""


def migrate(cr, version):
    from odoo import SUPERUSER_ID, api

    cr.execute(
        """
        UPDATE ctkm_inventory_tem_tag
           SET replaced_quantity = COALESCE(quantity, 0.0)
         WHERE replaced IS TRUE
           AND COALESCE(replaced_quantity, 0.0) = 0.0
        """
    )

    env = api.Environment(cr, SUPERUSER_ID, {})
    cr.execute(
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_name = 'ctkm_task'
           AND column_name = 'is_tem_tag_import_task'
        """
    )
    if not cr.fetchone():
        # ctkm_core chưa được nâng cấp (chạy -u ctkm_core,ctkm_inventory).
        return
    program_ids = env['ctkm.inventory.tem.tag'].search([]).mapped('program_id').ids
    if program_ids:
        env['ctkm.task']._ctkm_sync_tem_tag_lines_for_programs(program_ids)
