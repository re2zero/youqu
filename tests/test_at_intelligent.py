# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only
"""Tests for intelligent accessible_id dispatch (src/at/executor/intelligent.py)."""
import importlib.util
import sys
import types
from pathlib import Path
import unittest.mock

import pytest

_src_root = Path(__file__).resolve().parent.parent / "src"


def _fix_src():
    if str(_src_root) not in sys.path:
        sys.path.insert(0, str(_src_root))
    mod = types.ModuleType("src")
    mod.__path__ = [str(_src_root)]
    mod.__package__ = "src"
    mod.__file__ = str(_src_root / "__init__.py")
    mod.logger = unittest.mock.MagicMock()
    sys.modules["src"] = mod


_fix_src()

if "pyatspi" not in sys.modules:
    sys.modules["pyatspi"] = unittest.mock.MagicMock()

from src.at.executor import intelligent  # noqa: E402


class TestClassifyMenuType:
    def test_dropdown(self):
        assert intelligent.classify_menu_type("EditorApplication.DropdownMenu") == "dropdown"

    def test_dropdown_submenu(self):
        assert (
            intelligent.classify_menu_type(
                "EditorApplication.DropdownMenu.QAction.QMenu"
            )
            == "dropdown"
        )

    def test_main_menu(self):
        assert intelligent.classify_menu_type("EditorApplication.Menu_2") == "main"

    def test_context_qmenu(self):
        assert intelligent.classify_menu_type("EditorApplication.QMenu") == "context"

    def test_empty(self):
        assert intelligent.classify_menu_type("") == "context"


class TestIsMenuItem:
    def test_menu_item_role(self):
        node = unittest.mock.MagicMock()
        node.roleName = "menu item"
        assert intelligent.is_menu_item(node)

    def test_push_button(self):
        node = unittest.mock.MagicMock()
        node.roleName = "push button"
        assert not intelligent.is_menu_item(node)

    def test_mock_role_not_str(self):
        node = unittest.mock.MagicMock()  # roleName is a MagicMock
        assert not intelligent.is_menu_item(node)

    def test_exception(self):
        node = unittest.mock.MagicMock()
        node.roleName.side_effect = RuntimeError
        assert not intelligent.is_menu_item(node)


class TestDispatch:
    def test_normal_widget_returns_false(self):
        """Normal widgets: dispatch returns False so the caller clicks."""
        node = unittest.mock.MagicMock()
        node.roleName = "push button"
        result = intelligent.dispatch(None, {"accessible_id": "btn"}, "click", {}, node)
        assert result is False

    def test_menu_item_click_navigates(self):
        """Menu item click: dispatch performs auto navigation, returns True."""
        node = unittest.mock.MagicMock()
        node.roleName = "menu item"
        node.name = "Windows"
        parent = unittest.mock.MagicMock()
        parent.get_accessible_id.return_value = "EditorApplication.DropdownMenu"
        node.parent = parent

        with (
            unittest.mock.patch.object(
                intelligent, "act_on_menu_item"
            ) as mock_act,
        ):
            result = intelligent.dispatch(
                unittest.mock.MagicMock(),
                {"accessible_id": "WindowsAction"},
                "click",
                {"app": "test-app"},
                node,
            )
        assert result is True
        mock_act.assert_called_once()

    def test_menu_item_assert_not_dispatched(self):
        """Menu item + assert action: not a click, dispatch returns False."""
        node = unittest.mock.MagicMock()
        node.roleName = "menu item"
        result = intelligent.dispatch(
            None, {"accessible_id": "WindowsAction"}, "assert_element", {}, node
        )
        assert result is False


class TestActOnMenuItem:
    def test_dropdown_menu_navigation(self):
        """Dropdown menu item: find trigger button, click it, keyboard-nav."""
        node = unittest.mock.MagicMock()
        node.roleName = "menu item"
        node.name = "Windows"
        parent = unittest.mock.MagicMock()
        parent.get_accessible_id.return_value = "EditorApplication.DropdownMenu"
        node.parent = parent

        trigger = unittest.mock.MagicMock()
        trigger.get_accessible_id.return_value = "EditorApplication.BottomBar.DDropdownMenu.PToolButton"
        trigger.showing = True
        trigger.extents = (100, 100, 50, 28)  # 有效坐标 (试探式触发跳过无效)
        dog = unittest.mock.MagicMock()
        dog.find_elements_by_accessible_id.return_value = [trigger]

        nav_instance = unittest.mock.MagicMock()
        with (
            unittest.mock.patch(
                "src.at.executor.menu_nav.AtMenuNavigator",
                return_value=nav_instance,
            ),
        ):
            intelligent.act_on_menu_item(
                dog, node, "click", {"accessible_id": "WindowsAction"}, {"app": "app"}
            )
        trigger.click.assert_called_once()
        nav_instance.select.assert_called_once_with(["Windows"], exact=True)

    def test_no_display_text_raises(self):
        node = unittest.mock.MagicMock()
        node.roleName = "menu item"
        node.name = ""
        with pytest.raises(ValueError, match="no display text"):
            intelligent.act_on_menu_item(
                unittest.mock.MagicMock(), node, "click", {}, {"app": "app"}
            )

    def test_no_trigger_still_navigates(self):
        """No trigger found → warn but still keyboard-navigate."""
        node = unittest.mock.MagicMock()
        node.roleName = "menu item"
        node.name = "Windows"
        parent = unittest.mock.MagicMock()
        parent.get_accessible_id.return_value = "EditorApplication.QMenu"
        node.parent = parent

        dog = unittest.mock.MagicMock()
        dog.find_elements_by_accessible_id.return_value = []

        nav_instance = unittest.mock.MagicMock()
        with unittest.mock.patch(
            "src.at.executor.menu_nav.AtMenuNavigator",
            return_value=nav_instance,
        ):
            intelligent.act_on_menu_item(
                dog, node, "click", {"accessible_id": "X"}, {"app": "app"}
            )
        nav_instance.select.assert_called_once_with(["Windows"], exact=True)
