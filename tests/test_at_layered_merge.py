# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only

"""Tests for the layered merge: persistent (last-wins states) + transient extraction."""

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

import yaml

from src.at.scanner.merger import (
    _anonymous_path_key,
    _merge_persistent_state,
    extract_transient,
    merge_persistent,
    write_at_tree_yaml,
)
from src.at.scanner.merger import load_record_session


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_node(role, name="", states=None, children=None, index_in_parent=-1):
    node = {
        "role": role,
        "name": name,
        "object_name": "",
        "accessible_id": "",
        "states": states or [],
        "index_in_parent": index_in_parent,
        "source": "runtime",
    }
    if children is not None:
        node["children"] = children
    return node


def _make_session(segments):
    return {
        "version": "2.0",
        "app": "test-app",
        "segments": segments,
    }


# ---------------------------------------------------------------------------
# Test: last-wins states (not union)
# ---------------------------------------------------------------------------


class TestLastWinsStates:
    """States should be overwritten with the last observed value, not unioned."""

    def test_checkbox_state_overwritten(self):
        base = [_make_node("check box", "cb1", states=["checked", "visible"])]
        state = [_make_node("check box", "cb1", states=["unchecked", "visible"])]
        _merge_persistent_state(base, state, "snap2")
        assert base[0]["states"] == ["unchecked", "visible"]

    def test_multiple_snapshots_last_wins(self):
        base = [_make_node("check box", "cb1", states=["checked"])]
        snap2 = [_make_node("check box", "cb1", states=["unchecked"])]
        snap3 = [_make_node("check box", "cb1", states=["checked", "focused"])]
        _merge_persistent_state(base, snap2, "snap2")
        _merge_persistent_state(base, snap3, "snap3")
        assert base[0]["states"] == ["checked", "focused"]

    def test_states_not_unioned(self):
        base = [_make_node("push button", "btn", states=["visible"])]
        state = [_make_node("push button", "btn", states=["focused", "visible"])]
        _merge_persistent_state(base, state, "snap2")
        # Should be exactly ["focused", "visible"], not union with extra
        assert set(base[0]["states"]) == {"focused", "visible"}
        assert len(base[0]["states"]) == 2


# ---------------------------------------------------------------------------
# Test: anonymous node dedup by parent-chain path
# ---------------------------------------------------------------------------


class TestAnonymousDedup:
    """Anonymous nodes should be deduplicated by their parent-chain path."""

    def test_anonymous_path_key_basic(self):
        node = {"role": "panel", "index_in_parent": 0}
        assert _anonymous_path_key(node, "") == "/panel:0"
        assert _anonymous_path_key(node, "/frame:0") == "/frame:0/panel:0"

    def test_anonymous_nodes_same_path_merged(self):
        base = [
            _make_node(
                "frame",
                "",
                index_in_parent=0,
                children=[_make_node("panel", "", index_in_parent=0)],
            )
        ]
        state = [
            _make_node(
                "frame",
                "",
                index_in_parent=0,
                children=[_make_node("panel", "", index_in_parent=0, states=["visible"])],
            )
        ]
        _merge_persistent_state(base, state, "snap2")
        # Should have merged, not added a duplicate
        assert len(base) == 1
        assert len(base[0]["children"]) == 1
        assert base[0]["children"][0]["states"] == ["visible"]

    def test_anonymous_nodes_different_path_not_merged(self):
        base = [
            _make_node(
                "frame",
                "",
                index_in_parent=0,
                children=[_make_node("panel", "", index_in_parent=0)],
            )
        ]
        state = [
            _make_node(
                "frame",
                "",
                index_in_parent=0,
                children=[_make_node("panel", "", index_in_parent=1)],
            )
        ]
        _merge_persistent_state(base, state, "snap2")
        # Different index_in_parent → different node
        assert len(base[0]["children"]) == 2


# ---------------------------------------------------------------------------
# Test: transient extraction
# ---------------------------------------------------------------------------


class TestExtractTransient:
    """Transient contexts should be extracted from record_session events."""

    def test_menu_open_extracted(self):
        session = _make_session(
            [
                {
                    "label": "主界面",
                    "trigger": {"type": "launch", "command": "test-app"},
                    "events": [
                        {
                            "type": "menu_open",
                            "at_tree": "states/01_menu_open.yaml",
                            "menu_items": [
                                {"name": "复制", "role": "menu item"},
                                {"name": "粘贴", "role": "menu item"},
                            ],
                        },
                    ],
                    "states": ["states/00_launch.yaml"],
                },
            ]
        )
        contexts = extract_transient(session)
        assert len(contexts) == 1
        assert contexts[0]["id"] == "right_click_menu_000"
        assert contexts[0]["trigger"]["type"] == "launch"
        assert len(contexts[0]["items"]) == 2
        assert contexts[0]["at_tree"] == "states/01_menu_open.yaml"

    def test_window_create_extracted(self):
        session = _make_session(
            [
                {
                    "label": "设置",
                    "trigger": {"type": "window_activate", "app": "test-app"},
                    "events": [
                        {
                            "type": "window_create",
                            "app": "test-child",
                            "element": {"name": "子窗口", "role": "frame"},
                            "at_tree": "states/02_window.yaml",
                        },
                    ],
                    "states": [],
                },
            ]
        )
        contexts = extract_transient(session)
        assert len(contexts) == 1
        assert contexts[0]["id"] == "child_window_000"
        assert contexts[0]["trigger"]["type"] == "window_create"
        assert contexts[0]["trigger"]["app"] == "test-child"
        assert contexts[0]["at_tree"] == "states/02_window.yaml"

    def test_multiple_contexts_numbered(self):
        session = _make_session(
            [
                {
                    "label": "seg1",
                    "trigger": {"type": "launch"},
                    "events": [
                        {"type": "menu_open", "at_tree": "s/0.yaml", "menu_items": []},
                        {"type": "menu_open", "at_tree": "s/1.yaml", "menu_items": []},
                        {
                            "type": "window_create",
                            "at_tree": "s/2.yaml",
                            "app": "child",
                            "element": {},
                        },
                    ],
                    "states": [],
                },
            ]
        )
        contexts = extract_transient(session)
        assert len(contexts) == 3
        assert contexts[0]["id"] == "right_click_menu_000"
        assert contexts[1]["id"] == "right_click_menu_001"
        assert contexts[2]["id"] == "child_window_000"

    def test_no_transient_events(self):
        session = _make_session(
            [
                {
                    "label": "seg1",
                    "trigger": {"type": "launch"},
                    "events": [
                        {"type": "click", "element": {}},
                        {"type": "focus", "element": {}},
                    ],
                    "states": [],
                },
            ]
        )
        contexts = extract_transient(session)
        assert len(contexts) == 0


# ---------------------------------------------------------------------------
# Test: write_at_tree_yaml v2 format
# ---------------------------------------------------------------------------


class TestWriteAtTreeYamlV2:
    """at-tree.yaml should include transient_contexts when provided."""

    def test_v2_has_transient_contexts(self, tmp_path):
        tree = [_make_node("frame", "main", states=["visible"])]
        transient = [
            {
                "id": "right_click_menu_000",
                "trigger": {"type": "right_click"},
                "items": [{"name": "复制", "role": "menu item"}],
                "at_tree": "states/01.yaml",
            },
        ]
        out = tmp_path / "at-tree.yaml"
        write_at_tree_yaml(tree, str(out), app_name="test", transient_contexts=transient)

        with open(out) as f:
            data = yaml.safe_load(f)
        assert data["version"] == "2.0"
        assert "transient_contexts" in data
        assert len(data["transient_contexts"]) == 1
        assert data["transient_contexts"][0]["id"] == "right_click_menu_000"
        # tree field still present (backward compatible)
        assert "tree" in data
        assert len(data["tree"]) >= 1

    def test_v1_when_no_transient(self, tmp_path):
        tree = [_make_node("frame", "main")]
        out = tmp_path / "at-tree.yaml"
        write_at_tree_yaml(tree, str(out), app_name="test")

        with open(out) as f:
            data = yaml.safe_load(f)
        assert data["version"] == "1.0"
        assert "transient_contexts" not in data
        assert "tree" in data


# ---------------------------------------------------------------------------
# Test: merge_persistent (full function with session data)
# ---------------------------------------------------------------------------


class TestMergePersistent:
    """merge_persistent should only merge launch + window_activate snapshots."""

    def test_skips_transient_snapshots(self, tmp_path):
        # Create state files
        states_dir = tmp_path / "states"
        states_dir.mkdir()

        launch_tree = [_make_node("frame", "main", states=["visible"])]
        write_runtime_dump_helper(states_dir / "00_launch.yaml", launch_tree, "launch")

        menu_tree = [
            _make_node("menu", "", states=["visible"], children=[_make_node("menu item", "复制")])
        ]
        write_runtime_dump_helper(states_dir / "01_menu.yaml", menu_tree, "menu_open")

        window_tree = [_make_node("frame", "settings", states=["visible", "active"])]
        write_runtime_dump_helper(states_dir / "02_window.yaml", window_tree, "window_activate")

        session = _make_session(
            [
                {
                    "label": "主界面",
                    "trigger": {"type": "launch", "command": "test"},
                    "events": [{"type": "launch", "at_tree": "states/00_launch.yaml"}],
                    "states": ["states/00_launch.yaml"],
                },
                {
                    "label": "右键菜单",
                    "trigger": {"type": "right_click", "element": {}},
                    "events": [
                        {"type": "menu_open", "at_tree": "states/01_menu.yaml", "menu_items": []}
                    ],
                    "states": ["states/01_menu.yaml"],
                },
                {
                    "label": "设置窗口",
                    "trigger": {"type": "window_activate", "app": "test"},
                    "events": [],
                    "states": ["states/02_window.yaml"],
                },
            ]
        )

        base_tree = [_make_node("frame", "main", states=["visible"])]
        result = merge_persistent(base_tree, session, tmp_path)

        # Should have 2 root nodes: original "main" + "settings" from window_activate
        # The menu snapshot should NOT be merged (it's transient)
        all_names = {n.get("name", "") for n in result}
        assert "main" in all_names
        assert "settings" in all_names
        # The menu node should not be in the persistent tree
        assert "" not in all_names or len(result) == 2


def write_runtime_dump_helper(path, tree, label):
    """Write a state snapshot file."""
    from src.at.scanner.merger import write_runtime_dump

    write_runtime_dump(tree, str(path), app_name="test", state_label=label)


# ---------------------------------------------------------------------------
# Test: load_record_session
# ---------------------------------------------------------------------------


class TestLoadRecordSession:
    def test_loads_valid_session(self, tmp_path):
        session_data = {
            "version": "2.0",
            "app": "test-app",
            "segments": [],
        }
        session_path = tmp_path / "record_session.yaml"
        with open(session_path, "w") as f:
            yaml.dump(session_data, f)

        result = load_record_session(tmp_path)
        assert result is not None
        assert result["app"] == "test-app"

    def test_returns_none_when_missing(self, tmp_path):
        result = load_record_session(tmp_path)
        assert result is None
