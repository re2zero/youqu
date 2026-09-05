# SPDX-FileCopyrightText: 2026 UnionTech Software Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

_src_root = Path(__file__).resolve().parent.parent / "src"
if str(_src_root) not in sys.path:
    sys.path.insert(0, str(_src_root))
stub = sys.modules.get("src")
if stub is not None and getattr(stub, "__spec__", None) is None:
    sys.modules["src"] = types.ModuleType("src")
    sys.modules["src"].__path__ = [str(_src_root)]
    sys.modules["src"].__package__ = "src"
    sys.modules["src"].__file__ = str(_src_root / "__init__.py")

if "pyatspi" not in sys.modules:
    sys.modules["pyatspi"] = MagicMock()

import pytest


def _make_accessible(
    role_name: str = "panel",
    name: str = "test",
    attrs: str = "",
    accessible_id: str = "",
    children: list | None = None,
) -> MagicMock:
    """Build a mock pyatspi.Accessible with the given properties."""
    obj = MagicMock()
    obj.get_role_name.return_value = role_name
    obj.get_name.return_value = name
    obj.get_attributes.return_value = attrs
    if accessible_id:
        obj.get_accessible_id.return_value = accessible_id
    else:
        obj.get_accessible_id.return_value = ""
    obj.get_child_count.return_value = len(children) if children else 0
    if children:
        obj.get_child_at_index.side_effect = lambda i: children[i]
    else:
        obj.get_child_at_index.return_value = None
    return obj


class TestGetNodeAttrs:

    def test_extracts_object_name_and_accessible_id(self):
        from src.at.scanner.atspi_dumper import _get_node_attrs

        obj = _make_accessible(attrs="object-name:btnSave;accessible-id:save_btn")
        object_name, accessible_id = _get_node_attrs(obj)
        assert object_name == "btnSave"
        assert accessible_id == "save_btn"

    def test_empty_attrs_returns_empty_strings(self):
        from src.at.scanner.atspi_dumper import _get_node_attrs

        obj = _make_accessible(attrs="")
        object_name, accessible_id = _get_node_attrs(obj)
        assert object_name == ""
        assert accessible_id == ""

    def test_no_attrs_returns_empty_strings(self):
        from src.at.scanner.atspi_dumper import _get_node_attrs

        obj = _make_accessible(attrs=None)
        obj.get_attributes.return_value = None
        object_name, accessible_id = _get_node_attrs(obj)
        assert object_name == ""
        assert accessible_id == ""

    def test_exception_returns_empty_strings(self):
        from src.at.scanner.atspi_dumper import _get_node_attrs

        obj = _make_accessible()
        obj.get_attributes.side_effect = RuntimeError("AT-SPI error")
        object_name, accessible_id = _get_node_attrs(obj)
        assert object_name == ""
        assert accessible_id == ""

    def test_partial_attrs(self):
        from src.at.scanner.atspi_dumper import _get_node_attrs

        obj = _make_accessible(attrs="object-name:mainWindow")
        object_name, accessible_id = _get_node_attrs(obj)
        assert object_name == "mainWindow"
        assert accessible_id == ""


class TestExtractNode:

    def test_basic_node_structure(self):
        from src.at.scanner.atspi_dumper import _extract_node

        obj = _make_accessible(role_name="push button", name="Save")
        stats = {"total": 0, "skipped": 0, "errors": 0}
        result = _extract_node(obj, depth=0, stats=stats)

        assert result["role"] == "push button"
        assert result["name"] == "Save"
        assert result["object_name"] == ""
        assert result["accessible_id"] == ""
        assert result["source"] == "runtime"
        assert "children" not in result

    def test_node_with_children(self):
        from src.at.scanner.atspi_dumper import _extract_node

        child = _make_accessible(role_name="label", name="File")
        parent = _make_accessible(role_name="panel", name="toolbar", children=[child])
        stats = {"total": 0, "skipped": 0, "errors": 0}
        result = _extract_node(parent, depth=0, stats=stats)

        assert len(result["children"]) == 1
        assert result["children"][0]["role"] == "label"
        assert stats["total"] == 2

    def test_skips_unknown_roles(self):
        from src.at.scanner.atspi_dumper import _extract_node

        unknown_child = _make_accessible(role_name="unknown", name="ghost")
        good_child = _make_accessible(role_name="label", name="visible")
        parent = _make_accessible(
            role_name="panel", name="root", children=[unknown_child, good_child]
        )
        stats = {"total": 0, "skipped": 0, "errors": 0}
        result = _extract_node(parent, depth=0, stats=stats)

        assert len(result["children"]) == 1
        assert result["children"][0]["name"] == "visible"
        assert stats["skipped"] == 1

    def test_skips_invalid_roles(self):
        from src.at.scanner.atspi_dumper import _extract_node

        invalid_child = _make_accessible(role_name="invalid", name="broken")
        parent = _make_accessible(role_name="panel", name="root", children=[invalid_child])
        stats = {"total": 0, "skipped": 0, "errors": 0}
        result = _extract_node(parent, depth=0, stats=stats)

        assert result.get("children") in (None, [])
        assert stats["skipped"] == 1

    def test_truncates_long_names(self):
        from src.at.scanner.atspi_dumper import _extract_node

        long_name = "a" * 200
        obj = _make_accessible(role_name="label", name=long_name)
        stats = {"total": 0, "skipped": 0, "errors": 0}
        result = _extract_node(obj, depth=0, stats=stats)

        assert len(result["name"]) == 100

    def test_respects_max_depth(self):
        from src.at.scanner.atspi_dumper import _MAX_DEPTH, _extract_node

        obj = _make_accessible(role_name="frame", name="root", children=[])
        stats = {"total": 0, "skipped": 0, "errors": 0}
        result = _extract_node(obj, depth=_MAX_DEPTH, stats=stats)

        assert "children" not in result
        assert stats["total"] == 1

    def test_handles_get_role_name_exception(self):
        from src.at.scanner.atspi_dumper import _extract_node

        obj = MagicMock()
        obj.get_role_name.side_effect = RuntimeError("crash")
        stats = {"total": 0, "skipped": 0, "errors": 0}
        result = _extract_node(obj, depth=0, stats=stats)

        assert result["role"] == "unknown"
        assert stats["errors"] == 1

    def test_handles_none_child(self):
        from src.at.scanner.atspi_dumper import _extract_node

        obj = _make_accessible(role_name="panel", name="root", children=[])
        obj.get_child_at_index.return_value = None
        obj.get_child_count.return_value = 3
        stats = {"total": 0, "skipped": 0, "errors": 0}
        result = _extract_node(obj, depth=0, stats=stats)

        assert "children" not in result

    def test_node_with_attrs(self):
        from src.at.scanner.atspi_dumper import _extract_node

        obj = _make_accessible(
            role_name="push button",
            name="OK",
            attrs="object-name:okBtn;accessible-id:ok_btn",
        )
        stats = {"total": 0, "skipped": 0, "errors": 0}
        result = _extract_node(obj, depth=0, stats=stats)

        assert result["object_name"] == "okBtn"
        assert result["accessible_id"] == "ok_btn"


class TestDumpAtSpiTree:

    def test_app_not_found_returns_empty_list(self, monkeypatch):
        import src.at.scanner.atspi_dumper as dumper_mod

        mock_desktop = MagicMock()
        mock_desktop.get_child_count.return_value = 0

        mock_registry = MagicMock()
        mock_registry.getDesktop.return_value = mock_desktop

        monkeypatch.setattr(dumper_mod.pyatspi, "Registry", mock_registry)

        result = dumper_mod.dump_at_spi_tree("nonexistent-app")
        assert result == []

    def test_finds_app_and_dumps_windows(self, monkeypatch):
        import src.at.scanner.atspi_dumper as dumper_mod

        window = _make_accessible(role_name="frame", name="main window")
        app = _make_accessible(role_name="application", name="test-app", children=[window])

        mock_desktop = MagicMock()
        mock_desktop.get_child_count.return_value = 2
        mock_desktop.get_child_at_index.side_effect = lambda i: [app, MagicMock()][i]

        mock_registry = MagicMock()
        mock_registry.getDesktop.return_value = mock_desktop

        monkeypatch.setattr(dumper_mod.pyatspi, "Registry", mock_registry)

        result = dumper_mod.dump_at_spi_tree("test-app")
        assert len(result) == 1
        assert result[0]["role"] == "frame"
        assert result[0]["name"] == "main window"

    def test_skips_other_apps(self, monkeypatch):
        import src.at.scanner.atspi_dumper as dumper_mod

        other_app = _make_accessible(role_name="application", name="other-app")
        window = _make_accessible(role_name="frame", name="main window")
        target_app = _make_accessible(
            role_name="application", name="target-app", children=[window]
        )

        mock_desktop = MagicMock()
        mock_desktop.get_child_count.return_value = 2
        mock_desktop.get_child_at_index.side_effect = lambda i: [other_app, target_app][i]

        mock_registry = MagicMock()
        mock_registry.getDesktop.return_value = mock_desktop

        monkeypatch.setattr(dumper_mod.pyatspi, "Registry", mock_registry)

        result = dumper_mod.dump_at_spi_tree("target-app")
        assert len(result) == 1

    def test_skips_unknown_window_roles(self, monkeypatch):
        import src.at.scanner.atspi_dumper as dumper_mod

        unknown_win = _make_accessible(role_name="unknown", name="")
        valid_win = _make_accessible(role_name="frame", name="main")
        app = _make_accessible(
            role_name="application", name="test-app", children=[unknown_win, valid_win]
        )

        mock_desktop = MagicMock()
        mock_desktop.get_child_count.return_value = 1
        mock_desktop.get_child_at_index.return_value = app

        mock_registry = MagicMock()
        mock_registry.getDesktop.return_value = mock_desktop

        monkeypatch.setattr(dumper_mod.pyatspi, "Registry", mock_registry)

        result = dumper_mod.dump_at_spi_tree("test-app")
        assert len(result) == 1
        assert result[0]["role"] == "frame"
