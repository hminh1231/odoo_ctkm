/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { ListController } from "@web/views/list/list_controller";
import { useService } from "@web/core/utils/hooks";

export class CtkmStoreProgressMatrix extends Component {
    static template = "ctkm_core.CtkmStoreProgressMatrix";
    static props = {
        onFilterProgram: { type: Function, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");

        const savedCollapsed = window.localStorage.getItem("ctkm_matrix_collapsed");
        this.state = useState({
            collapsed: savedCollapsed === "true",
            loading: false,
            hasData: false,
            stores: [],
            programs: [],
            selectedCell: null,
        });

        onWillStart(async () => {
            await this.loadMatrix();
        });
    }

    async loadMatrix() {
        this.state.loading = true;
        try {
            const res = await this.orm.call("ctkm.task", "get_user_store_progress_matrix", []);
            if (res && res.has_data) {
                this.state.hasData = true;
                this.state.stores = res.stores || [];
                this.state.programs = res.programs || [];
            } else {
                this.state.hasData = false;
                this.state.stores = res?.stores || [];
                this.state.programs = [];
            }
        } catch (e) {
            console.error("Lỗi khi tải ma trận tiến độ cửa hàng:", e);
        } finally {
            this.state.loading = false;
        }
    }

    toggleCollapse() {
        this.state.collapsed = !this.state.collapsed;
        window.localStorage.setItem("ctkm_matrix_collapsed", String(this.state.collapsed));
    }

    onCellClick(program, store, cell) {
        if (!cell) {
            return;
        }
        this.state.selectedCell = {
            programId: program.id,
            programName: program.name,
            storeName: store.name || store.code,
            ...cell,
        };
        if (this.props.onFilterProgram) {
            this.props.onFilterProgram(program.id, cell.task_id);
        }
    }

    closeSelectedCell() {
        this.state.selectedCell = null;
    }

    openSelectedTask() {
        const taskId = this.state.selectedCell?.task_id;
        if (!taskId) {
            return;
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "ctkm.task",
            res_id: taskId,
            views: [[false, "form"]],
            target: "current",
        });
    }
}

export class CtkmTaskListMatrixController extends ListController {
    static template = "ctkm_core.CtkmTaskListMatrixView";
    static components = {
        ...ListController.components,
        CtkmStoreProgressMatrix,
    };

    onFilterProgram(programId, taskId) {
        if (!programId) {
            return;
        }
        if (this.env.searchModel) {
            const domain = [["program_id", "=", programId]];
            if (typeof this.env.searchModel.splitAndAddDomain === "function") {
                this.env.searchModel.splitAndAddDomain(domain);
            }
        }
    }
}

export const ctkmTaskListWithMatrix = {
    ...listView,
    Controller: CtkmTaskListMatrixController,
};

registry.category("views").add("ctkm_task_list_with_matrix", ctkmTaskListWithMatrix);
