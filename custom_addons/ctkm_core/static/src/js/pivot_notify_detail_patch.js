/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PivotRenderer } from "@web/views/pivot/pivot_renderer";
import { useService } from "@web/core/utils/hooks";

function extractNotifyCode(domain) {
    const stack = Array.isArray(domain) ? [...domain] : [];
    while (stack.length) {
        const leaf = stack.shift();
        if (Array.isArray(leaf) && leaf.length >= 3 && typeof leaf[0] === "string") {
            if (leaf[0] === "notify_code") {
                return leaf[2];
            }
        } else if (Array.isArray(leaf)) {
            stack.push(...leaf);
        }
    }
    return false;
}

patch(PivotRenderer.prototype, {
    setup() {
        super.setup(...arguments);
        this.orm = useService("orm");
    },

    _isCtkmNotifyReport() {
        if (this.model.metaData.resModel !== "ctkm.program") {
            return false;
        }
        const ctx = this.model.searchParams?.context || {};
        if (ctx.ctkm_notify_report) {
            return true;
        }
        const action = this.env.config?.action || {};
        return (
            action.path === "ctkm-reports" ||
            action.xml_id === "ctkm_core.action_ctkm_program_report"
        );
    },

    async _openNotifyCodeDetail(domain) {
        const notifyCode = extractNotifyCode(domain);
        const action = await this.orm.call(
            "ctkm.program",
            "action_open_notify_code_detail_by_code",
            [notifyCode || false, domain || []]
        );
        if (action) {
            await this.actionService.doAction(action, {
                stackPosition: "replaceCurrentAction",
            });
        }
    },

    /**
     * Bấm mã số thông báo trên hàng pivot → mở trang chi tiết.
     */
    async onHeaderClick(ev, cell, isXAxis) {
        if (!isXAxis && this._isCtkmNotifyReport() && cell?.groupId) {
            const group = { rowValues: cell.groupId[0], colValues: cell.groupId[1] };
            const domain = this.model.getGroupDomain(group);
            if (extractNotifyCode(domain)) {
                await this._openNotifyCodeDetail(domain);
                return;
            }
        }
        return super.onHeaderClick(ev, cell, isXAxis);
    },

    /**
     * Bấm ô số liệu pivot → cùng trang chi tiết theo mã TB.
     */
    async onOpenView(cell, newWindow) {
        if (cell.value === undefined || this.model.metaData.disableLinking) {
            return;
        }
        if (this._isCtkmNotifyReport()) {
            const group = { rowValues: cell.groupId[0], colValues: cell.groupId[1] };
            const domain = this.model.getGroupDomain(group);
            await this._openNotifyCodeDetail(domain);
            return;
        }
        return super.onOpenView(cell, newWindow);
    },
});
