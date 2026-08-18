# -*- coding: utf-8 -*-

from odoo import api, models


def _code_variants(code):
    """Các dạng mã có thể khớp: hoa/thường, gạch ngang/gạch dưới, EAN/UPC."""
    raw = (code or '').strip()
    if not raw:
        return []
    variants = {
        raw,
        raw.upper(),
        raw.replace(' ', ''),
        raw.replace(' ', '').upper(),
    }
    compact = ''.join(raw.split()).upper()
    variants.add(compact)
    variants.add(compact.replace('-', '_'))
    variants.add(compact.replace('_', '-'))
    digits = ''.join(ch for ch in raw if ch.isdigit())
    if digits:
        variants.add(digits)
        stripped = digits.lstrip('0')
        if stripped:
            variants.add(stripped)
        if len(digits) == 12:
            variants.add('0' + digits)
        if len(digits) == 13 and digits.startswith('0'):
            variants.add(digits[1:])
    return [value for value in variants if value]


class CtkmBarcodeLookup(models.TransientModel):
    _name = 'ctkm.barcode.lookup'
    _description = 'Quét mã vạch CTKM'

    @api.model
    def lookup_code(self, code):
        scanned = (code or '').strip()
        result = {
            'scanned': scanned,
            'found': False,
            'matches': [],
        }
        if not scanned:
            return result
        if 'ctkm.inventory.tem.tag' not in self.env:
            return result

        Inventory = self.env['ctkm.inventory.tem.tag']
        variants = _code_variants(scanned)
        domain = [('material_code', 'in', variants)]
        if 'barcode' in Inventory._fields:
            domain = ['|', ('barcode', 'in', variants), ('material_code', 'in', variants)]
        records = Inventory.search(domain, limit=80, order='date desc, id desc')
        if not records and any(ch.isalpha() for ch in scanned):
            records = Inventory.search(
                [('material_code', 'ilike', scanned)],
                limit=80,
                order='date desc, id desc',
            )

        matches = []
        for rec in records:
            program = rec.program_id
            item = {
                'id': rec.id,
                'program_id': program.id,
                'program_name': program.display_name or '',
                'notify_code': program.notify_code or '',
                'date_begin': program.date_begin.isoformat() if program.date_begin else '',
                'date_end': program.date_end.isoformat() if program.date_end else '',
                'material_code': rec.material_code or '',
                'tem_tag': rec.tem_tag or '',
                'promo_price': rec.promo_price or 0.0,
                'store': rec.store or '',
                'quantity': rec.quantity or 0.0,
                'replaced_quantity': rec.replaced_quantity or 0.0,
                'date': rec.date.isoformat() if rec.date else '',
            }
            if 'barcode' in rec._fields:
                item['barcode'] = rec.barcode or ''
            matches.append(item)

        result['found'] = bool(matches)
        result['matches'] = matches
        return result
