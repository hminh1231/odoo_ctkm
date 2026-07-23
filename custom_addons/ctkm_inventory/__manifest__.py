# -*- coding: utf-8 -*-
{
    'name': 'CTKM Kho',
    'version': '1.0',
    'category': 'Marketing/Promotions',
    'summary': 'Quản lý tồn kho tem/tag cho CTKM',
    'depends': ['ctkm_core', 'base_import'],
    'external_dependencies': {
        'python': ['pandas', 'python_calamine'],
    },
    'data': [
        'security/ir.model.access.csv',
        'views/ctkm_inventory_import_wizard_views.xml',
        'views/ctkm_inventory_tem_tag_views.xml',
        'views/ctkm_inventory_menu_views.xml',
    ],
    'installable': True,
    'author': 'CTKM',
    'license': 'LGPL-3',
}
