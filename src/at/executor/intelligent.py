# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only
"""Intelligent accessible_id dispatch.

Unified entry for `selector.accessible_id` (the source-level QObject::objectName,
encoded by Qt6 bridge into the accessible_id dotted-path suffix). The engine
classifies the located node and dispatches the right runtime behavior, so test
suites only write the code-level objectName — no dtk_dropdown_menu / items /
menu-type specifics.

Classification (all verified against deepin-editor, Qt6/DTK6):

| Node | Closed-state AT-SPI | Click | Assert |
|------|--------------------|-------|--------|
| normal widget | showing / valid coords | direct | exists |
| menu item | name=display text, parent=popup menu | auto menu-nav | exists |
| DDropdownMenu trigger | showing, several share same aid | direct | exists |

Menu item clicking cannot be direct (popup items vanish from AT-SPI once the
menu opens — Qt6 bridge does not expose DMenu popup content). The engine
therefore: resolves display text from the closed-state node name, identifies
the parent menu type from the popup accessible_id segment pattern, opens the
menu via the appropriate trigger, then keyboard-navigates via AtMenuNavigator.
"""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)
_MENU_TYPE_PATTERNS: list[tuple[tuple[str, ...], str]] = [
    # DropdownMenu segment → DDropdownMenu trigger button (click it)
    (("DropdownMenu",), "dropdown"),
    # Menu_N segment → main menu (Alt + arrow navigation)
    (("Menu", "Menu_"), "main"),
    # QMenu segment → context menu (needs a trigger point; fall back to
    # AtMenuNavigator keyboard nav if the menu is already open)
    (("QMenu",), "context"),
]


def classify_menu_type(popup_aid: str) -> str:
    """Classify a menu's trigger strategy from its popup accessible_id.

    Verified patterns (deepin-editor):
      EditorApplication.DropdownMenu           → dropdown (DDropdownMenu)
      EditorApplication.Menu_2                 → main menu
      EditorApplication.QMenu / QMenu.*        → context / generic
    """
    if not popup_aid:
        return "context"
    for segments, kind in _MENU_TYPE_PATTERNS:
        for seg in segments:
            for part in popup_aid.split("."):
                if part == seg or part.startswith(seg):
                    return kind
    return "context"


def resolve_display_text(node) -> str:
    """Display text of a closed-state menu item node (its AT-SPI name)."""
    try:
        return getattr(node, "name", "") or ""
    except BaseException:
        return ""


def _find_menu_trigger(dog, popup_aid: str, index: int | None = None):
    """Find the trigger button for a dropdown menu (best effort).

    DDropdownMenu trigger buttons share the same accessible_id suffix
    (PToolButton) across menus; they are distinguished by screen position,
    which the popup does not expose. Strategy: search buttons whose full
    accessible_id contains the same segment as the popup (e.g. both contain
    'DropdownMenu'), pick showing ones, apply index if given.
    """
    try:
        from src.at.executor.handlers import find_element
    except ImportError:  # pragma: no cover
        find_element = None

    # The trigger button's aid contains the same distinguishing segment as
    # the popup (e.g. '...BottomBar.DDropdownMenu.PToolButton' ↔
    # 'EditorApplication.DropdownMenu' share 'DropdownMenu').
    popup_segs = set(popup_aid.split("."))
    shared_seg = None
    for seg in ("DropdownMenu", "DDropdownMenu"):
        if seg in popup_segs:
            shared_seg = seg
            break
    if not shared_seg:
        return None

    candidates = []
    try:
        # Walk the app tree for buttons whose aid contains the shared segment
        buttons = dog.find_elements_by_accessible_id("PToolButton") or []
        for n in buttons:
            try:
                aid = n.get_accessible_id() or ""
                if shared_seg in aid and n.showing:
                    candidates.append(n)
            except BaseException:
                continue
    except BaseException:
        return None

    if not candidates:
        return None
    if index is not None:
        try:
            return candidates[index]
        except IndexError:
            return None
    return candidates[0]


def act_on_menu_item(dog, node, action: str, attrs: dict, context: dict) -> None:
    """Click/right-click a menu item via automatic menu navigation.

    Steps:
      1. display text ← closed-state node name (no hand-copied UI text)
      2. parent popup ← node.parent; classify trigger strategy
      3. open the menu (dropdown: click trigger button; main/context: rely
         on AtMenuNavigator which handles its own keyboard/event fallbacks)
      4. AtMenuNavigator.select([display_text]) — DMenu keyboard loop
    """
    display_text = resolve_display_text(node)
    if not display_text:
        raise ValueError(f"menu item has no display text: {attrs}")

    parent = None
    try:
        parent = node.parent
    except BaseException:
        pass
    popup_aid = ""
    if parent is not None:
        try:
            popup_aid = parent.get_accessible_id() or ""
        except BaseException:
            popup_aid = ""
    menu_kind = classify_menu_type(popup_aid)

    # Open the menu before navigating.
    if menu_kind == "dropdown":
        trigger = _find_menu_trigger(dog, popup_aid, attrs.get("index"))
        if trigger is not None:
            trigger.click()
            time.sleep(0.5)
        else:
            # No trigger found — maybe the menu is already open. Proceed to
            # keyboard navigation anyway.
            logger.warning(
                "dtk menu item: no dropdown trigger found for popup %r; "
                "assuming menu already open", popup_aid,
            )

    from src.at.executor.menu_nav import AtMenuNavigator

    nav = AtMenuNavigator(context.get("app", ""))
    try:
        nav.select([display_text], exact=True)
    except BaseException:
        nav.cancel()
        raise


def is_menu_item(node) -> bool:
    """True if the node is a closed-state menu item (role menu item)."""
    try:
        role = getattr(node, "roleName", "") or ""
        if not isinstance(role, str):
            return False
        return "menu item" in role.lower()
    except BaseException:
        return False


def dispatch(dog, attrs: dict, action: str, context: dict, element=None) -> Any:
    """Unified dispatch for accessible_id selectors.

    Returns the resolved element for callers that need it (assert uses the
    node's existence; click performs the action). Raises ElementNotFound /
    ValueError on failure.
    """
    from src.at.executor.handlers import ElementNotFound, find_element

    if element is None:
        idx = attrs.get("index", 0)
        element = find_element(dog, attrs, idx)

    if is_menu_item(element) and action in ("click", "right_click", "double_click"):
        act_on_menu_item(dog, element, action, attrs, context)
        return True

    # Normal widget: caller handles the actual action.
    return False
