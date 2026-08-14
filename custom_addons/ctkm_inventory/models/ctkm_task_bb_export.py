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
                'Chỉ công việc bước "Thay tem Tag" mới được xuất biên bản thay tem.'
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

        selected = self.store_ids.sudo()
        selected_map = {}
        for store in selected:
            key = _normalize_store_code(store.code or store.name)
            if key:
                selected_map[key] = store
        store_keys = list(selected_map.keys())
        store_cols = [selected_map[k].code or selected_map[k].name for k in store_keys]

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
            mat = materials.setdefault(code, {
                'promo': rec.promo_price or 0.0,
                'tem_tag': rec.tem_tag or '',
                'ctkm': program.name or '',
                'stores': {},
            })
            key = rec.store_key
            if key in selected_map:
                mat['stores'][key] = mat['stores'].get(key, 0.0) + (rec.quantity or 0.0)

        material_codes = sorted(materials.keys())

        wb = Workbook()
        ws = wb.active
        ws.title = (program.notify_code or 'BB')[:31]

        last_col = 4 + len(store_cols) + 1
        thin = Side(style='thin', color='FF000000')
        border = Border(left=thin, right=thin, top=thin, bottom=thin)
        bold = Font(bold=True)

        ws.cell(row=1, column=1, value=company.name or '').font = bold
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=last_col)
        ws.cell(row=2, column=1, value=address or '')
        ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=last_col)
        title_cell = ws.cell(
            row=3, column=1,
            value='BIÊN BẢN THAY TEM BỔ SUNG TB %s NGÀY %s'
            % (program.notify_code or program.name or '', date_str),
        )
        title_cell.font = Font(bold=True, size=12)
        title_cell.alignment = Alignment(horizontal='center')
        ws.merge_cells(start_row=3, start_column=1, end_row=3, end_column=last_col)
        ws.cell(row=4, column=1, value='Ngày %s' % date_str)
        ws.merge_cells(start_row=4, start_column=1, end_row=4, end_column=last_col)
        ws.cell(row=5, column=1, value=html2plaintext(program.note) if program.note else '')
        ws.merge_cells(start_row=5, start_column=1, end_row=5, end_column=last_col)

        header_row = 7
        headers = ['Mã vật tư', 'Giá KM', 'CTKM', 'Tem/tag'] + store_cols + ['Tổng cộng']
        for col_idx, h in enumerate(headers, start=1):
            cell = ws.cell(row=header_row, column=col_idx, value=h)
            cell.font = bold
            cell.border = border
            cell.alignment = Alignment(horizontal='center', wrap_text=True)

        r = header_row + 1
        store_totals = {k: 0.0 for k in store_keys}
        grand_total = 0.0
        for code in material_codes:
            mat = materials[code]
            row_vals = [code, mat['promo'], mat['ctkm'], mat['tem_tag']]
            row_sum = 0.0
            for k in store_keys:
                qty = mat['stores'].get(k, 0.0)
                row_vals.append(qty)
                store_totals[k] += qty
                row_sum += qty
            row_vals.append(row_sum)
            grand_total += row_sum
            for col_idx, val in enumerate(row_vals, start=1):
                cell = ws.cell(row=r, column=col_idx, value=val)
                cell.border = border
                if col_idx == 2 or col_idx >= 5:
                    cell.number_format = '#,##0'
            r += 1

        total_row = r
        tvals = ['Tổng cộng:', '', '', '']
        for k in store_keys:
            tvals.append(store_totals[k])
        tvals.append(grand_total)
        for col_idx, val in enumerate(tvals, start=1):
            cell = ws.cell(row=total_row, column=col_idx, value=val)
            cell.font = bold
            cell.border = border
            if col_idx >= 5:
                cell.number_format = '#,##0'

        widths = [16, 14, 28, 10] + [12] * len(store_cols) + [12]
        for col_idx, w in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(col_idx)].width = w

        stream = io.BytesIO()
        wb.save(stream)
        return stream.getvalue()
