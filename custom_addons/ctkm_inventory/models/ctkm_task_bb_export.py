# -*- coding: utf-8 -*-

import base64
import io
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html2plaintext

from .ctkm_inventory_tem_tag import _normalize_store_code

_logger = logging.getLogger(__name__)

try:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, Side
    from openpyxl.utils import get_column_letter
except ImportError:
    Workbook = None


# Định dạng số "Giá KM" giống file mẫu (accounting, không dấu phẩy nghìn chuẩn).
ACCOUNTING_NUMBER_FORMAT = '_-* #,##0_-;\\-* #,##0_-;_-* "-"??_-;_-@_-'
# Định dạng số lượng (Tổng SL, các cột cửa hàng, cột Tổng cộng).
QUANTITY_NUMBER_FORMAT = '#,##0'

# Dòng tiêu đề (giống file mẫu step 4: tem.xlsx).
HEADER_ROW = 7
DATA_START_ROW = 8


class CtkmTask(models.Model):
    _inherit = 'ctkm.task'

    store_ids = fields.Many2many(
        'hr.store',
        string='Cửa hàng',
        help='Chọn một hoặc nhiều cửa hàng để xuất biên bản thay tem (bước 6).',
    )

    def action_export_bb_file(self):
        self.ensure_one()
        if not self.is_tem_replace_task:
            raise UserError(_(
                'Chỉ công việc bước "Thay tem Tag" (lập BB thay tem) mới được '
                'xuất biên bản thay tem.'
            ))
        if not self.store_ids:
            raise UserError(_('Vui lòng chọn ít nhất một Cửa hàng trước khi xuất file.'))
        if Workbook is None:
            raise UserError(_('Thiếu thư viện openpyxl để xuất file Excel.'))
        data = self._build_bb_xlsx()
        date_str = fields.Date.context_today(self).strftime('%d_%m_%Y')
        filename = 'BB_thay_tem_%s_%s.xlsx' % (
            self.program_id.notify_code or self.program_id.id or 'CTKM',
            date_str,
        )
        attachment = self.env['ir.attachment'].sudo().create({
            'name': filename,
            'datas': base64.b64encode(data),
            'res_model': 'ctkm.task',
            'res_id': self.id,
            'type': 'binary',
            'public': True,
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'self',
        }

    def _build_bb_xlsx(self):
        """Xuất biên bản thay tem theo đúng mẫu step 4 (file tem.xlsx).

        Bố cục:
            Dòng 1: Tên công ty (bold)
            Dòng 2: Địa chỉ (bold)
            Dòng 3: Tiêu đề "BIÊN BẢN THAY TEM BỔ SUNG TB <mã> NGÀY <ngày>" (bold, size 18)
            Dòng 4: "Ngày <ngày>" (bold)
            Dòng 5: Ghi chú chương trình
            Dòng 7: Tiêu đề cột (Mã vật tư, Giá KM, CTKM, Tem/tag, <các cửa hàng>, Tổng cộng)
            Dòng 8+: Chi tiết từng Mã vật tư, SL theo từng cửa hàng đã chọn
            Dòng cuối: Tổng cộng
        """
        self.ensure_one()
        program = self.program_id
        company = self.env.company
        partner = company.partner_id
        address = ', '.join(
            p for p in [
                partner.street,
                partner.city,
                partner.state_id.name if partner.state_id else '',
                partner.country_id.name if partner.country_id else '',
            ] if p
        )
        inventory_date = fields.Date.context_today(self)
        date_str = inventory_date.strftime('%d/%m/%Y')

        # --- Các cửa hàng được chọn (giữ đúng thứ tự người dùng chọn) ---
        selected = self.store_ids.sudo()
        if not selected:
            raise UserError(_('Vui lòng chọn ít nhất một Cửa hàng trước khi xuất file.'))
        selected_map = {}
        for store in selected:
            key = _normalize_store_code(store.code or store.name)
            if key and key not in selected_map:
                selected_map[key] = store
        store_keys = list(selected_map.keys())
        store_cols = [
            selected_map[k].code or selected_map[k].name or k for k in store_keys
        ]
        last_col = 4 + len(store_cols) + 1  # cột Tổng cộng
        total_col_letter = get_column_letter(last_col)

        # --- Gom SL kho Tem/Tag theo (Mã vật tư, cửa hàng) ---
        Inventory = self.env['ctkm.inventory.tem.tag'].sudo()
        records = Inventory.search([
            ('program_id', '=', program.id),
            ('store_key', 'in', store_keys),
        ])
        materials = {}
        for rec in records:
            code = rec.material_code
            if not code:
                continue
            key = rec.store_key
            if key not in selected_map:
                continue
            mat = materials.setdefault(code, {
                'promo': rec.promo_price or 0.0,
                'tem_tag': rec.tem_tag or '',
                'ctkm': program.name or '',
                'stores': {},
            })
            mat['stores'][key] = mat['stores'].get(key, 0.0) + (rec.quantity or 0.0)
        material_codes = sorted(materials.keys())

        # --- Vẽ workbook ---
        wb = Workbook()
        ws = wb.active
        sheet_title = '%s_BỔ SUNG' % (program.notify_code or 'BB')
        ws.title = sheet_title[:31]

        thin = Side(style='thin', color='FF000000')
        border = Border(left=thin, right=thin, top=thin, bottom=thin)
        bold = Font(bold=True)
        header_font = Font(bold=True, size=11)
        center = Alignment(horizontal='center', vertical='center')
        center_h = Alignment(horizontal='center')

        # Dòng 1-2: công ty / địa chỉ
        ws.cell(row=1, column=1, value=company.name or '').font = bold
        ws.cell(row=2, column=1, value=address or '').font = bold
        # Dòng 3: tiêu đề
        title_cell = ws.cell(
            row=3, column=1,
            value='BIÊN BẢN THAY TEM BỔ SUNG TB %s NGÀY %s'
            % (program.notify_code or program.name or '', date_str),
        )
        title_cell.font = Font(bold=True, size=18)
        ws.row_dimensions[3].height = 23.25
        # Dòng 4: ngày
        ws.cell(row=4, column=1, value='Ngày %s' % date_str).font = bold
        # Dòng 5: ghi chú
        note = html2plaintext(program.note) if program.note else ''
        ws.cell(row=5, column=1, value=note or '')
        ws.row_dimensions[5].height = 39.0

        # Dòng 7: tiêu đề cột
        headers = (
            ['Mã vật tư', 'Giá KM', 'CTKM', 'Tem/tag']
            + store_cols
            + ['Tổng cộng']
        )
        for col_idx, h in enumerate(headers, start=1):
            cell = ws.cell(row=HEADER_ROW, column=col_idx, value=h)
            cell.font = header_font
            cell.border = border
            cell.alignment = center
        ws.row_dimensions[HEADER_ROW].height = 55.5

        # Dòng 8+: chi tiết
        r = DATA_START_ROW
        for code in material_codes:
            mat = materials[code]
            row_vals = [code, mat['promo'], mat['ctkm'], mat['tem_tag']]
            row_sum = 0.0
            for k in store_keys:
                qty = mat['stores'].get(k, 0.0)
                row_vals.append(qty)
                row_sum += qty
            row_vals.append(row_sum)
            for col_idx, val in enumerate(row_vals, start=1):
                cell = ws.cell(row=r, column=col_idx, value=val)
                cell.font = Font(size=11)
                cell.border = border
                if col_idx == 2:
                    cell.number_format = ACCOUNTING_NUMBER_FORMAT
                elif col_idx >= 5:
                    cell.number_format = QUANTITY_NUMBER_FORMAT
            # Công thức Tổng cộng cho dòng
            total_cell = ws.cell(row=r, column=last_col)
            first_store_letter = get_column_letter(5)
            last_store_letter = get_column_letter(4 + len(store_cols))
            total_cell.value = '=SUM(%s%d:%s%d)' % (
                first_store_letter, r, last_store_letter, r,
            )
            total_cell.number_format = QUANTITY_NUMBER_FORMAT
            total_cell.font = Font(bold=True, size=11)
            r += 1

        # Dòng cuối: tổng cộng
        total_row = r
        ws.cell(row=total_row, column=1, value='Tổng cộng:').font = bold
        for col_idx in range(5, last_col + 1):
            col_letter = get_column_letter(col_idx)
            cell = ws.cell(
                row=total_row, column=col_idx,
                value='=SUM(%s%d:%s%d)' % (col_letter, DATA_START_ROW, col_letter, total_row - 1),
            )
            cell.font = Font(bold=True, size=11)
            cell.number_format = QUANTITY_NUMBER_FORMAT
            cell.border = border
        # Border các ô trống của dòng tổng cộng
        for col_idx in (1, 2, 3, 4, last_col):
            ws.cell(row=total_row, column=col_idx).border = border

        # Độ rộng cột (khớp mẫu)
        widths = {
            1: 46.29,   # Mã vật tư / CTKM
            2: 12.71,   # Giá KM
            3: 25.43,   # CTKM
            4: 12.71,   # Tem/tag
        }
        for i in range(len(store_cols)):
            widths[5 + i] = 12.0
        widths[last_col] = 12.0
        for col_idx, w in widths.items():
            ws.column_dimensions[get_column_letter(col_idx)].width = w

        stream = io.BytesIO()
        wb.save(stream)
        return stream.getvalue()
