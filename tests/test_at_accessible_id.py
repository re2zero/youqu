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
    def _make_gi_node(self, accessible_id, children=()):
        node = unittest.mock.MagicMock()
        node.get_accessible_id.return_value = accessible_id
        node.get_child_count.return_value = len(children)
        node.get_child_at_index.side_effect = lambda i: children[i]
        return node

    def test_matches_exact_and_suffix_via_gi_walk(self):
        """find_elements_by_accessible_id must walk the gi AT-SPI tree
        (findChildren is broken for gi Accessible) and match get_accessible_id()
        exact or dotted-suffix."""
        real = dogtail_utils.DogtailUtils.__dict__["find_elements_by_accessible_id"]
        hit = self._make_gi_node("EditorApplication.DropdownMenu.UnixAction")
        miss = self._make_gi_node("EditorApplication.DropdownMenu.WindowsAction")
        root = self._make_gi_node("EditorApplication", children=(hit, miss))
        fake_self = unittest.mock.MagicMock()
        fake_self.obj = root

        results = real(fake_self, "UnixAction")
        assert results == [hit]

    def test_no_get_accessible_id_node_skipped(self):
        real = dogtail_utils.DogtailUtils.__dict__["find_elements_by_accessible_id"]
        bad = unittest.mock.MagicMock()
        bad.get_accessible_id.side_effect = RuntimeError("no id")
        bad.get_child_count.return_value = 0
        root = self._make_gi_node("EditorApplication", children=(bad,))
        fake_self = unittest.mock.MagicMock()
        fake_self.obj = root
        assert real(fake_self, "Anything") == []


class TestEvalxAccessibleId:
    def _make_gi_node(self, accessible_id, name="", role="", children=()):
        node = unittest.mock.MagicMock()
        node.get_accessible_id.return_value = accessible_id
        node.get_name.return_value = name
        node.get_role_name.return_value = role
        node.get_child_count.return_value = len(children)
        node.get_child_at_index.side_effect = lambda i: children[i]
        return node

    def _call_evalx(self, expr, children):
        real = dogtail_utils.DogtailUtils.__dict__["_DogtailUtils__evalx"]
        fake_self = unittest.mock.MagicMock()
        root = self._make_gi_node("EditorApplication", children=children)
        _, elements = real(expr + "/", root, True)
        return elements

    def test_pure_accessible_id_expr(self):
        child_hit = self._make_gi_node("EditorApplication.DropdownMenu.UnixAction")
        child_miss = self._make_gi_node("EditorApplication.DropdownMenu.WindowsAction")
        elements = self._call_evalx("[accessible-id='UnixAction']", [child_hit, child_miss])
        assert len(elements) == 1
        assert elements[0] is child_hit

    def test_name_with_accessible_id_expr(self):
        child_hit = self._make_gi_node(
            "EditorApplication.DropdownMenu.UnixAction", name="Unix"
        )
        elements = self._call_evalx("Unix[@accessible-id='UnixAction']", [child_hit])
        assert len(elements) == 1

    def test_full_path_accessible_id_expr(self):
        child_hit = self._make_gi_node("EditorApplication.DropdownMenu.UnixAction")
        elements = self._call_evalx(
            "[accessible-id='EditorApplication.DropdownMenu.UnixAction']", [child_hit]
        )
        assert len(elements) == 1

    def test_no_match_returns_empty(self):
        child_miss = self._make_gi_node("EditorApplication.DropdownMenu.WindowsAction")
        elements = self._call_evalx("[accessible-id='UnixAction']", [child_miss])
        assert elements == []


class TestActiveFrameFilter:
    """活动窗口过滤 (AT-SPI ACTIVE frame 判定 + 宽松回退)。

    修复: 打开设置对话框等子窗口后, 其内元素不能被误判为"不在活动窗口"
    而全部丢弃。有 ACTIVE frame 时只返回该 frame 内节点; 判定失败
    (无 ACTIVE frame) 时不过滤。
    """

    def _install_fake_gi(self):
        saved = {
            "gi": sys.modules.get("gi"),
            "gi.repository": sys.modules.get("gi.repository"),
            "gi.repository.Atspi": sys.modules.get("gi.repository.Atspi"),
        }
        atspi = types.ModuleType("gi.repository.Atspi")
        atspi.CoordType = type("CoordType", (), {"SCREEN": 1})
        atspi.StateType = type("StateType", (), {"ACTIVE": 0})
        repo = types.ModuleType("gi.repository")
        repo.Atspi = atspi
        gi = types.ModuleType("gi")
        gi.repository = repo
        sys.modules["gi"] = gi
        sys.modules["gi.repository"] = repo
        sys.modules["gi.repository.Atspi"] = atspi
        return saved

    def _restore_gi(self, saved):
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v

    def _gi_node(self, accessible_id="", name="", role="", extents=None, active=False, children=()):
        node = unittest.mock.MagicMock()
        node.get_accessible_id.return_value = accessible_id
        node.get_name.return_value = name
        node.get_role_name.return_value = role
        node.get_child_count.return_value = len(children)
        node.get_child_at_index.side_effect = lambda i: children[i]

        class _Ext:
            def __init__(self, x, y, w, h):
                self.x, self.y, self.width, self.height = x, y, w, h

        if extents is not None:
            node.get_extents.return_value = _Ext(*extents)
        state = unittest.mock.MagicMock()
        state.contains.return_value = active
        node.get_state_set.return_value = state
        return node

    def _find_by_name(self, root, name):
        return dogtail_utils._gi_find_descendants(root, name=name)

    def test_active_frame_only(self):
        """有 ACTIVE frame: 只返回该 frame 内节点, 其它窗口元素被丢弃。"""
        saved = self._install_fake_gi()
        try:
            active_frame = self._gi_node(
                "FrameActive", role="frame", extents=(0, 0, 100, 100), active=True,
                children=(self._gi_node(name="Target", extents=(50, 50, 10, 10)),),
            )
            inactive_frame = self._gi_node(
                "FrameInactive", role="frame", extents=(200, 0, 100, 100), active=False,
                children=(self._gi_node(name="Target", extents=(250, 50, 10, 10)),),
            )
            root = self._gi_node("EditorApplication", children=(active_frame, inactive_frame))
            results = self._find_by_name(root, "Target")
            # 只保留活动 frame 内节点 (child 均在 activity_frame 下则只取其一)。
            # 这里用坐标区分: 只有 active frame 内的 (50,50) 被保留。
            assert len(results) == 1
            assert results[0].get_name() == "Target"
        finally:
            self._restore_gi(saved)

    def test_no_active_frame_no_filter(self):
        """无 ACTIVE frame (判定失败): 宽松回退, 不过滤 —— 子窗口元素不被误删。"""
        saved = self._install_fake_gi()
        try:
            frame_a = self._gi_node(
                "FrameA", role="frame", extents=(0, 0, 100, 100), active=False,
                children=(self._gi_node(name="Target", extents=(50, 50, 10, 10)),),
            )
            frame_b = self._gi_node(
                "FrameB", role="frame", extents=(200, 0, 100, 100), active=False,
                children=(self._gi_node(name="Target", extents=(250, 50, 10, 10)),),
            )
            root = self._gi_node("EditorApplication", children=(frame_a, frame_b))
            results = self._find_by_name(root, "Target")
            assert len(results) == 2
        finally:
            self._restore_gi(saved)

