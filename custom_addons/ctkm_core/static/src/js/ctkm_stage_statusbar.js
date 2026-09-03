/** @odoo-module **/

import { useEffect, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useRecordObserver } from "@web/model/relational_model/utils";
import { StatusBarField, statusBarField } from "@web/views/fields/statusbar/statusbar_field";

function progressEntry(value) {
    if (value && typeof value === "object" && !Array.isArray(value)) {
        return {
            state: value.state || "todo",
            percent: readPercent(value.percent),
        };
    }
    if (typeof value === "string") {
        return { state: value || "todo", percent: null };
    }
    return { state: "todo", percent: null };
}

function readPercent(raw) {
    if (raw === false || raw === null || raw === undefined || raw === "") {
        return null;
    }
    const value = Number(raw);
    if (!Number.isFinite(value)) {
        return null;
    }
    return Math.max(0, Math.min(100, Math.round(value)));
}

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
        mapping[String(key)] = progressEntry(value);
    }
    return mapping;
}

function mappingFromRecord(record) {
    const jsonMap = normalizeProgressMap(
        record.data.stage_progress_json || record.data.program_stage_progress_json
    );
    const lines = record.data.checklist_line_ids;
    if (lines?.records?.length) {
        const mapping = {};
        let found = false;
        for (const line of lines.records) {
            const stage = line.data.stage_id;
            if (stage?.id) {
                const id = String(stage.id);
                const jsonEntry = jsonMap[id] || progressEntry(null);
                mapping[id] = {
                    state: line.data.state || jsonEntry.state || "todo",
                    percent: readPercent(line.data.work_percent) ?? jsonEntry.percent,
                };
                found = true;
            }
        }
        if (found) {
            return mapping;
        }
    }
    return jsonMap;
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

function withPercentLabel(label, percent) {
    if (percent === null || percent === undefined) {
        return label;
    }
    const text = String(label || "");
    if (/\d+\s*%\s*$/.test(text)) {
        return text.replace(/\s*\d+\s*%\s*$/, ` ${percent}%`);
    }
    return `${text} ${percent}%`;
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

    getStageEntry(stageId) {
        return progressEntry(this.getStageProgressMap()[String(stageId)]);
    }

    getCurrentWorkStageId() {
        return this.progressState.currentId || false;
    }

    getAllItems() {
        const items = super.getAllItems();
        const currentId = this.getCurrentWorkStageId();
        return items.map((item) => {
            const entry = this.getStageEntry(item.value);
            return {
                ...item,
                label: withPercentLabel(item.label, entry.percent),
                isSelected: currentId
                    ? Number(item.value) === Number(currentId)
                    : item.isSelected,
            };
        });
    }

    /**
     * Keep overflow "..." menus, but do not let clicks move the official stage.
     * Visible focus always follows the in-progress / nearest todo checklist step.
     */
    async selectItem() {
        return;
    }

    _progressForItems(items) {
        const states = (items || []).map(
            (item) => this.getStageEntry(item.value).state
        );
        if (states.includes("progress")) {
            return "progress";
        }
        if (states.length && states.every((state) => state === "done")) {
            return "done";
        }
        return "todo";
    }

    _percentForItems(items) {
        const percents = (items || [])
            .map((item) => this.getStageEntry(item.value).percent)
            .filter((value) => value !== null && value !== undefined);
        if (!percents.length) {
            return null;
        }
        return Math.round(
            percents.reduce((sum, value) => sum + value, 0) / percents.length
        );
    }

    applyProgressClasses() {
        const root = this.rootRef?.el;
        if (!root) {
            return;
        }
        for (const btn of root.querySelectorAll(".o_arrow_button[data-value]")) {
            const entry = this.getStageEntry(btn.dataset.value);
            btn.setAttribute("data-progress", entry.state || "todo");
            if (entry.percent === null || entry.percent === undefined) {
                btn.removeAttribute("data-percent");
                btn.style.removeProperty("--ctkm-pct");
            } else {
                btn.setAttribute("data-percent", String(entry.percent));
                btn.style.setProperty("--ctkm-pct", String(entry.percent));
            }
            if (!btn.classList.contains("dropdown-toggle")) {
                let fill = btn.querySelector(":scope > .o_ctkm_sb_fill");
                let label = btn.querySelector(":scope > .o_ctkm_sb_label");
                const base = String(label?.textContent || btn.textContent || "")
                    .replace(/\s*\d+\s*%\s*$/, "")
                    .trim();
                if (entry.percent === null || entry.percent === undefined) {
                    if (fill) {
                        fill.remove();
                    }
                } else {
                    if (!fill) {
                        fill = document.createElement("span");
                        fill.className = "o_ctkm_sb_fill";
                        btn.insertBefore(fill, btn.firstChild);
                    }
                    fill.style.width = `${entry.percent}%`;
                }
                btn.childNodes.forEach((node) => {
                    if (node.nodeType === Node.TEXT_NODE) {
                        node.remove();
                    }
                });
                if (!label) {
                    label = document.createElement("span");
                    label.className = "o_ctkm_sb_label";
                    btn.appendChild(label);
                }
                label.textContent = withPercentLabel(base, entry.percent);
                if (entry.percent !== null && entry.percent !== undefined) {
                    btn.title = `${base} — ${entry.percent}%`;
                } else {
                    btn.removeAttribute("title");
                }
            }
        }
        const applyGroup = (el, items) => {
            if (!el) {
                return;
            }
            el.setAttribute("data-progress", this._progressForItems(items));
            const percent = this._percentForItems(items);
            if (percent === null) {
                el.removeAttribute("data-percent");
                el.style.removeProperty("--ctkm-pct");
            } else {
                el.setAttribute("data-percent", String(percent));
                el.style.setProperty("--ctkm-pct", String(percent));
            }
        };
        applyGroup(this.beforeRef?.el, this.items.before);
        applyGroup(this.afterRef?.el, this.items.after);
    }

    getDropdownItemClassNames(item) {
        const state = this.getStageEntry(item.value).state;
        return `${super.getDropdownItemClassNames(item)} o_ctkm_stage_${state}`;
    }
}

export const ctkmStageStatusBarField = {
    ...statusBarField,
    component: CtkmStageStatusBarField,
    additionalClasses: ["o_field_statusbar"],
};

registry.category("fields").add("ctkm_stage_statusbar", ctkmStageStatusBarField);
