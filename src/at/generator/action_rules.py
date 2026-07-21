# SPDX-FileCopyrightText: 2026 Uniontech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only

"""Role-to-action mapping rules for precandidate pipeline.

Given a candidate node's role, the system auto-generates the action type
and default wait. AI does not need to decide these.
"""

from __future__ import annotations

from typing import Any

ROLE_ACTION_MAP: dict[str, dict[str, Any]] = {
    "menu item": {
        "action": "dtk_main_menu",
        "wait": 0.5,
        "requires": "dtk_main_menu",
    },
    "menu": {
        "action": "dtk_context_menu",
        "wait": 0.5,
        "requires": "dtk_context_menu",
    },
    "button": {
        "action": "element_action",
        "wait": 0.3,
        "do": "click",
    },
    "check box": {
        "action": "element_action",
        "wait": 0.3,
        "do": "click",
    },
    "toggle button": {
        "action": "element_action",
        "wait": 0.3,
        "do": "click",
    },
    "radio button": {
        "action": "element_action",
        "wait": 0.3,
        "do": "click",
    },
    "text": {
        "action": "keyboard_type",
        "wait": 0.2,
    },
    "entry": {
        "action": "keyboard_type",
        "wait": 0.2,
    },
    "edit bar": {
        "action": "keyboard_type",
        "wait": 0.2,
    },
    "spin button": {
        "action": "keyboard_type",
        "wait": 0.2,
    },
    "list": {
        "action": "mouse_click",
        "wait": 0.5,
    },
    "tree": {
        "action": "mouse_click",
        "wait": 0.5,
    },
    "combo box": {
        "action": "mouse_click",
        "wait": 0.5,
    },
    "tab": {
        "action": "element_action",
        "wait": 0.3,
        "do": "click",
    },
    "page tab": {
        "action": "element_action",
        "wait": 0.3,
        "do": "click",
    },
    "slider": {
        "action": "mouse_click",
        "wait": 0.3,
    },
    "link": {
        "action": "element_action",
        "wait": 0.3,
        "do": "click",
    },
}

DEFAULT_ACTION: dict[str, Any] = {
    "action": "element_action",
    "wait": 0.3,
    "do": "click",
}

ROLE_KEYWORDS: dict[str, list[str]] = {
    "button": ["按钮", "button", "btn"],
    "check box": ["复选", "勾选", "checkbox", "check box"],
    "menu item": ["菜单项", "menu item"],
    "menu": ["菜单", "menu"],
    "text": ["文本", "text", "输入框", "input"],
    "entry": ["输入", "entry", "编辑", "edit"],
    "list": ["列表", "list"],
    "tree": ["树", "tree"],
    "combo box": ["下拉", "combo", "选择器"],
    "tab": ["标签", "tab"],
    "slider": ["滑块", "slider"],
    "link": ["链接", "link"],
}


def get_action_for_role(role: str) -> dict[str, Any]:
    """Get action config for a given AT-SPI role."""
    return ROLE_ACTION_MAP.get(role, DEFAULT_ACTION).copy()


def guess_role_from_description(description: str) -> str | None:
    """Guess AT-SPI role from description keywords (Chinese + English)."""
    desc_lower = description.lower()
    for role, keywords in ROLE_KEYWORDS.items():
        for kw in keywords:
            if kw in desc_lower:
                return role
    return None
