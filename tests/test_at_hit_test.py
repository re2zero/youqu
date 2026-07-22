# SPDX-FileCopyrightText: 2026 UnionTechnologies Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only

"""Unit tests for src.at.scanner.hit_test.

Tests cover:
- Recursive hit-test (deepest visible element)
- Invisible element filtering
- _SKIP_ROLES filtering
- Coordinate containment check (outside bounds → None)
- Extents cache build + lookup
- Edge cases: None root, no children, exception resilience
"""

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

from src.at.scanner.event_listener import (
    DegradedListener,
    InputEvent,
    InputEventListener,
    X11RecordListener,
    WaylandEvdevListener,
    create_input_listener,
    is_modifier,
    is_printable_char,
    keysym_to_name,
)
from src.at.scanner.hit_test import (
    ExtentsCache,
    _contains,
    _extract_hit_node,
    _get_extents,
    _is_visible,
    hit_test,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _MockExtents:
    """Minimal stand-in for pyatspi.Rect."""

    def __init__(self, x: int, y: int, width: int, height: int) -> None:
        self.x = x
        self.y = y
        self.width = width
        self.height = height


class _MockStateSet:
    """Stand-in for pyatspi StateSet."""

    def __init__(self, state_ids: list[int]) -> None:
        self._states = state_ids

    def getStates(self) -> list[int]:
        return self._states


def _make_accessible(
    role_name: str = "panel",
    name: str = "test",
    states: list[str] | None = None,
    extents: tuple[int, int, int, int] | None = None,
    children: list | None = None,
    attrs: str = "",
) -> MagicMock:
    """Build a mock pyatspi.Accessible for hit-test tests.

    Parameters
    ----------
    states
        List of AT-SPI state *names* (e.g. ``["visible", "showing"]``).
        These are mapped to fake integer IDs for the StateSet mock.
    extents
        (x, y, width, height) for get_extents().
    children
        List of child MagicMock objects.
    """
    obj = MagicMock()

    obj.get_role_name.return_value = role_name
    obj.get_name.return_value = name
    obj.get_attributes.return_value = attrs

    # Map state names to integers (arbitrary unique ints)
    _STATE_NAME_TO_INT = {"visible": 1, "showing": 2, "active": 3, "focused": 4}
    if states is None:
        states = ["visible", "showing"]
    state_ids = [_STATE_NAME_TO_INT.get(s, 99) for s in states]

    # Patch the _STATE_MAP in both hit_test and atspi_dumper modules
    # so _state_names() resolves correctly
    import src.at.scanner.atspi_dumper as dumper_mod

    for sid, sname in zip(state_ids, states):
        dumper_mod._STATE_MAP[sid] = sname

    state_set = _MockStateSet(state_ids)
    obj.getState.return_value = state_set

    if extents is not None:
        obj.get_extents.return_value = _MockExtents(*extents)
    else:
        obj.get_extents.return_value = _MockExtents(0, 0, 0, 0)

    obj.get_child_count.return_value = len(children) if children else 0
    if children:
        obj.get_child_at_index.side_effect = lambda i: children[i] if i < len(children) else None
    else:
        obj.get_child_at_index.return_value = None

    obj.description = ""
    obj.getIndexInParent.return_value = 0

    return obj


# ---------------------------------------------------------------------------
# _contains
# ---------------------------------------------------------------------------

class TestContains:
    def test_point_inside(self):
        assert _contains((10, 20, 100, 50), 50, 40)

    def test_point_at_corner(self):
        assert _contains((10, 20, 100, 50), 110, 70)

    def test_point_outside(self):
        assert not _contains((10, 20, 100, 50), 200, 200)

    def test_point_at_origin(self):
        assert _contains((0, 0, 100, 100), 0, 0)

    def test_zero_size_element(self):
        assert not _contains((50, 50, 0, 0), 51, 51)


# ---------------------------------------------------------------------------
# _is_visible
# ---------------------------------------------------------------------------

class TestIsVisible:
    def test_visible_and_showing(self):
        obj = _make_accessible(states=["visible", "showing"])
        assert _is_visible(obj)

    def test_only_visible(self):
        obj = _make_accessible(states=["visible"])
        assert _is_visible(obj)

    def test_not_visible(self):
        obj = _make_accessible(states=["showing"])
        assert not _is_visible(obj)

    def test_no_states(self):
        obj = _make_accessible(states=[])
        assert not _is_visible(obj)

    def test_state_exception_returns_false(self):
        obj = MagicMock()
        obj.getState.side_effect = RuntimeError("AT-SPI error")
        assert not _is_visible(obj)


# ---------------------------------------------------------------------------
# _get_extents
# ---------------------------------------------------------------------------

class TestGetExtents:
    def test_normal_extents(self):
        obj = _make_accessible(extents=(10, 20, 100, 50))
        result = _get_extents(obj)
        assert result == (10, 20, 100, 50)

    def test_exception_returns_none(self):
        obj = MagicMock()
        obj.get_extents.side_effect = RuntimeError("crash")
        assert _get_extents(obj) is None


# ---------------------------------------------------------------------------
# _extract_hit_node
# ---------------------------------------------------------------------------

class TestExtractHitNode:
    def test_basic_extraction(self):
        obj = _make_accessible(role_name="push button", name="Save")
        result = _extract_hit_node(obj)
        assert result["role"] == "push button"
        assert result["name"] == "Save"
        assert result["source"] == "runtime"

    def test_with_object_name(self):
        obj = _make_accessible(
            role_name="push button",
            name="OK",
            attrs="object-name:okBtn;accessible-id:ok_btn",
        )
        result = _extract_hit_node(obj)
        assert result["object_name"] == "okBtn"
        assert result["accessible_id"] == "ok_btn"

    def test_exception_returns_unknown(self):
        obj = MagicMock()
        obj.get_role_name.side_effect = RuntimeError("crash")
        result = _extract_hit_node(obj)
        assert result["role"] == "unknown"
        assert result["name"] == ""


# ---------------------------------------------------------------------------
# hit_test
# ---------------------------------------------------------------------------

class TestHitTest:
    def test_none_root_returns_none(self):
        assert hit_test(10, 10, None) is None

    def test_invisible_root_returns_none(self):
        root = _make_accessible(states=["showing"], extents=(0, 0, 1000, 1000))
        assert hit_test(500, 500, root) is None

    def test_point_outside_returns_none(self):
        root = _make_accessible(extents=(0, 0, 100, 100))
        assert hit_test(500, 500, root) is None

    def test_skip_role_returns_none(self):
        root = _make_accessible(
            role_name="scroll bar",
            extents=(0, 0, 1000, 1000),
        )
        assert hit_test(500, 500, root) is None

    def test_leaf_node_returns_itself(self):
        root = _make_accessible(
            role_name="push button",
            name="Click Me",
            extents=(100, 100, 50, 30),
        )
        result = hit_test(120, 115, root)
        assert result is not None
        assert result["role"] == "push button"
        assert result["name"] == "Click Me"

    def test_recurses_to_deepest_child(self):
        # Parent at (0,0) 1000x1000, child at (100,100) 50x30
        child = _make_accessible(
            role_name="push button",
            name="Deep Button",
            extents=(100, 100, 50, 30),
        )
        root = _make_accessible(
            role_name="frame",
            name="Main",
            extents=(0, 0, 1000, 1000),
            children=[child],
        )
        result = hit_test(120, 115, root)
        assert result is not None
        assert result["name"] == "Deep Button"
        assert result["role"] == "push button"

    def test_returns_parent_when_point_in_parent_not_child(self):
        child = _make_accessible(
            role_name="push button",
            name="Deep Button",
            extents=(100, 100, 50, 30),
        )
        root = _make_accessible(
            role_name="frame",
            name="Main",
            extents=(0, 0, 1000, 1000),
            children=[child],
        )
        result = hit_test(500, 500, root)
        assert result is not None
        assert result["name"] == "Main"

    def test_skips_invisible_child(self):
        invisible_child = _make_accessible(
            role_name="push button",
            name="Hidden",
            states=["showing"],  # not visible
            extents=(100, 100, 50, 30),
        )
        visible_child = _make_accessible(
            role_name="push button",
            name="Visible",
            extents=(200, 200, 50, 30),
        )
        root = _make_accessible(
            role_name="frame",
            name="Main",
            extents=(0, 0, 1000, 1000),
            children=[invisible_child, visible_child],
        )
        result = hit_test(110, 115, root)
        # Point is inside invisible child but it's filtered → falls to root
        assert result is not None
        assert result["name"] == "Main"

    def test_skips_skip_role_child(self):
        skip_child = _make_accessible(
            role_name="separator",
            name="Sep",
            extents=(100, 100, 50, 30),
        )
        good_child = _make_accessible(
            role_name="push button",
            name="Good",
            extents=(100, 100, 50, 30),
        )
        root = _make_accessible(
            role_name="frame",
            name="Main",
            extents=(0, 0, 1000, 1000),
            children=[skip_child, good_child],
        )
        result = hit_test(110, 115, root)
        assert result is not None
        assert result["name"] == "Good"

    def test_first_matching_child_wins(self):
        child1 = _make_accessible(
            role_name="push button",
            name="First",
            extents=(100, 100, 50, 30),
        )
        child2 = _make_accessible(
            role_name="push button",
            name="Second",
            extents=(100, 100, 50, 30),
        )
        root = _make_accessible(
            role_name="frame",
            name="Main",
            extents=(0, 0, 1000, 1000),
            children=[child1, child2],
        )
        result = hit_test(110, 115, root)
        assert result["name"] == "First"

    def test_get_extents_exception_returns_none(self):
        root = MagicMock()
        root.getState.return_value = _MockStateSet([1, 2])
        root.get_extents.side_effect = RuntimeError("crash")
        result = hit_test(10, 10, root)
        assert result is None

    def test_get_child_count_exception_falls_to_leaf(self):
        root = MagicMock()
        root.getState.return_value = _MockStateSet([1, 2])
        root.get_extents.return_value = _MockExtents(0, 0, 1000, 1000)
        root.get_role_name.return_value = "frame"
        root.get_name.return_value = "Main"
        root.get_attributes.return_value = ""
        root.description = ""
        root.getIndexInParent.return_value = 0
        root.get_child_count.side_effect = RuntimeError("crash")
        result = hit_test(500, 500, root)
        assert result is not None
        assert result["role"] == "frame"

    def test_none_child_skipped(self):
        root = _make_accessible(
            role_name="frame",
            name="Main",
            extents=(0, 0, 1000, 1000),
            children=[],
        )
        root.get_child_count.return_value = 3
        root.get_child_at_index.return_value = None
        result = hit_test(500, 500, root)
        assert result is not None
        assert result["name"] == "Main"

    def test_deep_recursion_three_levels(self):
        leaf = _make_accessible(
            role_name="label",
            name="Deep Leaf",
            extents=(50, 50, 10, 10),
        )
        mid = _make_accessible(
            role_name="panel",
            name="Mid Panel",
            extents=(0, 0, 500, 500),
            children=[leaf],
        )
        root = _make_accessible(
            role_name="frame",
            name="Root",
            extents=(0, 0, 1000, 1000),
            children=[mid],
        )
        result = hit_test(55, 55, root)
        assert result is not None
        assert result["name"] == "Deep Leaf"
        assert result["role"] == "label"


# ---------------------------------------------------------------------------
# ExtentsCache
# ---------------------------------------------------------------------------

class TestExtentsCache:
    def test_empty_cache_lookup_returns_none(self):
        cache = ExtentsCache()
        assert cache.lookup(10, 10) is None
        assert len(cache) == 0

    def test_build_and_lookup(self):
        child = _make_accessible(
            role_name="push button",
            name="Button",
            extents=(100, 100, 50, 30),
        )
        root = _make_accessible(
            role_name="frame",
            name="Main",
            extents=(0, 0, 1000, 1000),
            children=[child],
        )
        cache = ExtentsCache()
        cache.build(root)
        assert len(cache) == 2  # root + child

        # Lookup a point inside the child
        result = cache.lookup(120, 115)
        assert result is not None
        assert result["name"] == "Button"

    def test_lookup_returns_smallest_element(self):
        big = _make_accessible(
            role_name="frame",
            name="Big",
            extents=(0, 0, 1000, 1000),
        )
        small = _make_accessible(
            role_name="push button",
            name="Small",
            extents=(100, 100, 20, 20),
        )
        root = _make_accessible(
            role_name="application",
            name="App",
            extents=(0, 0, 2000, 2000),
            children=[big, small],
        )
        cache = ExtentsCache()
        cache.build(root)
        result = cache.lookup(105, 105)
        assert result is not None
        assert result["name"] == "Small"

    def test_lookup_outside_all_returns_none(self):
        root = _make_accessible(
            role_name="frame",
            name="Main",
            extents=(0, 0, 100, 100),
        )
        cache = ExtentsCache()
        cache.build(root)
        assert cache.lookup(500, 500) is None

    def test_skips_invisible_during_build(self):
        visible = _make_accessible(
            role_name="push button",
            name="Visible",
            extents=(100, 100, 50, 30),
        )
        invisible = _make_accessible(
            role_name="push button",
            name="Invisible",
            states=["showing"],
            extents=(200, 200, 50, 30),
        )
        root = _make_accessible(
            role_name="frame",
            name="Main",
            extents=(0, 0, 1000, 1000),
            children=[visible, invisible],
        )
        cache = ExtentsCache()
        cache.build(root)
        assert len(cache) == 2  # root + visible only

    def test_skips_skip_roles_during_build(self):
        skip_child = _make_accessible(
            role_name="separator",
            name="Sep",
            extents=(100, 100, 50, 30),
        )
        good_child = _make_accessible(
            role_name="push button",
            name="Good",
            extents=(200, 200, 50, 30),
        )
        root = _make_accessible(
            role_name="frame",
            name="Main",
            extents=(0, 0, 1000, 1000),
            children=[skip_child, good_child],
        )
        cache = ExtentsCache()
        cache.build(root)
        assert len(cache) == 2  # root + good only

    def test_zero_area_element_skipped(self):
        zero_area = _make_accessible(
            role_name="label",
            name="Zero",
            extents=(50, 50, 0, 0),
        )
        root = _make_accessible(
            role_name="frame",
            name="Main",
            extents=(0, 0, 1000, 1000),
            children=[zero_area],
        )
        cache = ExtentsCache()
        cache.build(root)
        assert len(cache) == 1  # root only

    def test_rebuild_clears_old_entries(self):
        child1 = _make_accessible(
            role_name="push button",
            name="A",
            extents=(0, 0, 10, 10),
        )
        root1 = _make_accessible(
            role_name="frame",
            name="Main1",
            extents=(0, 0, 1000, 1000),
            children=[child1],
        )
        cache = ExtentsCache()
        cache.build(root1)
        assert len(cache) == 2

        # Rebuild with a different tree
        root2 = _make_accessible(
            role_name="frame",
            name="Main2",
            extents=(0, 0, 1000, 1000),
        )
        cache.build(root2)
        assert len(cache) == 1  # only root2

    def test_none_node_ignored(self):
        cache = ExtentsCache()
        cache._walk(None)
        assert len(cache) == 0


# ---------------------------------------------------------------------------
# keysym_to_name
# ---------------------------------------------------------------------------

class TestKeysymToName:
    def test_enter(self):
        assert keysym_to_name(0xFF0D) == "Return"

    def test_escape(self):
        assert keysym_to_name(0xFF1B) == "Escape"

    def test_space(self):
        assert keysym_to_name(0x0020) == " "

    def test_lowercase_letter(self):
        assert keysym_to_name(0x61) == "a"

    def test_uppercase_letter(self):
        assert keysym_to_name(0x41) == "A"

    def test_digit(self):
        assert keysym_to_name(0x30) == "0"

    def test_unknown_keysym(self):
        result = keysym_to_name(0x12345678)
        assert "keysym" in result

    def test_shift_keys(self):
        assert keysym_to_name(0xFFE1) == "Shift_L"
        assert keysym_to_name(0xFFE3) == "Control_L"
