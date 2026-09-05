# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only
"""Tests for accessible-id (Qt objectName path) engine support.

Qt6 bridge encodes QObject::objectName into QAccessibleBridgeUtils::
accessibleId() dotted paths (e.g. "EditorApplication.DropdownMenu.UnixAction").
The engine must locate elements by that id, including objectName-suffix match.

tests/__init__.py replaces src.dogtail_utils with a MagicMock, so this module
loads the real file via importlib under an independent module name.
"""
import importlib.util
import sys
import types
from pathlib import Path
import unittest.mock

_src_root = Path(__file__).resolve().parent.parent / "src"


def _fix_src():
    if str(_src_root) not in sys.path:
        sys.path.insert(0, str(_src_root))
    # tests/__init__.py 把 sys.modules["src"] 换成了 MagicMock（无 __spec__
    # 且任意属性都 truthy），必须无条件替换回真实包。
    mod = types.ModuleType("src")
    mod.__path__ = [str(_src_root)]
    mod.__package__ = "src"
    mod.__file__ = str(_src_root / "__init__.py")
    mod.logger = unittest.mock.MagicMock()
    sys.modules["src"] = mod


_fix_src()


def _load_real_dogtail_utils():
    """Load the real src/dogtail_utils.py with its dogtail dependency stubbed."""
    # Stub the dogtail tree dependency (real module requires live AT-SPI).
    tree_mock = unittest.mock.MagicMock()
    tree_mock.SearchError = RuntimeError
    tree_mock.root = unittest.mock.MagicMock()
    tree_mock.predicate = unittest.mock.MagicMock()
    tree_mock.config = unittest.mock.MagicMock()
    tree_mock.Node = unittest.mock.MagicMock()
    sys.modules["src.depends.dogtail.tree"] = tree_mock

    # tests/__init__.py mocks src.mouse_key as MagicMock. If DogtailUtils
    # inherits from a MagicMock, the whole class becomes a Mock. Provide a
    # real base class instead.
    mouse_key_mod = types.ModuleType("src.mouse_key")

    class MouseKey:
        def __init__(self, *args, **kwargs):
            pass

        def press_key(self, key):
            pass

        def hot_key(self, *keys):
            pass

        def input_message(self, text):
            pass

        def click(self, x, y):
            pass

        def right_click(self, x, y):
            pass

        def double_click(self, x, y):
            pass

        def middle_click(self, x, y):
            pass

        def move_to(self, x, y):
            pass

        def mouse_scroll(self, value):
            pass

        def drag_to(self, x, y):
            pass

    mouse_key_mod.MouseKey = MouseKey
    sys.modules["src.mouse_key"] = mouse_key_mod

    spec = importlib.util.spec_from_file_location(
        "dogtail_utils_real", str(_src_root / "dogtail_utils.py")
    )
    assert spec is not None, "cannot locate src/dogtail_utils.py"
    mod = importlib.util.module_from_spec(spec)
    sys.modules["dogtail_utils_real"] = mod
    spec.loader.exec_module(mod)
    return mod
dogtail_utils = _load_real_dogtail_utils()

if "pyatspi" not in sys.modules:
    sys.modules["pyatspi"] = unittest.mock.MagicMock()

from src.at.scanner.atspi_dumper import _extract_node, _get_node_attrs  # noqa: E402

def _make_node(get_accessible_id_return: str = "", attrs: str = "") -> unittest.mock.MagicMock:
    obj = unittest.mock.MagicMock()
    obj.get_role_name.return_value = "menu item"
    obj.get_name.return_value = "Unix"
    obj.get_attributes.return_value = attrs
    obj.get_accessible_id.return_value = get_accessible_id_return
    obj.get_child_count.return_value = 0
    return obj


class TestGetNodeAttrsDict:
    """pyatspi 2.x returns a dict from get_attributes()."""

    def test_dict_attrs_parsed(self):
        obj = unittest.mock.MagicMock()
        obj.get_attributes.return_value = {"object-name": "btnSave", "accessible-id": "save_btn"}
        object_name, accessible_id = _get_node_attrs(obj)
        assert object_name == "btnSave"
        assert accessible_id == "save_btn"

    def test_empty_dict(self):
        obj = unittest.mock.MagicMock()
        obj.get_attributes.return_value = {}
        object_name, accessible_id = _get_node_attrs(obj)
        assert object_name == ""
        assert accessible_id == ""


class TestExtractNodeAccessibleIdChannel:
    def test_falls_back_to_get_accessible_id(self):
        obj = _make_node(get_accessible_id_return="EditorApplication.DropdownMenu.UnixAction")
        stats = {"total": 0, "skipped": 0, "errors": 0}
        result = _extract_node(obj, depth=0, stats=stats)
        assert result["accessible_id"] == "EditorApplication.DropdownMenu.UnixAction"

    def test_empty_get_accessible_id(self):
        obj = _make_node(get_accessible_id_return="")
        stats = {"total": 0, "skipped": 0, "errors": 0}
        result = _extract_node(obj, depth=0, stats=stats)
        assert result["accessible_id"] == ""


class TestNodeMatchesAccessibleId:
    def test_full_path_match(self):
        node = _make_node("EditorApplication.DropdownMenu.UnixAction")
        assert dogtail_utils._node_matches_accessible_id(
            node, "EditorApplication.DropdownMenu.UnixAction"
        )

    def test_suffix_match_object_name(self):
        node = _make_node("EditorApplication.DropdownMenu.UnixAction")
        assert dogtail_utils._node_matches_accessible_id(node, "UnixAction")

    def test_no_match(self):
        node = _make_node("EditorApplication.DropdownMenu.UnixAction")
        assert not dogtail_utils._node_matches_accessible_id(node, "WindowsAction")

    def test_empty_id_no_match(self):
        node = _make_node("")
        assert not dogtail_utils._node_matches_accessible_id(node, "UnixAction")

    def test_id_none_no_match(self):
        node = unittest.mock.MagicMock()
        node.get_accessible_id.return_value = None
        assert not dogtail_utils._node_matches_accessible_id(node, "UnixAction")

    def test_exception_no_match(self):
        node = unittest.mock.MagicMock()
        node.get_accessible_id.side_effect = RuntimeError("AT-SPI error")
        assert not dogtail_utils._node_matches_accessible_id(node, "UnixAction")


class TestFindElementsByAccessibleId:
    def test_method_uses_get_accessible_id_not_attrs(self):
        """find_elements_by_accessible_id must read get_accessible_id(), not
        get_attributes() (which returns {} for Qt6 nodes)."""
        real = dogtail_utils.DogtailUtils.__dict__["find_elements_by_accessible_id"]
        fake_self = unittest.mock.MagicMock()
        fake_self.obj.findChildren.return_value = ["node1"]

        real(fake_self, "UnixAction")
        match_fn = fake_self.obj.findChildren.call_args.args[0]

        node_hit = _make_node("EditorApplication.DropdownMenu.UnixAction")
        node_miss = _make_node("EditorApplication.DropdownMenu.WindowsAction")
        assert match_fn(node_hit) is True
        assert match_fn(node_miss) is False

    def test_empty_target_returns_empty(self):
        real = dogtail_utils.DogtailUtils.__dict__["find_elements_by_accessible_id"]
        fake_self = unittest.mock.MagicMock()
        result = real(fake_self, "")
        assert result == []
        fake_self.obj.findChildren.assert_not_called()


class TestEvalxAccessibleId:
    def _call_evalx(self, expr, children):
        # Python name-mangles __evalx → _DogtailUtils__evalx in the class dict.
        real = dogtail_utils.DogtailUtils.__dict__["_DogtailUtils__evalx"]
        fake_self = unittest.mock.MagicMock()
        fake_self.obj.findChildren.return_value = children
        # __evalx is a @staticmethod: (expr, element, recursive)
        _, elements = real(expr + "/", fake_self.obj, True)
        return elements
    def test_pure_accessible_id_expr(self):
        child_hit = _make_node("EditorApplication.DropdownMenu.UnixAction")
        child_miss = _make_node("EditorApplication.DropdownMenu.WindowsAction")
        elements = self._call_evalx("[accessible-id='UnixAction']", [child_hit, child_miss])
        assert len(elements) == 1
        assert elements[0] is child_hit

    def test_name_with_accessible_id_expr(self):
        child_hit = _make_node("EditorApplication.DropdownMenu.UnixAction")
        elements = self._call_evalx("Unix[@accessible-id='UnixAction']", [child_hit])
        assert len(elements) == 1

    def test_full_path_accessible_id_expr(self):
        child_hit = _make_node("EditorApplication.DropdownMenu.UnixAction")
        elements = self._call_evalx(
            "[accessible-id='EditorApplication.DropdownMenu.UnixAction']", [child_hit]
        )
        assert len(elements) == 1

    def test_no_match_returns_empty(self):
        child_miss = _make_node("EditorApplication.DropdownMenu.WindowsAction")
        elements = self._call_evalx("[accessible-id='UnixAction']", [child_miss])
        assert elements == []
