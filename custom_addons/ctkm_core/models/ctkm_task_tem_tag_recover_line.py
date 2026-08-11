# -*- coding: utf-8 -*-

from odoo import api, fields, models


class CtkmTaskTemTagRecoverLine(models.Model):
    """Dòng "Thu hồi tem" của bước 10 (Bàn giao Tem Tag / Thu hồi tem tag cũ).

    Mỗi dòng chọn một Chương trình khuyến mãi và các Tem/Tag (bản ghi kho
    ``ctkm.inventory.tem.tag``) cần thu hồi. Khi công việc bước này bấm
    <b>Hoàn thành</b>, các Tem/Tag đã chọn sẽ bị xóa khỏi "Kho" của ứng dụng.
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
    tem_tag_ids = fields.Many2many(
        'ctkm.inventory.tem.tag',
        'ctkm_task_recover_line_tem_tag_rel',
        'line_id',
        'tem_tag_id',
        string='Tem/Tag',
        domain="[('program_id', '=', program_id)]",
        help='Chọn các Tem/Tag cần thu hồi (sẽ bị xóa khỏi Kho khi Hoàn thành).',
    )

    def _ctkm_recover_inventory(self):
        """Xóa các Tem/Tag đã chọn khỏi Kho Tem/Tag của ứng dụng."""
        if 'ctkm.inventory.tem.tag' not in self.env:
            return self.browse()
        tem_tag = self.env['ctkm.inventory.tem.tag'].sudo().with_context(
            ctkm_tem_tag_line_sync=True,
        )
        to_unlink = tem_tag.browse()
        for line in self.sudo():
            to_unlink |= line.tem_tag_ids
        if to_unlink:
            to_unlink.unlink()
        return to_unlink
