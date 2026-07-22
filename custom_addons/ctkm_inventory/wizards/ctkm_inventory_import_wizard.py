# -*- coding: utf-8 -*-

import base64
import io
import math
import re
import unicodedata
from datetime import date, datetime, timedelta
from zipfile import ZipFile
from xml.etree import ElementTree

from odoo import _, fields, models
from odoo.exceptions import UserError


_MAIN_NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'


class CtkmInventoryImportWizard(models.TransientModel):
    _name = 'ctkm.inventory.import.wizard'
    _description = 'Import kho Tem/Tag CTKM'

    upload_file = fields.Binary(string='File .xlsx', required=True)
    filename = fields.Char(string='Tên file')
    program_id = fields.Many2one(
        'ctkm.program',
        string='CTKM',
        required=True,
        help='Chọn chương trình khuyến mãi thuộc file Excel này.',
    )
    import_date = fields.Date(
        string='Date',
        help='Để trống để lấy ngày từ file Excel.',
    )
    replace_existing = fields.Boolean(
        string='Xóa dữ liệu cùng CTKM/ngày trước khi import',
        default=False,
    )

    def action_import(self):
        self.ensure_one()
        raw_file = self._decode_upload()
        frames = self._read_excel_frames(raw_file)
        visible_sheet_names = self._get_visible_sheet_names(raw_file)
        rows = self._extract_rows(frames, visible_sheet_names)
        if not rows:
            raise UserError(_('Không tìm thấy dòng Tem/Tag hợp lệ trong file Excel.'))

        records_by_program_date = {}
        values = []
        for row in rows:
            inventory_date = self.import_date or row.get('date') or fields.Date.context_today(self)
            program = self._find_program(row)
            key = (program.id, fields.Date.to_date(inventory_date))
            records_by_program_date[key] = True
            values.append({
                'date': inventory_date,
                'material_code': row['material_code'],
                'promo_price': row.get('promo_price') or 0.0,
                'program_id': program.id,
                'tem_tag': row.get('tem_tag'),
                'quantity': row.get('quantity') or 0.0,
                'import_filename': self.filename,
            })

        Inventory = self.env['ctkm.inventory.tem.tag']
        if self.replace_existing and records_by_program_date:
            domain = ['|'] * (len(records_by_program_date) - 1)
            for program_id, inventory_date in records_by_program_date:
                domain.append('&')
                domain.append(('program_id', '=', program_id))
                domain.append(('date', '=', inventory_date))
            Inventory.search(domain).unlink()

        created = Inventory.create(values)
        action = self.env.ref('ctkm_inventory.action_ctkm_inventory_tem_tag').read()[0]
        action.update({
            'name': _('Tem/Tag đã import'),
            'domain': [('id', 'in', created.ids)],
        })
        return action

    def _decode_upload(self):
        try:
            raw_file = base64.b64decode(self.upload_file or b'')
        except Exception as exc:
            raise UserError(_('Không đọc được file upload.')) from exc
        if not raw_file:
            raise UserError(_('File upload đang trống.'))
        return raw_file

    def _read_excel_frames(self, raw_file):
        try:
            import pandas as pd
        except ImportError as exc:
            raise UserError(
                _('Thiếu thư viện pandas. Hãy cài pandas và python-calamine cho môi trường Odoo.')
            ) from exc

        try:
            return pd.read_excel(
                io.BytesIO(raw_file),
                sheet_name=None,
                header=None,
                dtype=object,
                engine='calamine',
            )
        except ImportError as exc:
            raise UserError(
                _('Thiếu thư viện python-calamine để pandas đọc file Excel bằng engine calamine.')
            ) from exc
        except Exception as exc:
            raise UserError(_('Không đọc được file Excel bằng pandas/calamine: %s') % exc) from exc

    def _get_visible_sheet_names(self, raw_file):
        try:
            with ZipFile(io.BytesIO(raw_file)) as workbook:
                root = ElementTree.fromstring(workbook.read('xl/workbook.xml'))
        except Exception:
            return []

        visible_names = []
        sheets = root.find(_MAIN_NS + 'sheets')
        if sheets is None:
            return []
        for sheet in sheets:
            if sheet.attrib.get('state') not in ('hidden', 'veryHidden'):
                visible_names.append(sheet.attrib.get('name'))
        return [name for name in visible_names if name]

    def _extract_rows(self, frames, visible_sheet_names):
        rows = []
        sheet_names = visible_sheet_names or list(frames)
        for sheet_name in sheet_names:
            frame = frames.get(sheet_name)
            if frame is None:
                continue
            rows.extend(self._extract_sheet_rows(sheet_name, frame))
        return rows

    def _extract_sheet_rows(self, sheet_name, frame):
        header_row, columns = self._find_header(frame)
        if header_row is None:
            return []

        sheet_date = self.import_date or self._find_date(frame, header_row)
        result = []
        for index in range(header_row + 1, len(frame.index)):
            row = frame.iloc[index]
            material_code = self._clean_text(row.iloc[columns['material_code']])
            if not material_code:
                continue
            if self._normalize_label(material_code).startswith('tong cong'):
                break

            tem_tag = self._clean_text(row.iloc[columns['tem_tag']])
            quantity = self._extract_quantity(row, columns)
            if quantity is None:
                continue

            result.append({
                'date': sheet_date,
                'material_code': material_code,
                'promo_price': self._to_float(row.iloc[columns['promo_price']]),
                'tem_tag': tem_tag,
                'quantity': quantity,
                'sheet_name': sheet_name,
            })
        return result

    def _find_header(self, frame):
        required = {
            'ma vat tu': 'material_code',
            'gia km': 'promo_price',
            'ctkm': 'ctkm_name',
            'tem tag': 'tem_tag',
        }
        for row_index in range(len(frame.index)):
            found = {}
            for col_index, value in enumerate(frame.iloc[row_index]):
                label = self._normalize_label(value)
                if label in required:
                    found[required[label]] = col_index
                elif label == 'tong cong':
                    found['quantity_total'] = col_index
            if all(column in found for column in required.values()):
                return row_index, found
        return None, {}

    def _extract_quantity(self, row, columns):
        total_col = columns.get('quantity_total')
        if total_col is not None:
            return self._to_float(row.iloc[total_col])

        numeric_values = []
        fixed_columns = {
            columns['material_code'],
            columns['promo_price'],
            columns['ctkm_name'],
            columns['tem_tag'],
        }
        for index, value in enumerate(row):
            if index in fixed_columns:
                continue
            number = self._to_float(value)
            if number:
                numeric_values.append(number)
        return sum(numeric_values) if numeric_values else None

    def _find_date(self, frame, header_row):
        for row_index in range(max(header_row, 0)):
            for value in frame.iloc[row_index]:
                parsed = self._parse_date(value)
                if parsed:
                    return parsed
        return False

    def _find_program(self, row):
        return self.program_id

    def _parse_date(self, value):
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, (int, float)) and not self._is_empty(value):
            try:
                return (datetime(1899, 12, 30) + timedelta(days=float(value))).date()
            except Exception:
                return False

        text = self._clean_text(value)
        match = re.search(r'(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})', text)
        if not match:
            return False
        day, month, year = (int(part) for part in match.groups())
        if year < 100:
            year += 2000
        try:
            return date(year, month, day)
        except ValueError:
            return False

    def _to_float(self, value):
        if self._is_empty(value):
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)

        text = self._clean_text(value)
        if not text:
            return 0.0
        text = re.sub(r'[^\d,.-]', '', text)
        if not text:
            return 0.0
        if ',' in text and '.' in text:
            text = text.replace('.', '').replace(',', '.')
        elif re.fullmatch(r'-?\d{1,3}(\.\d{3})+', text):
            text = text.replace('.', '')
        elif re.fullmatch(r'-?\d{1,3}(,\d{3})+', text):
            text = text.replace(',', '')
        elif ',' in text:
            text = text.replace(',', '.')
        try:
            return float(text)
        except ValueError:
            return 0.0

    def _clean_text(self, value):
        if self._is_empty(value):
            return ''
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value).strip()

    def _normalize_label(self, value):
        text = self._clean_text(value).lower()
        text = unicodedata.normalize('NFD', text)
        text = ''.join(char for char in text if unicodedata.category(char) != 'Mn')
        return re.sub(r'[^a-z0-9]+', ' ', text).strip()

    def _is_empty(self, value):
        if value is None:
            return True
        if isinstance(value, float) and math.isnan(value):
            return True
        return False
