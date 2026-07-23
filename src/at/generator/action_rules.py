# SPDX-FileCopyrightText: 2026 Uniontech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only

"""Role-to-action mapping rules for precandidate pipeline.

Given a candidate node's role, the system auto-generates the action type
and default wait. AI does not need to decide these.

For menu items, a binary rule classifies main menu vs context menu
based on description context (not role alone).
"""

from __future__ import annotations

from typing import Any

ROLE_ACTION_MAP: dict[str, dict[str, Any]] = {
    "menu item": {
        "action": "element_action",
        "wait": 0.3,
        "do": "click",
    },
    "menu": {
        "action": "element_action",
        "wait": 0.3,
        "do": "click",
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

# Keywords for binary menu classification
_CONTEXT_MENU_KEYWORDS = frozenset(
    {"右键", "右击", "context menu", "右键菜单", "contextmenu", "right-click", "right click"}
)
_MAIN_MENU_KEYWORDS = frozenset(
    {"主菜单", "标题栏菜单", "menu bar", "menubar", "titlebar menu", "标题栏"}
)


def classify_menu_type(description: str, node: dict | None = None) -> str:
    """Classify a menu interaction as main menu or context menu.

    Binary rule based on description context and node location:
    - Description contains right-click keywords → dtk_context_menu
    - Description contains main-menu keywords → dtk_main_menu
    - Node in titlebar region → dtk_main_menu
    - Default fallback → dtk_context_menu (more general)

    Returns "dtk_main_menu" or "dtk_context_menu".
    """
    desc_lower = description.lower() if description else ""

    if any(kw in desc_lower for kw in _CONTEXT_MENU_KEYWORDS):
        return "dtk_context_menu"

    if any(kw in desc_lower for kw in _MAIN_MENU_KEYWORDS):
        return "dtk_main_menu"

    if node:
        parent_role = (node.get("role") or "").lower()
        comment = (node.get("comment") or "").lower()
        if "titlebar" in parent_role or "titlebar" in comment or "menu bar" in parent_role:
            return "dtk_main_menu"
        if "popup" in parent_role or "context" in comment:
            return "dtk_context_menu"

    return "dtk_context_menu"


def get_action_for_role(role: str) -> dict[str, Any]:
    """Get action config for a given AT-SPI role."""
    return ROLE_ACTION_MAP.get(role, DEFAULT_ACTION).copy()


def get_menu_action(description: str, node: dict | None = None) -> dict[str, Any]:
    """Get action config for a menu item, using binary classification.

    Returns either dtk_main_menu or dtk_context_menu config with requires field.
    """
    menu_type = classify_menu_type(description, node)
    return {
        "action": menu_type,
        "wait": 0.5,
        "requires": menu_type,
    }


def guess_role_from_description(description: str) -> str | None:
    """Guess AT-SPI role from description keywords (Chinese + English)."""
    desc_lower = description.lower()
    for role, keywords in ROLE_KEYWORDS.items():
        for kw in keywords:
            if kw in desc_lower:
                return role
    return None
