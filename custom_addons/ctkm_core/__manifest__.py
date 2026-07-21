# -*- coding: utf-8 -*-
{
    'name': 'Chương trình khuyến mãi',
    'version': '3.15',
    'category': 'Marketing/Promotions',
    'summary': 'Quản lý chương trình khuyến mãi',
    'description': """
Quản lý chương trình khuyến mãi
================================

Module cung cấp quản lý các chương trình khuyến mãi.
""",
    'depends': ['mail', 'hr_employee_hrm_detail', 'business_discuss_bots'],
    'data': [
        'security/ctkm_security.xml',
        'security/ir.model.access.csv',
        'views/ctkm_menu_views.xml',
        'views/ctkm_stage_views.xml',
        'views/ctkm_program_views.xml',
        'views/ctkm_notify_report_views.xml',
        'views/ctkm_task_views.xml',
        'data/ctkm_task_hooks.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'ctkm_core/static/src/scss/ctkm_notify_report.scss',
            'ctkm_core/static/src/css/ctkm_task_status.css',
            'ctkm_core/static/src/js/pivot_notify_detail_patch.js',
            (
                'after',
                'mail/static/src/chatter/web/chatter_patch.js',
                'ctkm_core/static/src/xml/chatter_patch.xml',
            ),
            (
                'after',
                'mail/static/src/chatter/web/chatter_patch.js',
                'ctkm_core/static/src/js/chatter_patch.js',
            ),
            (
                'after',
                'mail/static/src/core/common/attachment_list.js',
                'ctkm_core/static/src/js/attachment_list_patch.js',
            ),
            (
                'after',
                'mail/static/src/discuss/core/common/attachment_model_patch.js',
                'ctkm_core/static/src/js/attachment_patch.js',
            ),
            (
                'after',
                'mail/static/src/core/web/store_service_patch.js',
                'ctkm_core/static/src/js/discuss_detail_link_patch.js',
            ),
        ],
    },
    'installable': True,
    'author': 'CTKM',
    'license': 'LGPL-3',
}
