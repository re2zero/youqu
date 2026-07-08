# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only

HINT_ROLE_CONSTRAINTS: dict[str, dict[str, str]] = {
    "dtk_main_menu": {"parent_role": "menu_bar", "item_role": "menu_item"},
    "dtk_context_menu": {"requires_context": True},
    "titlebar": {"parent_role": "title_bar"},
    "toolbar": {"parent_role": "tool_bar"},
    "sidebar": {"role": "panel"},
    "tab_bar": {"role": "page_tab"},
    "dialog": {"role": "dialog"},
    "tooltip": {"role": "tool_tip"},
    "dock": {"role": "panel"},
}

STEP_TYPE_MAP: dict[str, str] = {
    "action": "element_action",
    "assert": "assert_element",
    "navigate": "element_action",
}
