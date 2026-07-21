/** @odoo-module **/

import { Store } from "@mail/core/common/store_service";
import { browser } from "@web/core/browser/browser";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";

// Inline CSS so status colors load even if separate asset files are skipped.
(function injectCtkmTaskStatusColors() {
    if (document.getElementById("ctkm_task_status_colors")) {
        return;
    }
    const style = document.createElement("style");
    style.id = "ctkm_task_status_colors";
    style.textContent = `
.o_ctkm_task_list .o_field_selection_badge span.badge[raw-value="todo"],
.o_ctkm_task_list .o_field_selection_badge .o_selection_badge[value='"todo"'],
.o_ctkm_task_list .o_field_selection_badge .badge[value='"todo"'] {
    background-color: #adb5bd !important;
    color: #212529 !important;
    border-color: #868e96 !important;
}
.o_ctkm_task_list .o_field_selection_badge span.badge[raw-value="progress"],
.o_ctkm_task_list .o_field_selection_badge .o_selection_badge[value='"progress"'],
.o_ctkm_task_list .o_field_selection_badge .badge[value='"progress"'] {
    background-color: #ffc107 !important;
    color: #212529 !important;
    border-color: #e0a800 !important;
}
.o_ctkm_task_list .o_field_selection_badge span.badge[raw-value="done"],
.o_ctkm_task_list .o_field_selection_badge .o_selection_badge[value='"done"'],
.o_ctkm_task_list .o_field_selection_badge .badge[value='"done"'] {
    background-color: #28a745 !important;
    color: #ffffff !important;
    border-color: #1e7e34 !important;
}
.o_ctkm_task_list td.o_list_button > div {
    flex-direction: column !important;
    align-items: flex-start !important;
    flex-wrap: nowrap !important;
    gap: 2px !important;
}
.o_ctkm_task_list td.o_list_button > div > button {
    justify-content: flex-start;
}`;
    (document.head || document.documentElement).appendChild(style);
})();

const CTKM_DETAIL_BTN_SELECTOR = "a.o_ctkm_notify_detail_btn";
const CTKM_TASKS_PATH = "/odoo/ctkm-my-tasks";

function extractCtkmProgramId(link) {
    const fromDataset = Number(
        link.dataset.programId ||
            (link.dataset.oeModel === "ctkm.program" ? link.dataset.oeId : 0) ||
            0
    );
    if (fromDataset) {
        return fromDataset;
    }
    try {
        const href = link.getAttribute("href") || "";
        const url = new URL(href, window.location.origin);
        return Number(url.searchParams.get("ctkm_program_id") || 0);
    } catch {
        return 0;
    }
}

function rememberCtkmApp(menus) {
    const taskMenu =
        menus.getAll().find((m) => m.actionPath === "ctkm-my-tasks") ||
        menus.getApps().find((app) => String(app.name || "").toUpperCase().includes("CTKM"));
    if (taskMenu) {
        browser.sessionStorage.setItem("menu_id", String(taskMenu.appID || taskMenu.id));
    }
}

patch(Store.prototype, {
    handleClickOnLink(ev, thread) {
        const link = ev.target?.closest?.(CTKM_DETAIL_BTN_SELECTOR);
        if (!link) {
            return super.handleClickOnLink(...arguments);
        }
        ev.preventDefault();
        ev.stopPropagation();
        const programId = extractCtkmProgramId(link);
        if (!programId) {
            this.env.services.notification.add(
                _t("Tin nhắn cũ chưa gắn chương trình. Vui lòng Gửi tin lại từ CTKM."),
                { type: "warning" }
            );
            return true;
        }
        // Tạo/mở task rồi redirect full page → navbar CTKM.
        this.env.services.orm
            .call("ctkm.task", "action_open_for_program", [programId])
            .then((action) => {
                rememberCtkmApp(this.env.services.menu);
                const url =
                    (action && action.type === "ir.actions.act_url" && action.url) ||
                    CTKM_TASKS_PATH;
                browser.location.assign(url);
            })
            .catch((error) => {
                const message =
                    error?.data?.message ||
                    error?.message ||
                    _t("Không mở được công việc CTKM.");
                this.env.services.notification.add(message, { type: "danger" });
            });
        return true;
    },
});
