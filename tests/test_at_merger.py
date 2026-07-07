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
import yaml


class TestAssignIds:

    def test_assigns_sequential_ids(self):
        from src.at.scanner.merger import _assign_ids

        nodes = [{"name": "a"}, {"name": "b"}]
        _assign_ids(nodes)
        assert nodes[0]["id"] == "n0"
        assert nodes[1]["id"] == "n1"

    def test_assigns_ids_recursively(self):
        from src.at.scanner.merger import _assign_ids

        nodes = [{"name": "a", "children": [{"name": "b"}, {"name": "c"}]}]
        _assign_ids(nodes)
        assert nodes[0]["id"] == "n0"
        assert nodes[0]["children"][0]["id"] == "n1"
        assert nodes[0]["children"][1]["id"] == "n2"


class TestMatchStaticToRuntime:

    def test_matches_by_object_name(self):
        from src.at.scanner.merger import _match_static_to_runtime

        runtime = [
            {"id": "n0", "name": "mainWindow", "role": "frame"},
            {"id": "n1", "name": "Save", "role": "push button"},
        ]
        static = [
            {"class_name": "MainWindow", "object_names": ["mainWindow"], "accessible_names": ["main_win"]},
        ]
        matches = _match_static_to_runtime(static, runtime)
        assert "n0" in matches
        assert matches["n0"]["class_name"] == "MainWindow"

    def test_matches_by_accessible_id(self):
        from src.at.scanner.merger import _match_static_to_runtime

        runtime = [
            {"id": "n0", "name": "Window", "accessible_id": "main_win", "role": "frame"},
        ]
        static = [
            {"class_name": "MainWindow", "object_names": [], "accessible_names": ["main_win"]},
        ]
        matches = _match_static_to_runtime(static, runtime)
        assert "n0" in matches

    def test_no_match_returns_empty(self):
        from src.at.scanner.merger import _match_static_to_runtime

        runtime = [{"id": "n0", "name": "other", "role": "frame"}]
        static = [{"class_name": "Foo", "object_names": ["bar"], "accessible_names": []}]
        matches = _match_static_to_runtime(static, runtime)
        assert matches == {}


class TestMergeTrees:

    def test_runtime_only(self):
        from src.at.scanner.merger import merge_trees

        runtime = [
            {"name": "main", "role": "frame", "children": [{"name": "btn", "role": "push button"}]},
        ]
        result = merge_trees(runtime, [])
        assert len(result) == 1
        assert result[0]["source"] == "runtime"
        assert result[0]["id"] == "n0"
        assert result[0]["children"][0]["id"] == "n1"
        assert result[0]["children"][0]["source"] == "runtime"

    def test_empty_inputs(self):
        from src.at.scanner.merger import merge_trees

        result = merge_trees([], [])
        assert result == []

    def test_static_enriches_runtime(self):
        from src.at.scanner.merger import merge_trees

        runtime = [
            {"name": "mainWindow", "role": "frame", "object_name": "", "accessible_id": ""},
        ]
        static = [
            {"class_name": "MainWindow", "object_names": ["mainWindow"], "accessible_names": ["main_win"]},
        ]
        result = merge_trees(runtime, static)
        assert result[0]["object_name"] == "mainWindow"
        assert result[0]["accessible_id"] == "main_win"
        assert result[0]["source"] == "static+runtime"

    def test_unmatched_static_appended(self):
        from src.at.scanner.merger import merge_trees

        runtime = [
            {"name": "visible_win", "role": "frame"},
        ]
        static = [
            {"class_name": "HiddenDialog", "object_names": ["hiddenDlg"], "accessible_names": ["hidden_dlg"]},
        ]
        result = merge_trees(runtime, static)
        assert len(result) == 2
        hidden = [n for n in result if n.get("source") == "static"]
        assert len(hidden) == 1
        assert hidden[0]["name"] == "hiddenDlg"

    def test_does_not_mutate_input(self):
        from src.at.scanner.merger import merge_trees

        runtime = [{"name": "a", "role": "frame"}]
        static = [{"class_name": "A", "object_names": ["a"], "accessible_names": []}]
        merge_trees(runtime, static)
        assert "id" not in runtime[0]
        assert "source" not in runtime[0]


class TestWriteAtTreeYaml:

    def test_writes_valid_yaml(self, tmp_path):
        from src.at.scanner.merger import write_at_tree_yaml

        tree = [{"id": "n0", "name": "main", "role": "frame", "source": "runtime"}]
        output = str(tmp_path / "at-tree.yaml")
        write_at_tree_yaml(tree, output, app_name="test-app")

        with open(output) as f:
            doc = yaml.safe_load(f)

        assert doc["version"] == "1.0"
        assert doc["app"] == "test-app"
        assert len(doc["tree"]) == 1
        assert doc["tree"][0]["name"] == "main"

    def test_creates_parent_dirs(self, tmp_path):
        from src.at.scanner.merger import write_at_tree_yaml

        output = str(tmp_path / "nested" / "dir" / "at-tree.yaml")
        write_at_tree_yaml([], output)
        assert Path(output).exists()
