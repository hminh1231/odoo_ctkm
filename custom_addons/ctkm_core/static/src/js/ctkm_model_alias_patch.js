/** @odoo-module **/

import { ORM } from "@web/core/orm_service";
import { View } from "@web/views/view";
import { browser } from "@web/core/browser/browser";
import { patch } from "@web/core/utils/patch";

const CTKM_MODEL_ALIASES = {
    "ctkm-my-tasks": "ctkm.task",
};

function resolveCtkmModel(model) {
    return CTKM_MODEL_ALIASES[model] || model;
}

function rewriteActionState(state) {
    if (!state || typeof state !== "object") return state;
    if (state.model && CTKM_MODEL_ALIASES[state.model]) {
        state.model = CTKM_MODEL_ALIASES[state.model];
    }
    if (state.action === "ctkm-my-tasks") {
        delete state.action;
        state.model = state.model || "ctkm.task";
    }
    if (Array.isArray(state.actionStack)) {
        for (const item of state.actionStack) {
            if (!item || typeof item !== "object") continue;
            if (item.model && CTKM_MODEL_ALIASES[item.model]) {
                item.model = CTKM_MODEL_ALIASES[item.model];
            }
            if (item.action === "ctkm-my-tasks") {
                delete item.action;
                item.model = item.model || "ctkm.task";
            }
        }
    }
    return state;
}

// Fix corrupted sessionStorage from old deep links.
try {
    const raw = browser.sessionStorage.getItem("current_state");
    if (raw && raw.includes("ctkm-my-tasks")) {
        const parsed = JSON.parse(raw);
        browser.sessionStorage.setItem(
            "current_state",
            JSON.stringify(rewriteActionState(parsed))
        );
    }
} catch {
    // ignore
}

// Patch ORM.call: rewrite model before any RPC.
patch(ORM.prototype, {
    call(model, method, args = [], kwargs = {}) {
        return super.call(resolveCtkmModel(model), method, args, kwargs);
    },
});

// Patch View.loadView: rewrite resModel in props before calling viewService.
patch(View.prototype, {
    async loadView(props) {
        const resolved = resolveCtkmModel(props.resModel);
        const newProps = resolved !== props.resModel
            ? { ...props, resModel: resolved }
            : props;
        return super.loadView(newProps);
    },
});
