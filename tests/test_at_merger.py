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

    def test_matches_by_object_name_to_runtime_object_name(self):
        from src.at.scanner.merger import _match_static_to_runtime

        runtime = [
            {"id": "n0", "name": "", "role": "frame", "object_name": "CentralView"},
            {"id": "n1", "name": "DMainWindow", "role": "frame", "object_name": ""},
        ]
        static = [
            {
                "class_name": "FileManagerWindow",
                "object_names": ["CentralView"],
                "accessible_names": [],
            },
        ]
        matches = _match_static_to_runtime(static, runtime)
        assert "n0" in matches
        assert "n1" not in matches

    def test_matches_by_class_name_to_runtime_object_name(self):
        from src.at.scanner.merger import _match_static_to_runtime

        runtime = [
            {"id": "n0", "name": "", "role": "panel", "object_name": "MyWidget"},
        ]
        static = [
            {
                "class_name": "MyWidget",
                "object_names": [],
                "accessible_names": [],
            },
        ]
        matches = _match_static_to_runtime(static, runtime)
        assert "n0" in matches


class TestMergeStateSnapshots:
    def test_loads_state_files_from_directory(self, tmp_path):
        from src.at.scanner.merger import load_state_snapshots

        states_dir = tmp_path / "states"
        states_dir.mkdir()
        for i, label in enumerate(["menu", "dialog"]):
            data = {"version": "1.0", "app": "test", "type": "state", "state_label": label}
            data["tree"] = [{"role": "frame", "name": f"win_{label}", "object_name": ""}]
            with open(states_dir / f"{i:02d}_{label}.yaml", "w") as f:
                yaml.dump(data, f)

        snapshots = load_state_snapshots(str(states_dir))
        assert len(snapshots) == 2
        assert snapshots[0][0] == "menu"
        assert snapshots[1][0] == "dialog"

    def test_returns_empty_for_nonexistent_dir(self):
        from src.at.scanner.merger import load_state_snapshots

        assert load_state_snapshots("/nonexistent/path") == []

    def test_merges_new_nodes_from_state(self):
        from src.at.scanner.merger import merge_state_snapshots

        base = [{"role": "frame", "name": "main", "object_name": ""}]
        state_tree = [{"role": "menu", "name": "File", "object_name": ""}]
        result = merge_state_snapshots(base, [("menu_open", state_tree)])
        assert len(result) == 2
        assert result[1]["name"] == "File"
        assert result[1]["state_labels"] == ["menu_open"]

    def test_updates_existing_nodes_with_state_label(self):
        from src.at.scanner.merger import merge_state_snapshots

        base = [{"role": "frame", "name": "main", "object_name": "win"}]
        state_tree = [{"role": "frame", "name": "main", "object_name": "win"}]
        result = merge_state_snapshots(base, [("default", state_tree)])
        assert len(result) == 1
        assert result[0]["state_labels"] == ["default"]

    def test_merges_children_from_state_into_existing_parent(self):
        from src.at.scanner.merger import merge_state_snapshots

        base = [
            {"role": "frame", "name": "main", "object_name": "", "children": []},
        ]
        state_tree = [
            {
                "role": "frame",
                "name": "main",
                "object_name": "",
                "children": [{"role": "menu item", "name": "Open", "object_name": ""}],
            },
        ]
        result = merge_state_snapshots(base, [("menu", state_tree)])
        assert len(result) == 1
        assert len(result[0]["children"]) == 1
        assert result[0]["children"][0]["name"] == "Open"
        assert result[0]["children"][0]["state_labels"] == ["menu"]


class TestIsNoiseStaticClass:
    def test_filters_class_without_names_and_non_ui_bases(self):
        from src.at.scanner.merger import _is_noise_static_class

        cls = {
            "class_name": "KeywordStrategy",
            "base_classes": ["KeywordExtractionStrategy"],
            "object_names": [],
            "accessible_names": [],
        }
        assert _is_noise_static_class(cls) is True

    def test_keeps_class_with_object_names(self):
        from src.at.scanner.merger import _is_noise_static_class

        cls = {
            "class_name": "MyWidget",
            "base_classes": ["QObject"],
            "object_names": ["myWidget"],
            "accessible_names": [],
        }
        assert _is_noise_static_class(cls) is False

    def test_keeps_class_with_accessible_names(self):
        from src.at.scanner.merger import _is_noise_static_class

        cls = {
            "class_name": "MyWidget",
            "base_classes": [],
            "object_names": [],
            "accessible_names": ["acc"],
        }
        assert _is_noise_static_class(cls) is False

    def test_keeps_class_with_ui_base_class(self):
        from src.at.scanner.merger import _is_noise_static_class

        cls = {
            "class_name": "FileDialog",
            "base_classes": ["DDialog"],
            "object_names": [],
            "accessible_names": [],
        }
        assert _is_noise_static_class(cls) is False

    def test_filters_class_without_bases_and_without_names(self):
        from src.at.scanner.merger import _is_noise_static_class

        cls = {
            "class_name": "Unknown",
            "base_classes": [],
            "object_names": [],
            "accessible_names": [],
        }
        assert _is_noise_static_class(cls) is True

    def test_flag_overrides_base_classes_when_false(self):
        from src.at.scanner.merger import _is_noise_static_class

        cls = {
            "class_name": "Strategy",
            "base_classes": ["DDialog"],
            "is_ui_widget": False,
            "object_names": [],
            "accessible_names": [],
        }
        assert _is_noise_static_class(cls) is True

    def test_flag_overrides_base_classes_when_true(self):
        from src.at.scanner.merger import _is_noise_static_class

        cls = {
            "class_name": "CustomWidget",
            "base_classes": [],
            "is_ui_widget": True,
            "object_names": [],
            "accessible_names": [],
        }
        assert _is_noise_static_class(cls) is False


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
        assert hidden[0]["name"] == "HiddenDialog"
        assert hidden[0]["class_name"] == "HiddenDialog"
        assert len(hidden[0].get("children", [])) == 1
        assert hidden[0]["children"][0]["name"] == "hiddenDlg"

    def test_does_not_mutate_input(self):
        from src.at.scanner.merger import merge_trees

        runtime = [{"name": "a", "role": "frame"}]
        static = [{"class_name": "A", "object_names": ["a"], "accessible_names": []}]
        merge_trees(runtime, static)
        assert "id" not in runtime[0]
        assert "source" not in runtime[0]


class TestDedupStaticClasses:
    def test_duplicate_class_name_merged(self):
        from src.at.scanner.merger import merge_trees

        runtime = [{"name": "win", "role": "frame"}]
        static = [
            {
                "class_name": "MyWidget",
                "base_classes": ["DMainWindow"],
                "is_ui_widget": True,
                "object_names": ["btn1"],
                "accessible_names": [],
            },
            {
                "class_name": "MyWidget",
                "base_classes": [],
                "is_ui_widget": False,
                "object_names": ["btn2"],
                "accessible_names": [],
            },
        ]
        result = merge_trees(runtime, static)
        static_parents = [n for n in result if n.get("source") == "static"]
        assert len(static_parents) == 1
        assert static_parents[0]["name"] == "MyWidget"
        child_names = [c["name"] for c in static_parents[0].get("children", [])]
        assert "btn1" in child_names
        assert "btn2" in child_names

    def test_dedup_preserves_is_ui_widget_true(self):
        from src.at.scanner.merger import _dedup_static_classes

        classes = [
            {"class_name": "A", "is_ui_widget": False, "object_names": [], "accessible_names": []},
            {"class_name": "A", "is_ui_widget": True, "object_names": [], "accessible_names": []},
        ]
        result = _dedup_static_classes(classes)
        assert len(result) == 1
        assert result[0]["is_ui_widget"] is True


class TestStaticNesting:
    def test_multiple_object_names_nest_under_parent(self):
        from src.at.scanner.merger import merge_trees

        runtime = []
        static = [
            {
                "class_name": "Toolbar",
                "is_ui_widget": True,
                "object_names": ["btn1", "btn2", "btn3"],
                "accessible_names": [],
            },
        ]
        result = merge_trees(runtime, static)
        assert len(result) == 1
        assert result[0]["name"] == "Toolbar"
        assert result[0]["source"] == "static"
        assert len(result[0]["children"]) == 3
        assert result[0]["children"][0]["name"] == "btn1"
        assert result[0]["children"][0]["source"] == "static"

    def test_single_obj_name_equal_class_name_flat(self):
        from src.at.scanner.merger import merge_trees

        runtime = []
        static = [
            {
                "class_name": "SoloWidget",
                "is_ui_widget": True,
                "object_names": ["SoloWidget"],
                "accessible_names": [],
            },
        ]
        result = merge_trees(runtime, static)
        assert len(result) == 1
        assert result[0]["name"] == "SoloWidget"
        assert "children" not in result[0] or len(result[0].get("children", [])) == 0


class TestDedupRuntimeTree:
    def test_named_duplicates_merged(self):
        from src.at.scanner.merger import dedup_runtime_tree

        tree = [
            {"role": "frame", "name": "DMainWindow", "states": ["showing"], "children": [
                {"role": "panel", "name": "A"},
            ]},
            {"role": "frame", "name": "DMainWindow", "states": ["active"], "children": [
                {"role": "panel", "name": "B"},
            ]},
        ]
        result = dedup_runtime_tree(tree)
        assert len(result) == 1
        assert set(result[0]["states"]) == {"showing", "active"}
        child_names = [c["name"] for c in result[0]["children"]]
        assert "A" in child_names
        assert "B" in child_names

    def test_anonymous_duplicates_kept(self):
        from src.at.scanner.merger import dedup_runtime_tree

        tree = [
            {"role": "dialog", "name": "", "children": [{"role": "push button", "name": "OK"}]},
            {"role": "dialog", "name": "", "children": [{"role": "push button", "name": "Cancel"}]},
        ]
        result = dedup_runtime_tree(tree)
        assert len(result) == 2

    def test_mixed_named_and_anonymous(self):
        from src.at.scanner.merger import dedup_runtime_tree

        tree = [
            {"role": "frame", "name": "win1", "states": ["s1"]},
            {"role": "frame", "name": "win1", "states": ["s2"]},
            {"role": "panel", "name": "", "children": [{"role": "label", "name": "x"}]},
            {"role": "panel", "name": "", "children": [{"role": "label", "name": "y"}]},
        ]
        result = dedup_runtime_tree(tree)
        assert len(result) == 3

    def test_children_merged_recursively(self):
        from src.at.scanner.merger import dedup_runtime_tree

        tree = [
            {"role": "popup menu", "name": "MainMenu", "children": [
                {"role": "menu item", "name": "item1", "states": ["showing"]},
            ]},
            {"role": "popup menu", "name": "MainMenu", "children": [
                {"role": "menu item", "name": "item1", "states": ["selected"]},
                {"role": "menu item", "name": "item2"},
            ]},
        ]
        result = dedup_runtime_tree(tree)
        assert len(result) == 1
        children = result[0]["children"]
        item1 = [c for c in children if c["name"] == "item1"][0]
        assert set(item1["states"]) == {"showing", "selected"}
        assert len(children) == 2


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
        from src.at.scanner.clang_scanner import _ALL_UI_CLASSES

        return [
            {
                "class_name": name,
                "source_file": f"/src/{name}.cpp",
                "base_classes": bases,
                "is_ui_widget": any(b in _ALL_UI_CLASSES for b in bases),
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

    def test_skips_non_ui_widget_with_base_classes(self, tmp_path):
        from src.at.scanner.merger import generate_name_gaps_report

        classes = self._make_classes(
            [("KeywordStrategy", ["KeywordExtractionStrategy"], [], [], [])]
        )
        report = generate_name_gaps_report(classes, str(tmp_path / "g.yaml"))
        assert report["gaps"] == []
        assert report["summary"]["total_ui_classes"] == 0

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


class TestIdentityKeyAndDedup:
    def test_accessible_id_distinguishes_same_role_name(self):
        from src.at.scanner.merger import merge_state_snapshots

        base = [
            {"role": "push button", "name": "取消", "object_name": "", "accessible_id": "cancelA"},
            {"role": "push button", "name": "取消", "object_name": "", "accessible_id": "cancelB"},
        ]
        state_tree = [
            {"role": "push button", "name": "取消", "object_name": "", "accessible_id": "cancelA"},
            {"role": "push button", "name": "取消", "object_name": "", "accessible_id": "cancelB"},
        ]
        result = merge_state_snapshots(base, [("dialog_open", state_tree)])
        assert len(result) == 2
        assert result[0]["accessible_id"] == "cancelA"
        assert result[1]["accessible_id"] == "cancelB"

    def test_same_identity_merges_not_duplicates(self):
        from src.at.scanner.merger import merge_state_snapshots

        base = [{"role": "frame", "name": "main", "object_name": "", "accessible_id": ""}]
        snapshots = [
            ("state_a", [{"role": "frame", "name": "main", "object_name": "", "accessible_id": ""}]),
            ("state_b", [{"role": "frame", "name": "main", "object_name": "", "accessible_id": ""}]),
        ]
        result = merge_state_snapshots(base, snapshots)
        assert len(result) == 1
        assert set(result[0]["state_labels"]) == {"state_a", "state_b"}

    def test_states_union_across_snapshots(self):
        from src.at.scanner.merger import merge_state_snapshots

        base = [{"role": "frame", "name": "main", "object_name": "", "accessible_id": "", "states": ["showing"]}]
        snapshots = [
            ("focused", [{"role": "frame", "name": "main", "object_name": "", "accessible_id": "", "states": ["focused", "showing"]}]),
        ]
        result = merge_state_snapshots(base, snapshots)
        assert set(result[0]["states"]) == {"showing", "focused"}

    def test_different_children_under_same_parent_dont_merge(self):
        from src.at.scanner.merger import merge_state_snapshots

        base = [
            {
                "role": "frame", "name": "main", "object_name": "", "accessible_id": "",
                "children": [{"role": "push button", "name": "OK", "object_name": "", "accessible_id": ""}],
            },
        ]
        state_tree = [
            {
                "role": "frame", "name": "main", "object_name": "", "accessible_id": "",
                "children": [{"role": "push button", "name": "Cancel", "object_name": "", "accessible_id": ""}],
            },
        ]
        result = merge_state_snapshots(base, [("dialog", state_tree)])
        assert len(result) == 1
        child_names = {c["name"] for c in result[0]["children"]}
        assert child_names == {"OK", "Cancel"}


class TestNormalizeNode:
    def test_fills_missing_fields(self):
        from src.at.scanner.merger import _normalize_node

        node = {"role": "frame", "name": "main", "source": "runtime"}
        _normalize_node(node)
        assert node["object_name"] == ""
        assert node["accessible_id"] == ""
        assert node["description"] == ""
        assert node["actions"] == []
        assert node["index_in_parent"] == -1
        assert node["states"] == []
        assert node["state_labels"] == []
        assert node["class_name"] == ""

    def test_preserves_existing_values(self):
        from src.at.scanner.merger import _normalize_node

        node = {"role": "frame", "name": "main", "states": ["focused"], "source": "static+runtime"}
        _normalize_node(node)
        assert node["states"] == ["focused"]
        assert node["source"] == "static+runtime"

    def test_normalizes_children_recursively(self):
        from src.at.scanner.merger import _normalize_node

        node = {"role": "frame", "name": "main", "children": [{"role": "push button", "name": "OK"}]}
        _normalize_node(node)
        child = node["children"][0]
        assert child["accessible_id"] == ""
        assert child["states"] == []

    def test_write_at_tree_yaml_produces_uniform_schema(self, tmp_path):
        from src.at.scanner.merger import write_at_tree_yaml

        tree = [
            {"id": "n0", "role": "frame", "name": "main", "source": "runtime", "children": [
                {"id": "n1", "role": "push button", "name": "OK", "source": "runtime"},
            ]},
            {"id": "n2", "role": "panel", "name": "X", "source": "static",
             "class_name": "MyWidget"},
        ]
        out = tmp_path / "out.yaml"
        write_at_tree_yaml(tree, str(out), "test")
        with open(out) as f:
            doc = yaml.safe_load(f)

        def check_keys(n, expected):
            for k in expected:
                assert k in n, f"missing key {k} in node {n.get('name')}"
            if "children" in n:
                for c in n["children"]:
                    check_keys(c, expected)

        expected_keys = {"id", "role", "name", "object_name", "accessible_id",
                         "description", "actions", "index_in_parent", "states",
                         "state_labels", "source", "class_name"}
        for n in doc["tree"]:
            check_keys(n, expected_keys)
