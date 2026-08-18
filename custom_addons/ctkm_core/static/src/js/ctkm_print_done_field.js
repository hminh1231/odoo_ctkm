/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useRecordObserver } from "@web/model/relational_model/utils";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

export class CtkmPrintDoneField extends Component {
    static template = "ctkm_core.CtkmPrintDoneField";
    static props = { ...standardFieldProps };

    setup() {
        this.orm = useService("orm");
        this.state = useState({ value: false, saving: false });
        useRecordObserver((record) => {
            this.state.value = record.data[this.props.name];
        });
    }

    /** List gán readonly khi hàng chưa edit — không dùng cờ đó để chặn tick. */
    get isDisabled() {
        if (this.state.saving) {
            return true;
        }
        const record = this.props.record;
        if (typeof record._isReadonly === "function" && record._isReadonly(this.props.name)) {
            return true;
        }
        if (record.config?.mode === "readonly") {
            return true;
        }
        const parent = record._parentRecord;
        if (parent?.config?.mode === "readonly") {
            return true;
        }
        return false;
    }

    async onClick() {
        if (this.isDisabled) {
            return;
        }
        const record = this.props.record;
        const newValue = !record.data[this.props.name];
        this.state.value = newValue;
        if (!record.resId) {
            await record.update({ [this.props.name]: newValue });
            return;
        }
        this.state.saving = true;
        try {
            await this.orm.write("ctkm.task.tem.print.line", [record.resId], {
                done: newValue,
            });
            const parent = record._parentRecord || record.model.root;
            if (parent && typeof parent.load === "function") {
                await parent.load();
            }
        } catch (error) {
            this.state.value = !newValue;
            throw error;
        } finally {
            this.state.saving = false;
        }
    }
}

export const ctkmPrintDoneField = {
    component: CtkmPrintDoneField,
    supportedTypes: ["boolean"],
};

registry.category("fields").add("ctkm_print_done", ctkmPrintDoneField);
registry.category("fields").add("list.ctkm_print_done", ctkmPrintDoneField);
