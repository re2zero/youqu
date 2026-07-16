# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
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

for _mod in (
    "pyatspi",
    "pyatspi.Accessibility",
    "pyatspi.application",
    "pyatspi.utils",
    "pyatspi.state",
    "pyatspi.constants",
    "pyatspi.registry",
):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

import pytest


def _make_node(
    nid: str,
    role: str = "",
    name: str = "",
    object_name: str = "",
    accessible_id: str = "",
    actions: list | None = None,
    children: list | None = None,
    class_name: str = "",
) -> dict:
    node = {
        "id": nid,
        "role": role,
        "name": name,
        "object_name": object_name,
        "accessible_id": accessible_id,
        "actions": actions or [],
        "children": children or [],
        "class_name": class_name,
    }
    return node


class TestFilterNoise:
    def test_filters_form_prefix_names(self):
        from src.at.scanner.merger import filter_noise

        tree = [
            _make_node(
                "n0",
                role="frame",
                name="main",
                children=[
                    _make_node("n1", role="panel", name="Form_mainwindow", children=[]),
                    _make_node("n2", role="push button", name="OK", actions=["click"]),
                ],
            ),
        ]
        result = filter_noise(tree)
        names = [n["name"] for n in result[0]["children"]]
        assert "Form_mainwindow" not in names
        assert "OK" in names

    def test_filters_numeric_names(self):
        from src.at.scanner.merger import filter_noise

        tree = [
            _make_node(
                "n0",
                role="list",
                name="thumbnails",
                children=[
                    _make_node("n1", role="list item", name="0", children=[]),
                    _make_node("n2", role="list item", name="1", children=[]),
                    _make_node("n3", role="list item", name="page_2", children=[]),
                ],
            ),
        ]
        result = filter_noise(tree)
        names = [n["name"] for n in result[0]["children"]]
        assert "0" not in names
        assert "1" not in names
        assert "page_2" in names

    def test_filters_qt_prefix_names(self):
        from src.at.scanner.merger import filter_noise

        tree = [
            _make_node(
                "n0",
                role="frame",
                name="main",
                children=[
                    _make_node("n1", role="label", name="qt_toolbar_break", children=[]),
                    _make_node("n2", role="push button", name="Save", actions=["click"]),
                ],
            ),
        ]
        result = filter_noise(tree)
        names = [n["name"] for n in result[0]["children"]]
        assert "qt_toolbar_break" not in names
        assert "Save" in names

    def test_filters_noise_leaf_roles_when_empty_children(self):
        from src.at.scanner.merger import filter_noise

        tree = [
            _make_node(
                "n0",
                role="frame",
                name="main",
                children=[
                    _make_node("n1", role="panel", name="empty_panel", children=[]),
                    _make_node("n2", role="scroll pane", name="empty_scroll", children=[]),
                    _make_node("n3", role="label", name="static_text", children=[]),
                ],
            ),
        ]
        result = filter_noise(tree)
        names = [n["name"] for n in result[0]["children"]]
        assert "empty_panel" not in names
        assert "empty_scroll" not in names
        assert "static_text" not in names

    def test_keeps_container_with_children(self):
        from src.at.scanner.merger import filter_noise

        tree = [
            _make_node(
                "n0",
                role="frame",
                name="main",
                children=[
                    _make_node(
                        "n1",
                        role="panel",
                        name="content_panel",
                        children=[
                            _make_node("n2", role="push button", name="OK", actions=["click"]),
                        ],
                    ),
                ],
            ),
        ]
        result = filter_noise(tree)
        assert len(result[0]["children"]) == 1
        assert result[0]["children"][0]["name"] == "content_panel"
        assert len(result[0]["children"][0]["children"]) == 1

    def test_preserves_nested_structure(self):
        from src.at.scanner.merger import filter_noise

        tree = [
            _make_node(
                "n0",
                role="window",
                name="win",
                children=[
                    _make_node(
                        "n1",
                        role="panel",
                        name="toolbar",
                        children=[
                            _make_node("n2", role="push button", name="Open", actions=["click"]),
                            _make_node("n3", role="label", name="qt_label", children=[]),
                        ],
                    ),
                ],
            ),
        ]
        result = filter_noise(tree)
        assert len(result) == 1
        assert len(result[0]["children"]) == 1
        assert result[0]["children"][0]["name"] == "toolbar"
        assert len(result[0]["children"][0]["children"]) == 1
        assert result[0]["children"][0]["children"][0]["name"] == "Open"


class TestClassifyNodes:
    def test_interactive_by_actions(self):
        from src.at.scanner.merger import classify_nodes

        tree = [_make_node("n0", role="push button", name="OK", actions=["click"])]
        classify_nodes(tree)
        assert tree[0]["classification"] == "interactive"

    def test_interactive_by_role(self):
        from src.at.scanner.merger import classify_nodes

        tree = [_make_node("n0", role="check box", name="Enable", actions=[])]
        classify_nodes(tree)
        assert tree[0]["classification"] == "interactive"

    def test_container_no_actions(self):
        from src.at.scanner.merger import classify_nodes

        tree = [
            _make_node(
                "n0",
                role="panel",
                name="container",
                actions=[],
                children=[
                    _make_node("n1", role="push button", name="OK", actions=["click"]),
                ],
            )
        ]
        classify_nodes(tree)
        assert tree[0]["classification"] == "container"
        assert tree[0]["children"][0]["classification"] == "interactive"


class TestElementGaps:
    def test_write_element_gaps_finds_missing(self, tmp_path):
        from src.at.scanner.merger import write_element_gaps

        tree = [
            _make_node("n0", role="push button", name="OK", actions=["click"]),
            _make_node(
                "n1", role="push button", name="Cancel", object_name="btn_cancel", actions=["click"]
            ),
        ]
        gaps_path = str(tmp_path / "element_gaps.yaml")
        write_element_gaps(tree, gaps_path, app_name="test_app")

        import yaml

        report = yaml.safe_load(Path(gaps_path).read_text())
        assert report["summary"]["total_interactive"] == 2
        assert report["summary"]["with_accessible_id"] == 1
        assert report["summary"]["missing_accessible_id"] == 1
        assert len(report["gaps"]) == 1
        assert report["gaps"][0]["name"] == "OK"

    def test_write_element_gaps_no_gaps(self, tmp_path):
        from src.at.scanner.merger import write_element_gaps

        tree = [
            _make_node(
                "n0", role="push button", name="OK", object_name="btn_ok", actions=["click"]
            ),
            _make_node("n1", role="check box", name="Enable", accessible_id="chk_enable"),
        ]
        gaps_path = str(tmp_path / "element_gaps.yaml")
        write_element_gaps(tree, gaps_path, app_name="test_app")

        import yaml

        report = yaml.safe_load(Path(gaps_path).read_text())
        assert report["summary"]["missing_accessible_id"] == 0
        assert len(report["gaps"]) == 0


class TestModelsNewFields:
    def test_at_tree_node_has_comment_field(self):
        from src.at.parser.models import AtTreeNode

        node = AtTreeNode(id="n1", role="push button", name="OK")
        assert node.comment == ""
        assert node.annotation_status == "draft"
        assert node.classification == ""

    def test_at_tree_node_with_comment(self):
        from src.at.parser.models import AtTreeNode

        node = AtTreeNode(
            id="n1",
            role="push button",
            name="OK",
            comment="GUI位置: 工具栏 | 功能: 确认操作",
            annotation_status="reviewed",
            classification="interactive",
        )
        assert node.comment == "GUI位置: 工具栏 | 功能: 确认操作"
        assert node.annotation_status == "reviewed"
        assert node.classification == "interactive"


class TestTreeInfoYaml:
    def test_simplify_tree_keeps_essential_fields(self):
        from src.at.generator.case_parser import _simplify_tree

        nodes = [
            {
                "id": "n0",
                "role": "push button",
                "name": "OK",
                "object_name": "btn_ok",
                "accessible_id": "ok_button",
                "classification": "interactive",
                "comment": "GUI位置: 工具栏 | 功能: 确认",
                "annotation_status": "reviewed",
                "description": "extra desc",
                "states": ["visible"],
                "actions": ["click"],
                "children": [],
            }
        ]
        result = _simplify_tree(nodes)
        assert "id" in result[0]
        assert "role" in result[0]
        assert "name" in result[0]
        assert "comment" in result[0]
        assert "annotation_status" in result[0]
        assert "classification" in result[0]
        assert "description" not in result[0]
        assert "states" not in result[0]
        assert "actions" not in result[0]

    def test_simplify_tree_preserves_children(self):
        from src.at.generator.case_parser import _simplify_tree

        nodes = [
            {
                "id": "n0",
                "role": "panel",
                "name": "container",
                "children": [
                    {"id": "n1", "role": "push button", "name": "OK"},
                ],
            }
        ]
        result = _simplify_tree(nodes)
        assert len(result[0]["children"]) == 1
        assert result[0]["children"][0]["name"] == "OK"

    def test_compact_at_tree_to_file_yaml(self, tmp_path):
        from src.at.generator.case_parser import compact_at_tree_to_file

        import yaml

        tree_data = {
            "version": "1.0",
            "tree": [
                {
                    "id": "n0",
                    "role": "push button",
                    "name": "OK",
                    "classification": "interactive",
                    "comment": "",
                    "annotation_status": "draft",
                },
            ],
        }
        at_tree_path = tmp_path / "at-tree.yaml"
        at_tree_path.write_text(yaml.dump(tree_data, allow_unicode=True, sort_keys=False))

        output_path = str(tmp_path / "compact.yaml")
        compact_at_tree_to_file(str(at_tree_path), output_path, fmt="yaml")

        result = yaml.safe_load(Path(output_path).read_text())
        assert "version" in result
        assert "tree" in result
        assert len(result["tree"]) == 1
        assert result["tree"][0]["comment"] == ""
        assert result["tree"][0]["annotation_status"] == "draft"

    def test_compact_at_tree_to_file_text(self, tmp_path):
        from src.at.generator.case_parser import compact_at_tree_to_file

        import yaml

        tree_data = {
            "version": "1.0",
            "tree": [
                {"id": "n0", "role": "push button", "name": "OK", "children": []},
            ],
        }
        at_tree_path = tmp_path / "at-tree.yaml"
        at_tree_path.write_text(yaml.dump(tree_data, allow_unicode=True, sort_keys=False))

        output_path = str(tmp_path / "compact.txt")
        compact_at_tree_to_file(str(at_tree_path), output_path, fmt="text")

        content = Path(output_path).read_text()
        assert "n0" in content
        assert "push button" in content
        assert "OK" in content
