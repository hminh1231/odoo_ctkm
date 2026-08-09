# -*- coding: utf-8 -*-

import base64
import io
import logging
import math
import re
import unicodedata
from collections import OrderedDict
from datetime import date, datetime, timedelta
from zipfile import ZipFile
from xml.etree import ElementTree

from markupsafe import Markup, escape

from odoo import _, fields, models
from odoo.addons.ctkm_inventory.models.ctkm_inventory_tem_tag import _normalize_store_code
from odoo.exceptions import AccessError, UserError


_MAIN_NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
_CTKM_BOT_XMLID = 'business_discuss_bots.user_bot_ctkm'

_logger = logging.getLogger(__name__)


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
        self._check_import_allowed()
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
                'store': row.get('store'),
                'quantity': row.get('quantity') or 0.0,
                'import_filename': self.filename,
            })

        # Người nhận việc bước "Đổ BB thay tem/tag" là nhân viên thường: họ chỉ được
        # ghi kho Tem/Tag thông qua wizard này (đã kiểm tra quyền ở trên).
        Inventory = self.env['ctkm.inventory.tem.tag'].sudo()
        if self.replace_existing and records_by_program_date:
            domain = ['|'] * (len(records_by_program_date) - 1)
            for program_id, inventory_date in records_by_program_date:
                domain.append('&')
                domain.append(('program_id', '=', program_id))
                domain.append(('date', '=', inventory_date))
            Inventory.search(domain).unlink()

        created = Inventory.create(values)
        self._notify_imported_tem_tags(created)
        return self._import_result_action(created)

    def _check_import_allowed(self):
        """CTKM user/manager, hoặc người được giao đúng bước import của CTKM này."""
        self.ensure_one()
        if self.env.user.has_group('ctkm_core.group_ctkm_user'):
            return
        if self.program_id and self._user_import_tasks():
            return
        raise AccessError(_(
            'Bạn chỉ được import Tem/Tag cho chương trình khuyến mãi có công việc '
            '"Đổ BB thay tem/tag (file tổng)" được giao cho bạn.'
        ))

    def _user_import_tasks(self):
        """Công việc bước import Tem/Tag của người dùng hiện tại trên CTKM đã chọn."""
        self.ensure_one()
        tasks = self.env['ctkm.task'].sudo().search([
            ('user_id', '=', self.env.user.id),
            ('program_id', '=', self.program_id.id),
        ])
        return tasks.filtered('is_tem_tag_import_task')

    def _import_result_action(self, created):
        """Mở danh sách vừa import; nhân viên thường chỉ nhận thông báo kết quả."""
        self.ensure_one()
        if not self.env.user.has_group('ctkm_core.group_ctkm_user'):
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'type': 'success',
                    'title': _('Import Tem/Tag'),
                    'message': _('Đã import %s dòng Tem/Tag.') % len(created),
                    'next': {'type': 'ir.actions.act_window_close'},
                },
            }
        action = self.env.ref('ctkm_inventory.action_ctkm_inventory_tem_tag').sudo().read()[0]
        action.update({
            'name': _('Tem/Tag đã import'),
            'domain': [('id', 'in', created.ids)],
        })
        return action

    def _notify_imported_tem_tags(self, records):
        grouped = self._group_tem_tag_records_by_store(records.sudo())
        if not grouped:
            return False

        sent_users = self.env['res.users']
        skipped_store_names = []
        for group in grouped.values():
            users = self._get_store_recipient_users(group['store_key'])
            if not users:
                skipped_store_names.append(group['store_name'])
                continue
            body = self._tem_tag_import_message_body(
                group['program'],
                group['store_name'],
                group['items'].values(),
            )
            for user in users:
                if self._post_tem_tag_bot_message(user, body):
                    sent_users |= user

        self._log_tem_tag_notification_result(records.sudo(), sent_users, skipped_store_names)
        return True

    def _group_tem_tag_records_by_store(self, records):
        grouped = OrderedDict()
        for record in records.sorted(
            lambda rec: (
                rec.program_id.id,
                rec.store_key or '',
                rec.material_code or '',
                rec.tem_tag or '',
                rec.id,
            )
        ):
            store_key = record.store_key or _normalize_store_code(record.store)
            if not store_key:
                continue
            group_key = (record.program_id.id, store_key)
            group = grouped.setdefault(
                group_key,
                {
                    'program': record.program_id,
                    'store_key': store_key,
                    'store_name': record.store or store_key,
                    'items': OrderedDict(),
                },
            )
            item_key = (record.tem_tag or '', record.material_code or '')
            item = group['items'].setdefault(
                item_key,
                {
                    'label': self._tem_tag_item_label(record),
                    'quantity': 0.0,
                },
            )
            item['quantity'] += record.quantity or 0.0
        return grouped

    def _tem_tag_item_label(self, record):
        tem_tag = (record.tem_tag or '').strip()
        material_code = (record.material_code or '').strip()
        if tem_tag and material_code:
            return '%s (%s)' % (tem_tag, material_code)
        return tem_tag or material_code or _('Không có mã')

    def _get_store_recipient_users(self, store_key):
        Employee = self.env['hr.employee'].sudo()
        employees = Employee.search([('active', '=', True), ('user_id', '!=', False)])
        employees = employees.filtered(
            lambda employee: store_key in self._employee_store_keys(employee)
        )
        return employees.mapped('user_id').filtered(
            lambda user: user and user.active and not user.share and user.partner_id
        )

    def _employee_store_keys(self, employee):
        codes = []
        if 'ma_bo_phan' in employee._fields:
            codes.append(employee.ma_bo_phan)
        if 'ma_bo_phan_id' in employee._fields and employee.ma_bo_phan_id:
            codes.append(employee.ma_bo_phan_id.code)
        if 'store_id' in employee._fields and employee.store_id:
            codes.append(employee.store_id.code)
        if 'current_version_id' in employee._fields and employee.current_version_id:
            version = employee.current_version_id
            if 'store_id' in version._fields and version.store_id:
                codes.append(version.store_id.code)

        keys = set()
        for code in codes:
            key = _normalize_store_code(code)
            if key:
                keys.add(key)
        return keys

    def _tem_tag_import_message_body(self, program, store_name, items):
        lines = [
            Markup('Chuong trinh khuyen mai <b>%s</b>') % escape(program.name or ''),
            Markup('cua hang <b>%s</b>') % escape(store_name or ''),
            Markup('da nhan so tem/tag la'),
        ]
        for index, item in enumerate(items, start=1):
            lines.append(
                Markup('%s. %s voi so luong %s')
                % (
                    index,
                    escape(item['label']),
                    escape(self._format_tem_tag_quantity(item['quantity'])),
                )
            )
        return Markup('<br/>').join(lines)

    def _format_tem_tag_quantity(self, quantity):
        quantity = quantity or 0.0
        if float(quantity).is_integer():
            return str(int(quantity))
        return ('%.6f' % quantity).rstrip('0').rstrip('.')

    def _post_tem_tag_bot_message(self, recipient_user, body):
        Message = self.env['mail.message']
        if not recipient_user or recipient_user.share or not recipient_user.partner_id:
            return Message
        bot_user = self.env.ref(_CTKM_BOT_XMLID, raise_if_not_found=False)
        if not bot_user or not bot_user.partner_id:
            _logger.warning('ctkm_inventory: CTKM bot user is not configured')
            return Message
        try:
            chat = (
                self.env['discuss.channel']
                .sudo()
                .with_user(recipient_user)
                ._get_or_create_chat([bot_user.partner_id.id], pin=True)
            )
            return chat.with_user(bot_user).sudo().message_post(
                body=body,
                message_type='comment',
                subtype_xmlid='mail.mt_comment',
                author_id=bot_user.partner_id.id,
            )
        except Exception:
            _logger.exception(
                'ctkm_inventory: Tem/Tag bot notification failed recipient_user_id=%s',
                recipient_user.id,
            )
            return Message

    def _log_tem_tag_notification_result(self, records, sent_users, skipped_store_names):
        programs = records.mapped('program_id')
        if not programs:
            return
        log_lines = [
            _('Đã import Tem/Tag và gửi thông báo Discuss tới %s người nhận.')
            % len(sent_users)
        ]
        if sent_users:
            log_lines.append(_('Người nhận: %s') % ', '.join(sent_users.mapped('name')))
        if skipped_store_names:
            log_lines.append(
                _('Không tìm thấy nhân viên có tài khoản nội bộ cho cửa hàng: %s')
                % ', '.join(skipped_store_names)
            )
        for program in programs:
            program.message_post(
                body=Markup('<br/>').join(Markup('%s') % escape(line) for line in log_lines),
                subtype_xmlid='mail.mt_note',
            )

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

            result.extend(
                self._extract_inventory_rows(row, columns, sheet_date, material_code, sheet_name)
            )
        return result

    def _extract_inventory_rows(self, row, columns, sheet_date, material_code, sheet_name):
        base_values = {
            'date': sheet_date,
            'material_code': material_code,
            'promo_price': self._to_float(row.iloc[columns['promo_price']]),
            'tem_tag': self._clean_text(row.iloc[columns['tem_tag']]),
            'sheet_name': sheet_name,
        }

        store_columns = columns.get('store_columns') or []
        if store_columns:
            rows = []
            for store_col, store_name in store_columns:
                quantity = self._to_float(row.iloc[store_col])
                if not quantity:
                    continue
                rows.append({
                    **base_values,
                    'store': store_name,
                    'quantity': quantity,
                })
            return rows

        quantity = self._extract_quantity(row, columns)
        if quantity is None:
            return []
        return [{**base_values, 'quantity': quantity}]

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
                found['store_columns'] = self._find_store_columns(frame.iloc[row_index], found)
                return row_index, found
        return None, {}

    def _find_store_columns(self, header_row, columns):
        fixed_columns = {
            columns['material_code'],
            columns['promo_price'],
            columns['ctkm_name'],
            columns['tem_tag'],
        }
        total_col = columns.get('quantity_total')
        store_columns = []
        for col_index, value in enumerate(header_row):
            if col_index in fixed_columns or col_index == total_col:
                continue
            if total_col is not None and col_index > total_col:
                continue
            store_name = self._clean_text(value)
            if store_name:
                store_columns.append((col_index, store_name))
        return store_columns

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
