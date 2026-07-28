# -*- coding: utf-8 -*-

from odoo.addons.web.controllers import action as action_mod

_CTKM_MODEL_ALIASES = {
    "ctkm-my-tasks": "ctkm.task",
}

_original_load_breadcrumbs = action_mod.Action.load_breadcrumbs


def _ctkm_load_breadcrumbs(self, actions):
    for action in actions or []:
        model = action.get("model")
        if model in _CTKM_MODEL_ALIASES:
            action["model"] = _CTKM_MODEL_ALIASES[model]
        if action.get("action") == "ctkm-my-tasks":
            action.pop("action", None)
            action["model"] = action.get("model") or "ctkm.task"
    return _original_load_breadcrumbs(self, actions)


action_mod.Action.load_breadcrumbs = _ctkm_load_breadcrumbs
