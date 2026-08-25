/** @odoo-module **/

import { useEffect, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useRecordObserver } from "@web/model/relational_model/utils";
import { StatusBarField, statusBarField } from "@web/views/fields/statusbar/statusbar_field";

function normalizeProgressMap(raw) {
    if (!raw) {
        return {};
    }
    if (typeof raw === "string") {
        try {
            raw = JSON.parse(raw);
        } catch {
            return {};
        }
    }
    if (typeof raw !== "object" || Array.isArray(raw)) {
        return {};
    }
    const mapping = {};
    for (const [key, value] of Object.entries(raw)) {
        mapping[String(key)] = value || "todo";
    }
    return mapping;
}

function mappingFromRecord(record) {
    const lines = record.data.checklist_line_ids;
    if (lines?.records?.length) {
        const mapping = {};
        let found = false;
        for (const line of lines.records) {
            const stage = line.data.stage_id;
            if (stage?.id) {
                mapping[String(stage.id)] = line.data.state || "todo";
                found = true;
            }
        }
        if (found) {
            return mapping;
        }
    }
    return normalizeProgressMap(
        record.data.stage_progress_json || record.data.program_stage_progress_json
    );
}

function many2oneId(value) {
    if (!value) {
        return false;
    }
    return typeof value === "object" ? value.id : value;
}

function currentStageIdFromRecord(record) {
    const lines = record.data.checklist_line_ids;
    if (lines?.records?.length) {
        const sorted = [...lines.records].sort((a, b) => {
            const seqDiff = (a.data.sequence || 0) - (b.data.sequence || 0);
            return seqDiff || (a.resId || 0) - (b.resId || 0);
        });
        const progress = sorted.find(
            (line) => line.data.state === "progress" && line.data.stage_id?.id
        );
        if (progress) {
            return progress.data.stage_id.id;
        }
        const todo = sorted.find(
            (line) => line.data.state === "todo" && line.data.stage_id?.id
        );
        if (todo) {
            return todo.data.stage_id.id;
        }
        for (let index = sorted.length - 1; index >= 0; index--) {
            const stageId = sorted[index].data.stage_id?.id;
            if (stageId) {
                return stageId;
            }
        }
    }
    return many2oneId(
        record.data.checklist_current_stage_id
        || record.data.program_checklist_current_stage_id
    );
}

export class CtkmStageStatusBarField extends StatusBarField {
    setup() {
        super.setup();
        this.progressState = useState({ map: {}, currentId: false });
        useRecordObserver((record) => {
            this.progressState.map = mappingFromRecord(record);
            this.progressState.currentId = currentStageIdFromRecord(record);
        });
        useEffect(() => {
            this.applyProgressClasses();
        });
    }

    getStageProgressMap() {
        return this.progressState.map || {};
    }

    getCurrentWorkStageId() {
        return this.progressState.currentId || false;
    }

    getAllItems() {
        const items = super.getAllItems();
        const currentId = this.getCurrentWorkStageId();
        if (!currentId) {
            return items;
        }
        return items.map((item) => ({
            ...item,
            isSelected: Number(item.value) === Number(currentId),
        }));
    }

    /**
     * Keep overflow "..." menus, but do not let clicks move the official stage.
     * Visible focus always follows the in-progress / nearest todo checklist step.
     */
    async selectItem() {
        return;
    }

    _progressForItems(items) {
        const mapping = this.getStageProgressMap();
        const states = (items || []).map((item) => mapping[String(item.value)] || "todo");
        if (states.includes("progress")) {
            return "progress";
        }
        if (states.length && states.every((state) => state === "done")) {
            return "done";
        }
        return "todo";
    }

    applyProgressClasses() {
        const root = this.rootRef?.el;
        if (!root) {
            return;
        }
        const mapping = this.getStageProgressMap();
        for (const btn of root.querySelectorAll(".o_arrow_button[data-value]")) {
            btn.setAttribute("data-progress", mapping[String(btn.dataset.value)] || "todo");
        }
        if (this.beforeRef?.el) {
            this.beforeRef.el.setAttribute(
                "data-progress",
                this._progressForItems(this.items.before)
            );
        }
        if (this.afterRef?.el) {
            this.afterRef.el.setAttribute(
                "data-progress",
                this._progressForItems(this.items.after)
            );
        }
    }

    getDropdownItemClassNames(item) {
        const state = this.getStageProgressMap()[String(item.value)] || "todo";
        return `${super.getDropdownItemClassNames(item)} o_ctkm_stage_${state}`;
    }
}

export const ctkmStageStatusBarField = {
    ...statusBarField,
    component: CtkmStageStatusBarField,
    additionalClasses: ["o_field_statusbar"],
};

registry.category("fields").add("ctkm_stage_statusbar", ctkmStageStatusBarField);
