# -*- coding: utf-8 -*-

from odoo import api, fields, models


class CtkmTaskTemDesignLine(models.Model):
    """Dòng thiết kế mẫu tem/tag theo từng Mã vật tư (bước 7).

    Mỗi dòng ứng với một ``Mã vật tư`` lấy từ bảng tổng hợp "Chi tiết tem/tag"
    của chương trình (``ctkm.task.tem.tag.replace.line``). Người nhận việc bước
    "Thiết kế mẫu tem/tag, Bảng nhận diện" tải lên file mẫu (PDF / ảnh) cho từng
    mã vật tư.
    """

    _name = 'ctkm.task.tem.design.line'
    _description = 'Thiết kế mẫu tem/tag theo mã vật tư'
    _order = 'material_code, id'
    _rec_name = 'material_code'

    task_id = fields.Many2one(
        'ctkm.task',
        string='Công việc',
        required=True,
        ondelete='cascade',
        index=True,
    )
    material_code = fields.Char(
        string='Mã vật tư',
        readonly=True,
        index=True,
        help='Mã vật tư lấy từ bảng "Chi tiết tem/tag" của chương trình.',
    )
    file = fields.Binary(
        string='File mẫu thiết kế',
        attachment=True,
        help='Tải lên mẫu thiết kế (PDF hoặc ảnh): .pdf, .png, .jpg, .jpeg, .gif, .webp.',
    )
    filename = fields.Char(string='Tên file')
