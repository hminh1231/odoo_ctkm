/** @odoo-module **/

import { WebClient } from "@web/webclient/webclient";
import { browser } from "@web/core/browser/browser";
import { patch } from "@web/core/utils/patch";

function findCtkmAppMenu(menuService) {
    const all = menuService.getAll();
    return (
        all.find((m) => m.xmlid === "ctkm_core.ctkm_main_menu") ||
        all.find((m) => m.xmlid === "ctkm_core.menu_ctkm_my_tasks") ||
        all.find((m) => String(m.name || "").trim().toUpperCase() === "CTKM") ||
        menuService
            .getApps()
            .find((app) => String(app.name || "").toUpperCase().includes("CTKM"))
    );
}

function findCtkmMyTasksMenu(menuService) {
    const all = menuService.getAll();
    return (
        all.find((m) => m.xmlid === "ctkm_core.menu_ctkm_my_tasks") ||
        all.find((m) => m.actionPath === "ctkm-my-tasks") ||
        all.find((m) => String(m.name || "").includes("Công việc của tôi"))
    );
}

function isCtkmTaskContext(action, controller, pathname) {
    const resModel =
        action?.res_model ||
        controller?.props?.resModel ||
        controller?.currentState?.resModel;
    if (resModel === "ctkm.task") {
        return true;
    }
    if (action?.xml_id === "ctkm_core.action_ctkm_task_my") {
        return true;
    }
    if (action?.path === "ctkm-my-tasks") {
        return true;
    }
    if (/\/odoo\/(?:ctkm\.task|ctkm-my-tasks)(?:\/|$)/.test(pathname || "")) {
        return true;
    }
    return false;
}

/**
 * Deep link /odoo/ctkm.task/<id> không gắn được app menu → thanh trên trống.
 * Chuyển sang /odoo/ctkm-my-tasks/<id>?menu_id=... (có path action).
 */
function redirectCtkmModelUrlToAction(menuService) {
    const path = browser.location?.pathname || "";
    const match = path.match(/^\/odoo\/ctkm\.task\/(\d+)\/?$/);
    if (!match) {
        return false;
    }
    const taskId = match[1];
    const taskMenu = findCtkmMyTasksMenu(menuService);
    const appMenu = findCtkmAppMenu(menuService);
    const menuId = appMenu?.appID || appMenu?.id || taskMenu?.appID || "";
    const url = menuId
        ? `/odoo/ctkm-my-tasks/${taskId}?menu_id=${menuId}`
        : `/odoo/ctkm-my-tasks/${taskId}`;
    browser.location.replace(url);
    return true;
}

patch(WebClient.prototype, {
    setup() {
        super.setup(...arguments);
        const ensure = () => this._ctkmEnsureNavbarApp();
        this.env.bus.addEventListener("ACTION_MANAGER:UI-UPDATED", ensure);
        this.env.bus.addEventListener("ACTION_MANAGER:UPDATE", ensure);
    },

    async loadRouterState() {
        // Redirect trước khi load state nếu đang ở URL model thuần.
        if (redirectCtkmModelUrlToAction(this.menuService)) {
            // Trang sẽ reload sang URL mới; trả về true để tránh default app.
            return true;
        }
        const loaded = await super.loadRouterState(...arguments);
        this._ctkmEnsureNavbarApp();
        return loaded;
    },

    _ctkmEnsureNavbarApp() {
        try {
            const controller = this.actionService?.currentController;
            const action = controller?.action;
            if (
                !isCtkmTaskContext(
                    action,
                    controller,
                    browser.location?.pathname || ""
                )
            ) {
                return;
            }
            const currentApp = this.menuService.getCurrentApp?.();
            if (
                currentApp &&
                String(currentApp.name || "").toUpperCase().includes("CTKM")
            ) {
                return;
            }
            const ctkmApp = findCtkmAppMenu(this.menuService);
            if (!ctkmApp) {
                return;
            }
            this.menuService.setCurrentMenu(ctkmApp);
            browser.sessionStorage.setItem(
                "menu_id",
                String(ctkmApp.appID || ctkmApp.id)
            );
        } catch {
            // ignore — không chặn webclient
        }
    },
});
