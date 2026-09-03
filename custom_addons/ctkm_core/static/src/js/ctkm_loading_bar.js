/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

export class CtkmLoadingBarField extends Component {
    static template = "ctkm_core.CtkmLoadingBarField";
    static props = { ...standardFieldProps };

    get percent() {
        const raw = this.props.record.data[this.props.name];
        const value = Number(raw);
        if (!Number.isFinite(value)) {
            return 0;
        }
        return Math.max(0, Math.min(100, Math.round(value)));
    }

    get barClass() {
        const percent = this.percent;
        if (percent >= 100) {
            return "o_ctkm_loading_bar_done";
        }
        if (percent >= 50) {
            return "o_ctkm_loading_bar_high";
        }
        if (percent > 0) {
            return "o_ctkm_loading_bar_low";
        }
        return "o_ctkm_loading_bar_empty";
    }
}

export const ctkmLoadingBarField = {
    component: CtkmLoadingBarField,
    displayName: "Loading bar",
    supportedTypes: ["integer", "float"],
    additionalClasses: ["o_ctkm_loading_bar"],
};

registry.category("fields").add("ctkm_loading_bar", ctkmLoadingBarField);
