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
    def test_matches_by_accessible_name_to_runtime_name(self):
        from src.at.scanner.merger import _match_static_to_runtime

        runtime = [
            {"id": "n0", "name": "DMainWindow", "role": "frame"},
        ]
        static = [
            {
                "class_name": "FileManagerWindow",
                "object_names": ["CentralView"],
                "accessible_names": ["DMainWindow"],
            },
        ]
        matches = _match_static_to_runtime(static, runtime)
        assert "n0" in matches
        assert matches["n0"]["class_name"] == "FileManagerWindow"

    def test_matches_by_class_name_to_runtime_name(self):
        from src.at.scanner.merger import _match_static_to_runtime

        runtime = [
            {"id": "n0", "name": "DMainWindow", "role": "frame"},
        ]
        static = [
            {
                "class_name": "DMainWindow",
                "object_names": [],
                "accessible_names": [],
            },
        ]
        matches = _match_static_to_runtime(static, runtime)
        assert "n0" in matches

    def test_matches_by_object_name_fallback(self):
        from src.at.scanner.merger import _match_static_to_runtime

        runtime = [
            {"id": "n0", "name": "mainWindow", "role": "frame"},
            {"id": "n1", "name": "Save", "role": "push button"},
        ]
        static = [
            {
                "class_name": "MainWindow",
                "object_names": ["mainWindow"],
                "accessible_names": [],
            },
        ]
        matches = _match_static_to_runtime(static, runtime)
        assert "n0" in matches

    def test_accessible_name_takes_priority_over_class_name(self):
        from src.at.scanner.merger import _match_static_to_runtime

        runtime = [
            {"id": "n0", "name": "CustomName", "role": "frame"},
            {"id": "n1", "name": "DMainWindow", "role": "frame"},
        ]
        static = [
            {
                "class_name": "MyWindow",
                "object_names": [],
                "accessible_names": ["CustomName"],
            },
        ]
        matches = _match_static_to_runtime(static, runtime)
        assert "n0" in matches
        assert "n1" not in matches

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
            {"name": "DMainWindow", "role": "frame", "object_name": "", "accessible_id": ""},
        ]
        static = [
            {
                "class_name": "MyWindow",
                "source_file": "mywindow.cpp",
                "object_names": ["CentralView"],
                "accessible_names": ["DMainWindow"],
            },
        ]
        result = merge_trees(runtime, static)
        assert result[0]["object_name"] == "CentralView"
        assert result[0]["accessible_id"] == "DMainWindow"
        assert result[0]["source"] == "static+runtime"
        assert result[0]["class_name"] == "MyWindow"
        assert result[0]["source_file"] == "mywindow.cpp"

    def test_unmatched_static_appended(self):
        from src.at.scanner.merger import merge_trees

        runtime = [
            {"name": "visible_win", "role": "frame"},
        ]
        static = [
            {
                "class_name": "HiddenDialog",
                "source_file": "hidden.cpp",
                "object_names": ["hiddenDlg"],
                "accessible_names": [],
            },
        ]
        result = merge_trees(runtime, static)
        assert len(result) == 2
        hidden = [n for n in result if n.get("source") == "static"]
        assert len(hidden) == 1
        assert hidden[0]["name"] == "hiddenDlg"
        assert hidden[0]["match_status"] == "unresolved"
        assert hidden[0]["class_name"] == "HiddenDialog"
        assert hidden[0]["source_file"] == "hidden.cpp"

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


class TestFilterNoise:
    def test_removes_empty_leaf_nodes(self):
        from src.at.scanner.merger import filter_noise

        tree = [{"role": "panel", "name": "", "object_name": "", "accessible_id": ""}]
        assert filter_noise(tree) == []

    def test_keeps_leaf_with_name(self):
        from src.at.scanner.merger import filter_noise

        tree = [{"role": "push button", "name": "Save", "object_name": "", "accessible_id": ""}]
        result = filter_noise(tree)
        assert len(result) == 1
        assert result[0]["name"] == "Save"

    def test_keeps_leaf_with_object_name(self):
        from src.at.scanner.merger import filter_noise

        tree = [{"role": "panel", "name": "", "object_name": "sidebar", "accessible_id": ""}]
        result = filter_noise(tree)
        assert len(result) == 1

    def test_keeps_leaf_with_accessible_id(self):
        from src.at.scanner.merger import filter_noise

        tree = [{"role": "panel", "name": "", "object_name": "", "accessible_id": "main_win"}]
        result = filter_noise(tree)
        assert len(result) == 1

    def test_keeps_non_leaf_nodes(self):
        from src.at.scanner.merger import filter_noise

        tree = [{"role": "frame", "name": "", "children": [{"role": "push button", "name": "OK"}]}]
        result = filter_noise(tree)
        assert len(result) == 1

    def test_nested_noise_removal(self):
        from src.at.scanner.merger import filter_noise

        tree = [
            {
                "role": "frame",
                "name": "main",
                "children": [
                    {"role": "panel", "name": "", "object_name": "", "accessible_id": ""},
                    {"role": "push button", "name": "Save"},
                ],
            }
        ]
        result = filter_noise(tree)
        assert len(result) == 1
        assert len(result[0]["children"]) == 1
        assert result[0]["children"][0]["name"] == "Save"


class TestWriteHelpers:
    def test_write_runtime_dump_roundtrip(self, tmp_path):
        from src.at.scanner.merger import write_runtime_dump

        tree = [{"role": "frame", "name": "main"}]
        path = str(tmp_path / "runtime.yaml")
        write_runtime_dump(tree, path, app_name="test-app")

        with open(path) as f:
            doc = yaml.safe_load(f)
        assert doc["version"] == "1.0"
        assert doc["app"] == "test-app"
        assert doc["type"] == "runtime"
        assert doc["tree"][0]["role"] == "frame"

    def test_write_runtime_dump_with_state_label(self, tmp_path):
        from src.at.scanner.merger import write_runtime_dump

        tree = [{"role": "frame", "name": "main"}]
        path = str(tmp_path / "state.yaml")
        write_runtime_dump(tree, path, app_name="app", state_label="menu_open")

        with open(path) as f:
            doc = yaml.safe_load(f)
        assert doc["type"] == "state"
        assert doc["state_label"] == "menu_open"

    def test_write_static_dump_roundtrip(self, tmp_path):
        from src.at.scanner.merger import write_static_dump

        classes = [{"class_name": "W", "base_classes": ["QWidget"]}]
        path = str(tmp_path / "static.yaml")
        write_static_dump(classes, path)

        with open(path) as f:
            doc = yaml.safe_load(f)
        assert doc["type"] == "static"
        assert doc["classes"][0]["class_name"] == "W"


class TestNameGapsReport:
    def _make_classes(self, specs):
        return [
            {
                "class_name": name,
                "source_file": f"/src/{name}.cpp",
                "base_classes": bases,
                "object_names": obj_names,
                "accessible_names": acc_names,
                "dtk_instantiations": dtk,
            }
            for name, bases, obj_names, acc_names, dtk in specs
        ]

    def test_reports_class_with_base_but_no_names(self, tmp_path):
        from src.at.scanner.merger import generate_name_gaps_report

        classes = self._make_classes([("NoName", ["QWidget"], [], [], [])])
        path = str(tmp_path / "gaps.yaml")
        report = generate_name_gaps_report(classes, path, "app")
        assert len(report["gaps"]) == 1
        assert report["gaps"][0]["class_name"] == "NoName"

    def test_skips_class_without_base(self, tmp_path):
        from src.at.scanner.merger import generate_name_gaps_report

        classes = self._make_classes([("Helper", [], [], [], [])])
        report = generate_name_gaps_report(classes, str(tmp_path / "g.yaml"))
        assert report["gaps"] == []

    def test_skips_class_with_object_name(self, tmp_path):
        from src.at.scanner.merger import generate_name_gaps_report

        classes = self._make_classes([("Named", ["QWidget"], ["myWidget"], [], [])])
        report = generate_name_gaps_report(classes, str(tmp_path / "g.yaml"))
        assert report["gaps"] == []

    def test_skips_class_with_accessible_name(self, tmp_path):
        from src.at.scanner.merger import generate_name_gaps_report

        classes = self._make_classes([("Acc", ["QWidget"], [], ["acc_id"], [])])
        report = generate_name_gaps_report(classes, str(tmp_path / "g.yaml"))
        assert report["gaps"] == []

    def test_includes_empty_dtk_instantiations(self, tmp_path):
        from src.at.scanner.merger import generate_name_gaps_report

        classes = self._make_classes([("Plain", ["QWidget"], [], [], [])])
        report = generate_name_gaps_report(classes, str(tmp_path / "g.yaml"))
        assert len(report["gaps"]) == 1

    def test_summary_counts_correct(self, tmp_path):
        from src.at.scanner.merger import generate_name_gaps_report

        classes = self._make_classes(
            [
                ("HasName", ["QWidget"], ["w"], [], []),
                ("NoName", ["QWidget"], [], [], []),
                ("NoBase", [], [], [], []),
            ]
        )
        report = generate_name_gaps_report(classes, str(tmp_path / "g.yaml"))
        assert report["summary"]["total_ui_classes"] == 2
        assert report["summary"]["classes_with_names"] == 1
        assert report["summary"]["classes_missing_names"] == 1
