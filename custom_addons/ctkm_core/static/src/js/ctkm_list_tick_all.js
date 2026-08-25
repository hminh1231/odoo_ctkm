/** @odoo-module **/

import { useState } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { ListRenderer } from "@web/views/list/list_renderer";

function optionEnabled(options, key) {
    if (!options || typeof options !== "object") {
        return false;
    }
    const value = options[key];
    return value === true || value === "true" || value === 1 || value === "1";
}

patch(ListRenderer.prototype, {
    setup() {
        super.setup(...arguments);
        this.ctkmTickAllState = useState({
            saving: false,
            pending: null,
        });
    },

    isTickAllColumn(column) {
        return Boolean(
            column &&
                column.type === "field" &&
                (optionEnabled(column.options, "tick_all") ||
                    optionEnabled(column.options, "tickAll"))
        );
    },

    isSortable(column) {
        if (this.isTickAllColumn(column)) {
            return false;
        }
        return super.isSortable(column);
    },

    _ctkmTickAllRecords(column) {
        const records = this.props.list?.records || [];
        return records.filter((record) => {
            if (typeof record._isReadonly === "function" && record._isReadonly(column.name)) {
                return false;
            }
            return true;
        });
    },

    isTickAllChecked(column) {
        const pending = this.ctkmTickAllState.pending;
        if (pending && pending.columnName === column.name) {
            return pending.value;
        }
        const records = this._ctkmTickAllRecords(column);
        return records.length > 0 && records.every((record) => record.data[column.name]);
    },

    isTickAllIndeterminate(column) {
        const pending = this.ctkmTickAllState.pending;
        if (pending && pending.columnName === column.name) {
            return false;
        }
        const records = this._ctkmTickAllRecords(column);
        if (!records.length) {
            return false;
        }
        const checkedCount = records.filter((record) => record.data[column.name]).length;
        return checkedCount > 0 && checkedCount < records.length;
    },

    isTickAllDisabled(column) {
        if (this.ctkmTickAllState.saving) {
            return true;
        }
        return !this._ctkmTickAllRecords(column).length;
    },

    async onTickAllChange(column, checked) {
        if (this.ctkmTickAllState.saving || !this.isTickAllColumn(column)) {
            return;
        }
        const records = this._ctkmTickAllRecords(column);
        const savedIds = [];
        const unsaved = [];
        for (const record of records) {
            if (Boolean(record.data[column.name]) === Boolean(checked)) {
                continue;
            }
            if (record.resId) {
                savedIds.push(record.resId);
            } else {
                unsaved.push(record);
            }
        }
        if (!savedIds.length && !unsaved.length) {
            return;
        }
        this.ctkmTickAllState.saving = true;
        this.ctkmTickAllState.pending = { columnName: column.name, value: checked };
        try {
            if (typeof this.props.list.leaveEditMode === "function") {
                await this.props.list.leaveEditMode();
            }
            for (const record of unsaved) {
                await record.update({ [column.name]: checked });
            }
            if (savedIds.length) {
                const resModel = this.props.list.resModel || records[0]?.resModel;
                await this.orm.write(resModel, savedIds, { [column.name]: checked });
                const parent =
                    records[0]?._parentRecord ||
                    this.props.list._parent ||
                    this.props.list.model?.root;
                if (parent && typeof parent.load === "function") {
                    await parent.load();
                } else if (typeof this.props.list.load === "function") {
                    await this.props.list.load();
                }
            }
        } catch (error) {
            throw error;
        } finally {
            this.ctkmTickAllState.pending = null;
            this.ctkmTickAllState.saving = false;
        }
    },
});
