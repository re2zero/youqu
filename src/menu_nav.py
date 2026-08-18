#!/usr/bin/env python3
# _*_ coding:utf-8 _*_

# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only
"""Keyboard navigation menu module.

Uses ↑↓←→Enter to navigate DTK menus.
Dual strategy:
  - Tree walking for persistent menus (main menu bar)
  - AT-SPI event listening for transient popups (DMenu::exec() context menus)
"""

import time
import logging

logger = logging.getLogger(__name__)


class MenuNotFoundError(Exception):
    """Menu item not found."""

    pass


class MenuNavigator:
    """Keyboard navigation menu operator.

    Usage:
        nav = MenuNavigator("deepin-reader", "Deepin Reader")
        nav.open_main_menu()
        nav.select(["文件", "打开"])

        nav.open_context_menu(500, 300)
        nav.select(["复制"])
    """

    MAX_LOOP = 30  # Max iterations per menu level (cycle detection stops earlier)

    def __init__(self, name=None, desc=None):
        self.app_name = name
        self.desc = desc
        self.mk = None  # MouseKey instance, lazy init
        self._app_node = None  # Cached AT-SPI app node

    def _ensure_mk(self):
        """Lazy-init MouseKey to keep module importable without desktop."""
        if self.mk is None:
            from src.mouse_key import MouseKey

            self.mk = MouseKey()
        return self.mk

    def _ensure_app_node(self):
        """Lazy-init AT-SPI app node. Cached for entire navigation session."""
        if self._app_node is None:
            from src.dogtail_utils import DogtailUtils

            dog = DogtailUtils(self.app_name, self.desc) if self.app_name else DogtailUtils()
            self._app_node = dog.obj  # DogtailUtils.obj is the connected app node
        return self._app_node

    def open_main_menu(self):
        """Open main menu.

        Tries Alt key first (works for standard QMenuBar apps), then
        clicks the DTK titlebar menu button via AT-SPI as fallback.
        Falls back to clicking the first unnamed frame button for QML TitleBar apps.
        """
        self._ensure_mk().press_key("Alt")
        time.sleep(0.1)
        try:
            from src.dogtail_utils import DogtailUtils
            dog = DogtailUtils(self.app_name, self.desc) if self.app_name else DogtailUtils()
            btns = dog.find_elements_by_attr("$//DTitlebarDWindowOptionButton/")
            if btns:
                btn = btns[-1]
                if "Press" in getattr(btn, "actions", {}):
                    btn.doActionNamed("Press")
                else:
                    btn.click()
                time.sleep(0.15)
                return
        except BaseException:
            pass
        # Fallback: QML TitleBar has unnamed WindowButton as menu button.
        try:
            import pyatspi
            desktop = pyatspi.Registry.getDesktop(0)
            for i in range(desktop.childCount):
                app = desktop[i]
                if self.app_name and self.app_name.lower() in (app.name or "").lower():
                    for j in range(app.childCount):
                        child = app[j]
                        if child.getRoleName() == "frame":
                            for k in range(child.childCount):
                                btn = child[k]
                                if btn.getRoleName() == "button" and not btn.name:
                                    action = btn.queryAction()
                                    if action.get_nActions() > 0:
                                        action.doAction(0)
                                        time.sleep(0.3)
                                        return
        except Exception:
            pass

    def open_context_menu(self, x, y):
        """Open context menu via right-click at coordinates."""
        self._ensure_mk().right_click(x, y)
        time.sleep(0.1)

    def _walk_menu_items(self, node, max_depth=-1, _depth=0):
        """Recursively yield menu/menu_item nodes from AT-SPI tree.

        When ``max_depth >= 0``, stops recursion at that depth.
        """
        if max_depth >= 0 and _depth >= max_depth:
            return
        try:
            children = node.children if hasattr(node, "children") else []
        except Exception:
            return
        for child in children:
            try:
                role = getattr(child, "roleName", "").lower()
            except Exception:
                continue
            if role in (
                "menu item",
                "menu",
                "check menu item",
                "radio menu item",
                "push button",
            ):
                yield child
            yield from self._walk_menu_items(child, max_depth, _depth + 1)

    def _list_menu_items(self, from_root=False):
        """List all menu item names, regardless of focus."""
        node = self._ensure_app_node()
        items = self._walk_and_collect(node, max_depth=3)
        if not items and from_root:
            try:
                from src.depends.dogtail.tree import root as atspi_root

                items = self._walk_and_collect(atspi_root, max_depth=4)
            except Exception:
                pass
        return items

    def _walk_and_collect(self, node, max_depth=-1):
        """Walk AT-SPI subtree and collect (name, node) for menu items."""
        items = []
        for child in self._walk_menu_items(node, max_depth=max_depth):
            name = getattr(child, "name", "") or ""
            if name:
                items.append((name, child))
        return items

    def _read_focused_item(self, from_root=False):
        """Read current AT-SPI focused or selected menu item text."""
        app_node = self._ensure_app_node()
        result = self._scan_for_focused(app_node, max_depth=3)
        if not result and from_root:
            try:
                from src.depends.dogtail.tree import root as atspi_root

                result = self._scan_for_focused(atspi_root, max_depth=4)
            except Exception:
                pass
        return result

    def _scan_for_focused(self, node, max_depth=-1):
        """Walk *node* subtree and return name of first focused/selected menu item."""
        for child in self._walk_menu_items(node, max_depth=max_depth):
            try:
                states = set(
                    s.lower() for s in getattr(child, "states", []) if hasattr(child, "states")
                )
            except Exception:
                continue
            if "focused" in states or "selected" in states:
                return getattr(child, "name", "") or ""
        return ""

    def _enumerate_and_navigate(self, target, exact=False):
        """Find target by enumerating all menu items, navigate by index."""
        items = self._list_menu_items(from_root=True)
        if not items:
            return False

        for idx, (name, _) in enumerate(items):
            matched = name == target if exact else target.lower() in name.lower()
            if matched:
                for _ in range(idx):
                    self._ensure_mk().press_key("Down")
                    time.sleep(0.1)
                return True
        return False

    def _navigate_by_focus(self, target, exact=False):
        """Navigate to target using AT-SPI focused/selected state tracking.

        Depth-limited tree scan (max_depth=3) to avoid recursing into
        frame children. Popup menus + their menu items are at depth ≤ 3.

        Returns (False, "") when no focused item exists — signature that
        the menu is a transient popup (DMenu::exec()) where tree walking
        is useless and event-based navigation should take over.
        """
        start_text = self._scan_for_focused(self._ensure_app_node(), max_depth=3)
        if not start_text:
            return False, ""

        for iteration in range(self.MAX_LOOP):
            current = self._scan_for_focused(self._ensure_app_node(), max_depth=3)
            if not current:
                current = self._read_focused_item(from_root=True)

            if not current and not start_text and iteration > 0:
                return False, "菜单已关闭"

            matched = (
                (current == target)
                if exact
                else (target.lower() in current.lower() if current else False)
            )
            if matched:
                return True, current

            if iteration > 0 and current == start_text:
                return False, f"菜单项 '{target}' 不存在"

            self._ensure_mk().press_key("Down")
            time.sleep(0.1)

        return (
            False,
            f"菜单项 '{target}' 未找到 (超过 {self.MAX_LOOP} 次循环)",
        )

    def _navigate_by_events(self, target, exact=False):
        """Navigate to target using AT-SPI event listening.

        For DTK DMenu::exec() transient popup menus whose items are
        only visible through AT-SPI events, not the static tree.
        Runs a GLib main loop to dispatch events, using non-blocking
        timeouts for keypresses.
        """
        import gi
        gi.require_version('Atspi', '2.0')
        from gi.repository import Atspi, GLib

        focused_name = [""]  # Mutable container for event callback
        found = [False]
        iteration = [0]
        start_name = [None]
        mk = self._ensure_mk()

        def on_focus_event(event):
            try:
                if event.type == 'object:state-changed:focused' and event.detail1 == 1:
                    src = event.source
                    role = src.get_role_name() if src else ""
                    if 'menu' in role.lower():
                        focused_name[0] = src.get_name() or ""
            except Exception:
                pass

        listener = Atspi.EventListener.new(on_focus_event)
        Atspi.EventListener.register(listener, 'object:state-changed:focused')

        loop = GLib.MainLoop()

        def step():
            iteration[0] += 1
            current = focused_name[0]

            if start_name[0] is None and current:
                start_name[0] = current

            matched = False
            if current:
                matched = (current == target) if exact else (target.lower() in current.lower())

            if matched:
                found[0] = True
                loop.quit()
                return False

            if iteration[0] >= self.MAX_LOOP:
                loop.quit()
                return False

            if iteration[0] > 2 and current and current == start_name[0]:
                loop.quit()
                return False

            mk.press_key('Down')
            GLib.timeout_add(100, step)
            return False

        GLib.timeout_add(50, step)

        loop.run()
        Atspi.EventListener.deregister(listener, 'object:state-changed:focused')

        if found[0]:
            return True, focused_name[0]
        return False, f"菜单项 '{target}' 未找到"

    def navigate_to(self, items, exact=False):
        """Navigate to target menu item(s) using keyboard.

        Strategy chain (first successful wins):
        1. AT-SPI tree focused/selected state tracking (persistent menus)
        2. AT-SPI tree enumeration (fallback for visible menu trees)
        3. AT-SPI event listening (transient DMenu::exec() popups)

        Args:
            items: Menu path, e.g. ["文件", "打开"] or ["复制"]
            exact: True=exact match, False=substring match (case-insensitive)

        Raises:
            MenuNotFoundError: target item not found or menu closed unexpectedly
        """
        event_mode = False
        for i, target in enumerate(items):
            ok = False
            err = ""
            if event_mode:
                ok, err = self._navigate_by_events(target, exact)
            else:
                ok, err = self._navigate_by_focus(target, exact)
                if not ok and not err:
                    ok, err = self._navigate_by_events(target, exact)
                elif not ok:
                    if not self._enumerate_and_navigate(target, exact):
                        raise MenuNotFoundError(err or f"菜单项 '{target}' 未找到")

            if ok:
                event_mode = True
            elif not event_mode:
                raise MenuNotFoundError(err or f"菜单项 '{target}' 未找到")
            else:
                raise MenuNotFoundError(err or f"菜单项 '{target}' 未找到")

            if i < len(items) - 1:
                self._ensure_mk().press_key("Right")
                time.sleep(0.3)

    def select(self, items, exact=False):
        """Navigate to target and press Enter."""
        self.navigate_to(items, exact)
        self._ensure_mk().press_key("Return")
        time.sleep(0.3)

    def cancel(self):
        """Close current menu via Escape."""
        self._ensure_mk().press_key("Escape")
