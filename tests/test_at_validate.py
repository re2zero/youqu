# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

import sys
import types
from pathlib import Path

_src_root = Path(__file__).resolve().parent.parent / "src"
if str(_src_root) not in sys.path:
    sys.path.insert(0, str(_src_root))
stub = sys.modules.get("src")
if stub is not None and getattr(stub, "__spec__", None) is None:
    sys.modules["src"] = types.ModuleType("src")
    sys.modules["src"].__path__ = [str(_src_root)]
    sys.modules["src"].__package__ = "src"
    sys.modules["src"].__file__ = str(_src_root / "__init__.py")

import pytest
import yaml


def _write_yaml(path: Path, data: dict) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False))
    return str(path)


class TestGate1:
    def test_passes_with_valid_annotations(self, tmp_path):
        from src.at.validator.gates import validate_gate1

        tree = {
            "version": "1.0",
            "tree": [
                {
                    "id": "n0",
                    "role": "push button",
                    "name": "OK",
                    "classification": "interactive",
                    "comment": "GUI位置: 工具栏 | 功能: 确认操作",
                    "annotation_status": "reviewed",
                    "children": [],
                }
            ],
        }
        tree_path = _write_yaml(tmp_path / "at-tree-annotated.yaml", tree)
        result = validate_gate1(tree_path)
        assert result["passed"]
        assert len(result["errors"]) == 0

    def test_fails_on_missing_comment(self, tmp_path):
        from src.at.validator.gates import validate_gate1

        tree = {
            "version": "1.0",
            "tree": [
                {
                    "id": "n0",
                    "role": "push button",
                    "name": "OK",
                    "classification": "interactive",
                    "comment": "",
                    "annotation_status": "draft",
                    "children": [],
                }
            ],
        }
        tree_path = _write_yaml(tmp_path / "at-tree-annotated.yaml", tree)
        result = validate_gate1(tree_path)
        assert not result["passed"]
        assert any("missing comment" in e for e in result["errors"])

    def test_fails_on_bad_comment_format(self, tmp_path):
        from src.at.validator.gates import validate_gate1

        tree = {
            "version": "1.0",
            "tree": [
                {
                    "id": "n0",
                    "role": "push button",
                    "name": "OK",
                    "classification": "interactive",
                    "comment": "just some text",
                    "annotation_status": "draft",
                    "children": [],
                }
            ],
        }
        tree_path = _write_yaml(tmp_path / "at-tree-annotated.yaml", tree)
        result = validate_gate1(tree_path)
        assert not result["passed"]
        assert any("comment format invalid" in e for e in result["errors"])

    def test_fails_on_noise_name(self, tmp_path):
        from src.at.validator.gates import validate_gate1

        tree = {
            "version": "1.0",
            "tree": [
                {
                    "id": "n0",
                    "role": "panel",
                    "name": "Form_mainwindow",
                    "classification": "container",
                    "comment": "",
                    "annotation_status": "draft",
                    "children": [],
                }
            ],
        }
        tree_path = _write_yaml(tmp_path / "at-tree-annotated.yaml", tree)
        result = validate_gate1(tree_path)
        assert not result["passed"]
        assert any("noise name" in e for e in result["errors"])

    def test_warns_on_missing_element_gaps(self, tmp_path):
        from src.at.validator.gates import validate_gate1

        tree = {"version": "1.0", "tree": []}
        tree_path = _write_yaml(tmp_path / "at-tree-annotated.yaml", tree)
        result = validate_gate1(tree_path, element_gaps_path=str(tmp_path / "nonexistent.yaml"))
        assert result["passed"]
        assert any("element_gaps.yaml not found" in w for w in result["warnings"])


class TestGate2:
    def test_passes_with_valid_suite(self, tmp_path):
        from src.at.validator.gates import validate_gate2

        cases = {
            "cases": [
                {
                    "id": "case_001",
                    "name": "test_open_file",
                    "status": "active",
                    "annotation": {
                        "测试界面": "主窗口",
                        "测试功能": "打开文件",
                        "前置条件": "应用已启动",
                        "AT元素引用": "OK",
                    },
                    "steps": [
                        {"step_type": "action", "description": "点击打开按钮"},
                        {"step_type": "assert", "description": "文件已打开"},
                    ],
                }
            ]
        }
        cases_path = _write_yaml(tmp_path / "suite-cases.yaml", cases)
        tree = {"version": "1.0", "tree": [{"id": "n0", "name": "OK", "role": "push button"}]}
        tree_path = _write_yaml(tmp_path / "at-tree-annotated.yaml", tree)

        result = validate_gate2(cases_path, tree_path)
        assert result["passed"]
        assert len(result["errors"]) == 0

    def test_fails_on_missing_annotation(self, tmp_path):
        from src.at.validator.gates import validate_gate2

        cases = {
            "cases": [
                {
                    "id": "case_001",
                    "name": "test_open",
                    "status": "active",
                    "annotation": {},
                    "steps": [
                        {"step_type": "action", "description": "click"},
                        {"step_type": "assert", "description": "verify"},
                    ],
                }
            ]
        }
        cases_path = _write_yaml(tmp_path / "suite-cases.yaml", cases)
        result = validate_gate2(cases_path)
        assert not result["passed"]
        assert any("测试界面" in e for e in result["errors"])

    def test_fails_on_no_assert(self, tmp_path):
        from src.at.validator.gates import validate_gate2

        cases = {
            "cases": [
                {
                    "id": "case_001",
                    "name": "test_open",
                    "status": "active",
                    "annotation": {
                        "测试界面": "主窗口",
                        "测试功能": "打开",
                        "前置条件": "无",
                        "AT元素引用": "",
                    },
                    "steps": [
                        {"step_type": "action", "description": "click"},
                    ],
                }
            ]
        }
        cases_path = _write_yaml(tmp_path / "suite-cases.yaml", cases)
        result = validate_gate2(cases_path)
        assert not result["passed"]
        assert any("no assert steps" in e for e in result["errors"])

    def test_fails_on_bad_at_ref(self, tmp_path):
        from src.at.validator.gates import validate_gate2

        cases = {
            "cases": [
                {
                    "id": "case_001",
                    "name": "test_open",
                    "status": "active",
                    "annotation": {
                        "测试界面": "主窗口",
                        "测试功能": "打开",
                        "前置条件": "无",
                        "AT元素引用": "NonExistent",
                    },
                    "steps": [
                        {"step_type": "action", "description": "click"},
                        {"step_type": "assert", "description": "verify"},
                    ],
                }
            ]
        }
        cases_path = _write_yaml(tmp_path / "suite-cases.yaml", cases)
        tree = {"version": "1.0", "tree": [{"id": "n0", "name": "OK", "role": "push button"}]}
        tree_path = _write_yaml(tmp_path / "at-tree-annotated.yaml", tree)

        result = validate_gate2(cases_path, tree_path)
        assert not result["passed"]
        assert any("NonExistent" in e for e in result["errors"])

    def test_skips_non_gui(self, tmp_path):
        from src.at.validator.gates import validate_gate2

        cases = {
            "cases": [
                {
                    "id": "case_001",
                    "name": "test_cli",
                    "status": "non_gui",
                    "annotation": {},
                    "steps": [],
                }
            ]
        }
        cases_path = _write_yaml(tmp_path / "suite-cases.yaml", cases)
        result = validate_gate2(cases_path)
        assert result["passed"]


class TestGate3:
    def test_fails_on_missing_format_example(self, tmp_path):
        from src.at.validator.gates import validate_gate3

        cases = {"cases": []}
        cases_path = _write_yaml(tmp_path / "cases_mapped.yaml", cases)
        result = validate_gate3(cases_path)
        assert not result["passed"]
        assert any("format example" in e for e in result["errors"])

    def test_passes_with_format_example(self, tmp_path):
        from src.at.validator.gates import validate_gate3

        content = "# === 格式范例 ===\n# ...\n" + yaml.dump(
            {"cases": []}, allow_unicode=True, sort_keys=False
        )
        path = tmp_path / "cases_mapped.yaml"
        path.write_text(content)
        result = validate_gate3(str(path))
        assert result["passed"]

    def test_fails_on_noise_selector(self, tmp_path):
        from src.at.validator.gates import validate_gate3

        cases = {
            "cases": [
                {
                    "id": "suite_001",
                    "status": "active",
                    "annotation": {"测试界面": "main", "测试功能": "test"},
                    "steps": [
                        {"action": "mouse_click", "selector": {"name": "Form_mainwindow"}},
                    ],
                }
            ]
        }
        path = tmp_path / "cases_mapped.yaml"
        content = "# === 格式范例 ===\n# ...\n" + yaml.dump(
            cases, allow_unicode=True, sort_keys=False
        )
        path.write_text(content)
        result = validate_gate3(str(path))
        assert not result["passed"]
        assert any("noise" in e for e in result["errors"])

    def test_fails_on_invalid_action(self, tmp_path):
        from src.at.validator.gates import validate_gate3

        cases = {
            "cases": [
                {
                    "id": "suite_001",
                    "status": "active",
                    "annotation": {"测试界面": "main", "测试功能": "test"},
                    "steps": [
                        {"action": "invalid_action", "selector": {"name": "OK"}},
                    ],
                }
            ]
        }
        path = tmp_path / "cases_mapped.yaml"
        content = "# === 格式范例 ===\n# ...\n" + yaml.dump(
            cases, allow_unicode=True, sort_keys=False
        )
        path.write_text(content)
        result = validate_gate3(str(path))
        assert not result["passed"]
        assert any("invalid action" in e for e in result["errors"])

    def test_fails_on_selector_not_in_tree(self, tmp_path):
        from src.at.validator.gates import validate_gate3

        cases = {
            "cases": [
                {
                    "id": "suite_001",
                    "status": "active",
                    "annotation": {"测试界面": "main", "测试功能": "test"},
                    "steps": [
                        {"action": "mouse_click", "selector": {"name": "NonExistent"}},
                    ],
                }
            ]
        }
        path = tmp_path / "cases_mapped.yaml"
        content = "# === 格式范例 ===\n# ...\n" + yaml.dump(
            cases, allow_unicode=True, sort_keys=False
        )
        path.write_text(content)

        tree = {"version": "1.0", "tree": [{"id": "n0", "name": "OK", "role": "push button"}]}
        tree_path = _write_yaml(tmp_path / "at-tree-annotated.yaml", tree)

        result = validate_gate3(str(path), str(tree_path))
        assert not result["passed"]
        assert any("not found in annotated tree" in e for e in result["errors"])


class TestGate4:
    def test_fails_on_missing_dir(self, tmp_path):
        from src.at.validator.gates import validate_gate4

        result = validate_gate4(str(tmp_path / "nonexistent"))
        assert not result["passed"]
        assert any("not found" in e for e in result["errors"])

    def test_fails_on_no_suite_files(self, tmp_path):
        from src.at.validator.gates import validate_gate4

        (tmp_path / "empty.txt").write_text("hello")
        result = validate_gate4(str(tmp_path))
        assert not result["passed"]
        assert any("No .suite.yaml" in e for e in result["errors"])

    def test_passes_with_valid_suite(self, tmp_path):
        from src.at.validator.gates import validate_gate4

        suite_data = {
            "suites": [
                {
                    "id": "spec_001",
                    "steps": [
                        {"action": "mouse_click", "selector": {"name": "OK"}},
                    ],
                }
            ]
        }
        _write_yaml(tmp_path / "test.suite.yaml", suite_data)
        result = validate_gate4(str(tmp_path))
        assert result["passed"]

    def test_fails_on_noise_selector(self, tmp_path):
        from src.at.validator.gates import validate_gate4

        suite_data = {
            "suites": [
                {
                    "id": "spec_001",
                    "steps": [
                        {"action": "mouse_click", "selector": {"name": "123"}},
                    ],
                }
            ]
        }
        _write_yaml(tmp_path / "test.suite.yaml", suite_data)
        result = validate_gate4(str(tmp_path))
        assert not result["passed"]
        assert any("noise" in e for e in result["errors"])
