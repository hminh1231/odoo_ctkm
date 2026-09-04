# -*- coding: utf-8 -*-
{
    'name': 'Chương trình khuyến mãi',
    'version': '4.38',
    'category': 'Marketing/Promotions',
    'summary': 'Quản lý chương trình khuyến mãi',
    'description': """
Quản lý chương trình khuyến mãi
================================

Module cung cấp quản lý các chương trình khuyến mãi.
""",
    'depends': ['mail', 'hr_employee_hrm_detail', 'hr_job_title_vn', 'hr_store', 'business_discuss_bots'],
    'data': [
        'security/ctkm_security.xml',
        'security/ir.model.access.csv',
        'data/ctkm_stage_default.xml',
        'views/ctkm_menu_views.xml',
        'views/ctkm_barcode_views.xml',
        'views/ctkm_stage_views.xml',
        'views/ctkm_program_views.xml',
        'views/ctkm_notify_report_views.xml',
        'views/ctkm_progress_report_views.xml',
        'views/ctkm_price_report_views.xml',
        'views/ctkm_violation_report_views.xml',
        'views/ctkm_task_views.xml',
        'data/ctkm_task_hooks.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'ctkm_core/static/src/js/ctkm_model_alias_patch.js',
            'ctkm_core/static/src/js/ctkm_print_done_field.js',
            'ctkm_core/static/src/xml/ctkm_print_done_field.xml',
            'ctkm_core/static/src/js/ctkm_list_tick_all.js',
            'ctkm_core/static/src/xml/ctkm_list_tick_all.xml',
            'ctkm_core/static/src/js/ctkm_navbar_app_patch.js',
            'ctkm_core/static/src/js/ctkm_report_access_denied.js',
            'ctkm_core/static/src/scss/ctkm_notify_report.scss',
            'ctkm_core/static/src/css/ctkm_task_status.css',
            'ctkm_core/static/src/js/ctkm_stage_statusbar.js',
            'ctkm_core/static/src/scss/ctkm_stage_statusbar.scss',
            'ctkm_core/static/src/js/ctkm_loading_bar.js',
            'ctkm_core/static/src/xml/ctkm_loading_bar.xml',
            'ctkm_core/static/src/scss/ctkm_loading_bar.scss',
            'ctkm_core/static/src/js/pivot_notify_detail_patch.js',
            'ctkm_core/static/src/js/ctkm_barcode_scan.js',
            'ctkm_core/static/src/xml/ctkm_barcode_scan.xml',
            'ctkm_core/static/src/scss/ctkm_barcode_scan.scss',
            'ctkm_core/static/src/js/ctkm_task_list_matrix.js',
            'ctkm_core/static/src/xml/ctkm_task_list_matrix.xml',
            'ctkm_core/static/src/scss/ctkm_task_list_matrix.scss',
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
    'application': True,
    'author': 'CTKM',
    'license': 'LGPL-3',
}
