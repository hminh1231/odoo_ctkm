# -*- coding: utf-8 -*-
{
    'name': 'Chương trình khuyến mãi',
    'version': '1.0',
    'category': 'Marketing/Promotions',
    'summary': 'Quản lý chương trình khuyến mãi',
    'description': """
Quản lý chương trình khuyến mãi
================================

Module cung cấp quản lý các chương trình khuyến mãi.
""",
    'depends': ['mail'],
    'data': [
        'security/ctkm_security.xml',
        'security/ir.model.access.csv',
        'views/ctkm_menu_views.xml',
        'views/ctkm_stage_views.xml',
        'views/ctkm_program_views.xml',
    ],
    'installable': True,
    'author': 'CTKM',
    'license': 'LGPL-3',
}
