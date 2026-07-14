/** @odoo-module **/

import { Store } from "@mail/core/common/store_service";
import { patch } from "@web/core/utils/patch";

const CTKM_DETAIL_BTN_SELECTOR =
    "a.o_ctkm_notify_detail_btn[data-oe-action], a.o_ctkm_notify_detail_btn[href*='ctkm-my-tasks'], a.o_ctkm_notify_detail_btn[href*='action-']";

patch(Store.prototype, {
    handleClickOnLink(ev, thread) {
        const link = ev.target?.closest?.(CTKM_DETAIL_BTN_SELECTOR);
        if (link) {
            ev.preventDefault();
            const actionXmlId =
                link.dataset.oeAction || "ctkm_core.action_ctkm_program_my_activities";
            this.env.services.action.doAction(actionXmlId, {
                clearBreadcrumbs: true,
            });
            return true;
        }
        return super.handleClickOnLink(...arguments);
    },
});
