# -*- coding: utf-8 -*-

import base64

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import mimetypes

_CTKM_NOTIFY_DOC_EXTENSIONS = frozenset({
    '.pdf', '.doc', '.docx', '.xls', '.xlsx',
})


class CtkmProgram(models.Model):
    _name = 'ctkm.program'
    _description = 'Chương trình khuyến mãi'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_begin, id'

    def _get_default_stage_id(self):
        return self.env['ctkm.stage'].search([], limit=1)

    name = fields.Char(string='Tên chương trình', translate=True, required=True)
    active = fields.Boolean(default=True)
    user_id = fields.Many2one(
        'res.users', string='Người phụ trách', tracking=True,
        default=lambda self: self.env.user)
    company_id = fields.Many2one(
        'res.company', string='Công ty', change_default=True,
        default=lambda self: self.env.company,
        required=False)
    stage_id = fields.Many2one(
        'ctkm.stage', ondelete='restrict', default=_get_default_stage_id,
        tracking=True, copy=False)
    kanban_state = fields.Selection([
        ('normal', 'Đang thực hiện'),
        ('done', 'Sẵn sàng cho giai đoạn tiếp'),
        ('blocked', 'Bị chặn'),
    ], default='normal', copy=False, tracking=True)
    tag_ids = fields.Many2many('ctkm.tag', string='Nhãn', readonly=False)
    organizer_id = fields.Many2one(
        'res.partner', string='Đơn vị tổ chức', tracking=True,
        default=lambda self: self.env.company.partner_id,
        check_company=True)
    address_id = fields.Many2one(
        'res.partner', string='Địa điểm', default=lambda self: self.env.company.partner_id.id,
        check_company=True, tracking=True)
    event_url = fields.Char(
        string='URL sự kiện trực tuyến',
        help="Liên kết nơi sự kiện trực tuyến diễn ra.")
    seats_limited = fields.Boolean(string='Giới hạn đăng ký')
    seats_max = fields.Integer(string='Số lượng tối đa')
    date_begin = fields.Datetime(string='Ngày bắt đầu', required=True, tracking=True)
    date_end = fields.Datetime(string='Ngày kết thúc', required=True, tracking=True)
    note = fields.Html(string='Ghi chú')
    description = fields.Html(string='Mô tả', translate=True)
    badge_format = fields.Selection(
        string='Kích thước nhãn',
        selection=[
            ('A4_french_fold', 'A4 gập đôi'),
            ('A6', 'A6'),
            ('four_per_sheet', '4 trên một tờ'),
        ], default='A6', required=True)
    badge_image = fields.Image(
        'Ảnh nền nhãn',
        max_width=1024,
        max_height=1024,
        help='Chỉ dùng file ảnh (JPG, PNG...). PDF/Word/Excel hãy tải ở mục Tài liệu đính kèm.',
    )
    notify_document_ids = fields.Many2many(
        comodel_name='ir.attachment',
        relation='ctkm_program_notify_document_rel',
        column1='program_id',
        column2='attachment_id',
        string='Tài liệu đính kèm',
        help='Tài liệu PDF, Word hoặc Excel gửi kèm thông báo Discuss.',
    )
    ticket_instructions = fields.Html('Hướng dẫn vé', translate=True)
    notify_line_ids = fields.One2many(
        'ctkm.program.notify.line',
        'program_id',
        string='Phạm vi thông báo',
        copy=True,
    )

    @api.constrains('badge_image')
    def _check_badge_image(self):
        for record in self:
            if not record.badge_image:
                continue
            raw = base64.b64decode(record.badge_image)
            mime = mimetypes.guess_mimetype(raw, default='') or ''
            if not mime.startswith('image/'):
                raise ValidationError(
                    _(
                        'Ảnh nền nhãn chỉ chấp nhận file ảnh (JPG, PNG...). '
                        'Để gửi PDF, Word hoặc Excel, hãy dùng mục "Tài liệu đính kèm".'
                    )
                )

    @api.constrains('notify_document_ids')
    def _check_notify_documents(self):
        for record in self:
            for attachment in record.notify_document_ids:
                filename = (attachment.name or '').lower()
                if '.' not in filename:
                    raise ValidationError(
                        _('Tài liệu đính kèm phải có phần mở rộng hợp lệ (PDF, Word, Excel).')
                    )
                extension = '.' + filename.rsplit('.', 1)[-1]
                if extension not in _CTKM_NOTIFY_DOC_EXTENSIONS:
                    raise ValidationError(
                        _('Chỉ chấp nhận tài liệu PDF, Word hoặc Excel: %s')
                        % attachment.name
                    )

    @api.model_create_multi
    def create(self, vals_list):
        programs = super().create(vals_list)
        programs._ctkm_link_notify_documents()
        return programs

    def write(self, vals):
        res = super().write(vals)
        if 'notify_document_ids' in vals:
            self._ctkm_link_notify_documents()
        return res

    def _ctkm_link_notify_documents(self):
        for program in self:
            program.notify_document_ids.write({
                'res_model': program._name,
                'res_id': program.id,
            })

    @api.constrains('date_begin', 'date_end')
    def _check_closing_date(self):
        for record in self:
            if record.date_end < record.date_begin:
                raise ValidationError(_('Ngày kết thúc không thể trước ngày bắt đầu.'))
