# -*- coding: utf-8 -*-

from odoo import api, fields, models


class CtkmTaskTemTagRecoverLine(models.Model):
    """Dòng "Thu hồi tem" của bước 10 (Bàn giao Tem Tag / Thu hồi tem tag cũ).

    Mỗi dòng chọn một Chương trình khuyến mãi và các Tem/Tag (bản ghi kho
    ``ctkm.inventory.tem.tag``) cần thu hồi. Khi công việc bước này bấm
    <b>Hoàn thành</b>, các Tem/Tag đã chọn sẽ bị xóa khỏi "Kho" của ứng dụng.

    Các Tem/Tag được lưu bằng danh sách id (Json) thay vì many2many cứng, để
    module này không phụ thuộc load-order vào module kho Tem/Tag.
    """

    _name = 'ctkm.task.tem.tag.recover.line'
    _description = 'Thu hồi tem/tag của công việc'
    _rec_name = 'program_id'
    _order = 'id'

    task_id = fields.Many2one(
        'ctkm.task',
        string='Công việc',
        required=True,
        ondelete='cascade',
        index=True,
    )
    program_id = fields.Many2one(
        'ctkm.program',
        string='Chương trình khuyến mãi',
        required=True,
        ondelete='cascade',
    )
    tem_tag_ids = fields.Json(
        string='Tem/Tag',
        help='Danh sách id các Tem/Tag cần thu hồi (sẽ bị xóa khỏi Kho khi Hoàn thành).',
    )

    def _ctkm_tem_tag_records(self):
        """Trả về recordset ctkm.inventory.tem.tag từ danh sách id (nếu module có)."""
        if 'ctkm.inventory.tem.tag' not in self.env:
            return self.env['ctkm.inventory.tem.tag']
        ids = []
        for line in self.sudo():
            for item in (line.tem_tag_ids or []) or []:
                if isinstance(item, int) and item not in ids:
                    ids.append(item)
        return self.env['ctkm.inventory.tem.tag'].sudo().browse(ids)

    def _ctkm_recover_inventory(self):
        """Xóa các Tem/Tag đã chọn khỏi Kho Tem/Tag của ứng dụng."""
        if 'ctkm.inventory.tem.tag' not in self.env:
            return self.env['ctkm.inventory.tem.tag']
        records = self._ctkm_tem_tag_records()
        if records:
            records.with_context(ctkm_tem_tag_line_sync=True).unlink()
        return records
