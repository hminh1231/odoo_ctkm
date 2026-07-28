# -*- coding: utf-8 -*-
"""Remap legacy action-path used as model name (ctkm-my-tasks → ctkm.task)."""

from odoo.modules.registry import Registry

_CTKM_MODEL_ALIASES = {
    "ctkm-my-tasks": "ctkm.task",
}

_original_registry_getitem = Registry.__getitem__


def _ctkm_registry_getitem(self, model_name):
    return _original_registry_getitem(
        self, _CTKM_MODEL_ALIASES.get(model_name, model_name)
    )


Registry.__getitem__ = _ctkm_registry_getitem
