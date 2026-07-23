import { Component } from "@odoo/owl";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { STATIC_ACTIONS_GROUP_NUMBER } from "@web/search/action_menus/action_menus";

const cogMenuRegistry = registry.category("cogMenu");

export class CtkmInventoryImportMenu extends Component {
    static template = "ctkm_inventory.ImportMenu";
    static components = { DropdownItem };
    static props = {};

    setup() {
        this.action = useService("action");
    }

    openImportWizard() {
        this.action.doAction("ctkm_inventory.action_ctkm_inventory_import_wizard");
    }
}

export const ctkmInventoryImportMenu = {
    Component: CtkmInventoryImportMenu,
    groupNumber: STATIC_ACTIONS_GROUP_NUMBER,
    isDisplayed: ({ config, isSmall, searchModel }) =>
        !isSmall &&
        config.actionType === "ir.actions.act_window" &&
        config.viewType === "list" &&
        searchModel.resModel === "ctkm.inventory.tem.tag",
};

cogMenuRegistry.add("ctkm-inventory-import-menu", ctkmInventoryImportMenu, { sequence: 1 });
