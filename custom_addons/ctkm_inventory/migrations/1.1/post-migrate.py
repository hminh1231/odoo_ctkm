# -*- coding: utf-8 -*-


def migrate(cr, version):
    cr.execute(
        """
        UPDATE ctkm_inventory_tem_tag
           SET store_key = NULLIF(
               UPPER(BTRIM(REGEXP_REPLACE(COALESCE(store, ''), '[[:space:]]+', ' ', 'g'))),
               ''
           )
        """
    )
