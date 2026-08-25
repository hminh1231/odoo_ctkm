/** @odoo-module **/

import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";

async function ctkmReportAccessDenied(env) {
    await new Promise((resolve) => {
        env.services.dialog.add(
            AlertDialog,
            {
                title: _t("Báo cáo"),
                body: _t("Bạn không đủ quyền hạn để xem mục này"),
                confirmLabel: _t("Đóng"),
                confirm: resolve,
            },
            {
                onClose: resolve,
            }
        );
    });
}

registry.category("actions").add("ctkm_report_access_denied", ctkmReportAccessDenied);
