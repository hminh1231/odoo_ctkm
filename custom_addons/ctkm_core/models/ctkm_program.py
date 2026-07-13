# -*- coding: utf-8 -*-

import base64
import io
import re
import zipfile
from xml.etree import ElementTree as ET

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import mimetypes

_CTKM_NOTIFY_DOC_EXTENSIONS = frozenset({
    '.pdf', '.doc', '.docx', '.xls', '.xlsx',
})
_CTKM_PRODUCT_QUANTITY_EXTENSIONS = frozenset({'.xlsx'})
_XLSX_NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
_XLSX_REL_NS = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
_XLSX_PACKAGE_REL_NS = '{http://schemas.openxmlformats.org/package/2006/relationships}'


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
    product_quantity_file_ids = fields.Many2many(
        comodel_name='ir.attachment',
        relation='ctkm_program_product_quantity_file_rel',
        column1='program_id',
        column2='attachment_id',
        string='Nhập file chi tiết số lượng sản phẩm',
        help='File Excel .xlsx chứa số lượng sản phẩm theo từng cửa hàng.',
    )
    ticket_instructions = fields.Html('Hướng dẫn vé', translate=True)
    notify_line_ids = fields.One2many(
        'ctkm.program.notify.line',
        'program_id',
        string='Phạm vi thông báo',
        copy=True,
    )
    approver_detail_line_ids = fields.One2many(
        'ctkm.program.approver.detail.line',
        'program_id',
        string='Chi tiết approver',
        copy=True,
    )
    store_detail_line_ids = fields.One2many(
        'ctkm.program.store.detail.line',
        'program_id',
        string='Chi tiết cửa hàng',
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

    @api.constrains('product_quantity_file_ids')
    def _check_product_quantity_files(self):
        for record in self:
            for attachment in record.product_quantity_file_ids:
                filename = (attachment.name or '').lower()
                extension = '.' + filename.rsplit('.', 1)[-1] if '.' in filename else ''
                if extension not in _CTKM_PRODUCT_QUANTITY_EXTENSIONS:
                    raise ValidationError(
                        _('File chi tiết số lượng sản phẩm chỉ chấp nhận Excel .xlsx: %s')
                        % attachment.name
                    )

    @api.model_create_multi
    def create(self, vals_list):
        programs = super().create(vals_list)
        programs._ctkm_link_notify_documents()
        programs._ctkm_link_product_quantity_files()
        programs._ctkm_import_product_quantity_files()
        return programs

    def write(self, vals):
        res = super().write(vals)
        if 'notify_document_ids' in vals:
            self._ctkm_link_notify_documents()
        if 'product_quantity_file_ids' in vals:
            self._ctkm_link_product_quantity_files()
            self._ctkm_import_product_quantity_files()
        return res

    def _ctkm_link_notify_documents(self):
        for program in self:
            program.notify_document_ids.write({
                'res_model': program._name,
                'res_id': program.id,
            })

    def _ctkm_link_product_quantity_files(self):
        for program in self:
            program.product_quantity_file_ids.write({
                'res_model': program._name,
                'res_id': program.id,
            })

    def _ctkm_import_product_quantity_files(self):
        DetailLine = self.env['ctkm.program.detail.line'].sudo()
        for program in self:
            DetailLine.search([
                ('program_id', '=', program.id),
                ('import_attachment_id', '!=', False),
            ]).unlink()
            for attachment in program.product_quantity_file_ids:
                rows = program._ctkm_parse_product_quantity_xlsx(attachment)
                for row in rows:
                    store = self.env['hr.store.code'].sudo().search([
                        ('code', '=', row['store_code']),
                    ], limit=1)
                    DetailLine.create({
                        'program_id': program.id,
                        'import_attachment_id': attachment.id,
                        'notification_file': attachment.name,
                        'store_code_id': store.id,
                        'product_name': row['product_name'],
                        'quantity': row['quantity'],
                        'note': row['note'],
                    })

    def _ctkm_parse_product_quantity_xlsx(self, attachment):
        self.ensure_one()
        raw = base64.b64decode(attachment.datas or b'')
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as workbook:
                sheet_path = self._ctkm_xlsx_visible_sheet_path(workbook)
                shared_strings = self._ctkm_xlsx_shared_strings(workbook)
                rows = self._ctkm_xlsx_rows(workbook, sheet_path, shared_strings)
        except (zipfile.BadZipFile, KeyError, ET.ParseError, ValueError) as exc:
            raise ValidationError(
                _('Không đọc được file chi tiết số lượng sản phẩm %s: %s')
                % (attachment.name, exc)
            ) from exc
        return self._ctkm_product_quantity_rows_from_sheet(rows, attachment.name)

    @api.model
    def _ctkm_xlsx_visible_sheet_path(self, workbook):
        workbook_root = ET.fromstring(workbook.read('xl/workbook.xml'))
        rel_root = ET.fromstring(workbook.read('xl/_rels/workbook.xml.rels'))
        rels = {
            rel.get('Id'): rel.get('Target')
            for rel in rel_root.findall(f'{_XLSX_PACKAGE_REL_NS}Relationship')
        }
        for sheet in workbook_root.findall(f'.//{_XLSX_NS}sheet'):
            if sheet.get('state') == 'hidden':
                continue
            rel_id = sheet.get(f'{_XLSX_REL_NS}id')
            target = rels.get(rel_id)
            if target:
                return 'xl/' + target.lstrip('/')
        raise ValueError(_('Không tìm thấy sheet Excel hiển thị.'))

    @api.model
    def _ctkm_xlsx_shared_strings(self, workbook):
        if 'xl/sharedStrings.xml' not in workbook.namelist():
            return []
        root = ET.fromstring(workbook.read('xl/sharedStrings.xml'))
        values = []
        for item in root.findall(f'{_XLSX_NS}si'):
            values.append(''.join(text.text or '' for text in item.iter(f'{_XLSX_NS}t')))
        return values

    @api.model
    def _ctkm_xlsx_rows(self, workbook, sheet_path, shared_strings):
        root = ET.fromstring(workbook.read(sheet_path))
        rows = []
        for row in root.findall(f'.//{_XLSX_NS}row'):
            values = {}
            for cell in row.findall(f'{_XLSX_NS}c'):
                ref = cell.get('r') or ''
                column = ''.join(ch for ch in ref if ch.isalpha())
                if not column:
                    continue
                values[column] = self._ctkm_xlsx_cell_value(cell, shared_strings)
            rows.append(values)
        return rows

    @api.model
    def _ctkm_xlsx_cell_value(self, cell, shared_strings):
        value = cell.find(f'{_XLSX_NS}v')
        if value is None:
            inline = cell.find(f'{_XLSX_NS}is')
            if inline is None:
                return ''
            return ''.join(text.text or '' for text in inline.iter(f'{_XLSX_NS}t')).strip()
        raw = (value.text or '').strip()
        if cell.get('t') == 's':
            return shared_strings[int(raw)].strip()
        return raw

    @api.model
    def _ctkm_product_quantity_rows_from_sheet(self, rows, filename):
        header_index = None
        for index, row in enumerate(rows):
            normalized = {
                column: self._ctkm_normalize_header(value)
                for column, value in row.items()
            }
            if normalized.get('A') in {'ma vat tu', 'ten sp', 'ten san pham'}:
                header_index = index
                break
        if header_index is None:
            raise ValueError(_('Không tìm thấy dòng tiêu đề "Mã vật tư" hoặc "Tên SP".'))

        header = rows[header_index]
        store_columns = [
            column for column, value in header.items()
            if column not in {'A', 'B', 'C', 'D', 'J'}
            and (value or '').strip()
            and self._ctkm_normalize_header(value) != 'tong cong'
        ]
        imported = []
        for row in rows[header_index + 1:]:
            product_name = (row.get('A') or '').strip()
            if not product_name or self._ctkm_normalize_header(product_name).startswith('tong cong'):
                continue
            for column in store_columns:
                quantity = self._ctkm_float(row.get(column))
                if not quantity:
                    continue
                imported.append({
                    'product_name': product_name,
                    'store_code': (header.get(column) or '').strip(),
                    'quantity': quantity,
                    'note': _('Import từ %(file)s. CTKM: %(program)s. Tem/tag: %(tag)s.')
                    % {
                        'file': filename,
                        'program': (row.get('C') or '').strip(),
                        'tag': (row.get('D') or '').strip(),
                    },
                })
        return imported

    @api.model
    def _ctkm_normalize_header(self, value):
        text = (value or '').strip().lower()
        replacements = {
            'ã': 'a', 'á': 'a', 'à': 'a', 'ả': 'a', 'ạ': 'a', 'ă': 'a', 'ắ': 'a',
            'ằ': 'a', 'ẳ': 'a', 'ẵ': 'a', 'ặ': 'a', 'â': 'a', 'ấ': 'a', 'ầ': 'a',
            'ẩ': 'a', 'ẫ': 'a', 'ậ': 'a', 'đ': 'd', 'é': 'e', 'è': 'e', 'ẻ': 'e',
            'ẽ': 'e', 'ẹ': 'e', 'ê': 'e', 'ế': 'e', 'ề': 'e', 'ể': 'e', 'ễ': 'e',
            'ệ': 'e', 'í': 'i', 'ì': 'i', 'ỉ': 'i', 'ĩ': 'i', 'ị': 'i', 'ó': 'o',
            'ò': 'o', 'ỏ': 'o', 'õ': 'o', 'ọ': 'o', 'ô': 'o', 'ố': 'o', 'ồ': 'o',
            'ổ': 'o', 'ỗ': 'o', 'ộ': 'o', 'ơ': 'o', 'ớ': 'o', 'ờ': 'o', 'ở': 'o',
            'ỡ': 'o', 'ợ': 'o', 'ú': 'u', 'ù': 'u', 'ủ': 'u', 'ũ': 'u', 'ụ': 'u',
            'ư': 'u', 'ứ': 'u', 'ừ': 'u', 'ử': 'u', 'ữ': 'u', 'ự': 'u', 'ý': 'y',
            'ỳ': 'y', 'ỷ': 'y', 'ỹ': 'y', 'ỵ': 'y',
        }
        for src, dest in replacements.items():
            text = text.replace(src, dest)
        return re.sub(r'\s+', ' ', text)

    @api.model
    def _ctkm_float(self, value):
        text = (value or '').strip()
        if not text:
            return 0.0
        try:
            return float(text.replace(',', ''))
        except ValueError:
            return 0.0

    @api.constrains('date_begin', 'date_end')
    def _check_closing_date(self):
        for record in self:
            if record.date_end < record.date_begin:
                raise ValidationError(_('Ngày kết thúc không thể trước ngày bắt đầu.'))
