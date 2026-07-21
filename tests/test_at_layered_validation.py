# SPDX-FileCopyrightText: 2026 Uniontech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only

"""Tests for R4 layered validation: L1 checks (gate3 extensions), L2/L3 runner."""

from __future__ import annotations

import sys
import types
from pathlib import Path

import yaml

_src_root = Path(__file__).resolve().parent.parent / "src"
if str(_src_root) not in sys.path:
    sys.path.insert(0, str(_src_root))
stub = sys.modules.get("src")
if stub is not None and getattr(stub, "__spec__", None) is None:
    sys.modules["src"] = types.ModuleType("src")
    sys.modules["src"].__path__ = [str(_src_root)]
    sys.modules["src"].__package__ = "src"
    sys.modules["src"].__file__ = str(_src_root / "__init__.py")

from src.at.validator.gates import _check_duplicate_blocks, validate_gate3


def _write_cases_mapped(path, cases):
    content = "# === 格式范例 ===\n# ...\n" + yaml.dump(
        {"cases": cases}, allow_unicode=True, sort_keys=False, default_flow_style=False
    )
    path.write_text(content, encoding="utf-8")
    return str(path)


# ---- L1: action-role consistency ----


def test_l1_action_role_mismatch_fails(tmp_path):
    at_tree = {
        "version": "1.0",
        "tree": [
            {
                "id": "n0",
                "role": "menu item",
                "name": "Settings",
                "classification": "interactive",
                "comment": "GUI位置: 菜单 | 功能: 设置",
            }
        ],
    }
    tree_path = tmp_path / "at-tree.yaml"
    tree_path.write_text(yaml.dump(at_tree, allow_unicode=True), encoding="utf-8")

    cases = [
        {
            "id": "s1",
            "status": "active",
            "annotation": {"测试界面": "main", "测试功能": "test"},
            "steps": [
                {
                    "action": "keyboard_type",
                    "selector": {"name": "Settings", "role": "menu item"},
                    "text": "hello",
                },
            ],
        }
    ]
    path = _write_cases_mapped(tmp_path / "cases_mapped.yaml", cases)
    result = validate_gate3(path, str(tree_path))
    assert not result["passed"]
    assert any("incompatible" in e or "role" in e for e in result["errors"])


def test_l1_action_role_match_passes(tmp_path):
    at_tree = {
        "version": "1.0",
        "tree": [
            {
                "id": "n0",
                "role": "entry",
                "name": "InputField",
                "classification": "interactive",
                "comment": "GUI位置: 主界面 | 功能: 输入",
            }
        ],
    }
    tree_path = tmp_path / "at-tree.yaml"
    tree_path.write_text(yaml.dump(at_tree, allow_unicode=True), encoding="utf-8")

    cases = [
        {
            "id": "s1",
            "status": "active",
            "annotation": {"测试界面": "main", "测试功能": "test"},
            "steps": [
                {
                    "action": "keyboard_type",
                    "selector": {"name": "InputField", "role": "entry"},
                    "text": "hello",
                },
            ],
        }
    ]
    path = _write_cases_mapped(tmp_path / "cases_mapped.yaml", cases)
    result = validate_gate3(path, str(tree_path))
    assert result["passed"]


# ---- L1: duplicate step block detection ----


def test_duplicate_blocks_detected():
    steps = [
        {"action": "mouse_click", "selector": {"name": "Btn"}, "key": "", "text": ""},
        {"action": "mouse_click", "selector": {"name": "Btn"}, "key": "", "text": ""},
        {"action": "mouse_click", "selector": {"name": "Btn"}, "key": "", "text": ""},
    ]
    report = {"errors": [], "warnings": [], "passed": True}
    _check_duplicate_blocks(steps, "s1", report)
    assert any("duplicate" in w.lower() for w in report["warnings"])


def test_duplicate_blocks_not_triggered_for_different():
    steps = [
        {"action": "mouse_click", "selector": {"name": "Btn1"}},
        {"action": "mouse_click", "selector": {"name": "Btn2"}},
        {"action": "mouse_click", "selector": {"name": "Btn3"}},
    ]
    report = {"errors": [], "warnings": [], "passed": True}
    _check_duplicate_blocks(steps, "s1", report)
    assert not any("duplicate" in w.lower() for w in report["warnings"])


def test_duplicate_blocks_short_sequence():
    steps = [
        {"action": "mouse_click", "selector": {"name": "Btn"}},
        {"action": "mouse_click", "selector": {"name": "Btn"}},
    ]
    report = {"errors": [], "warnings": [], "passed": True}
    _check_duplicate_blocks(steps, "s1", report)
    assert not any("duplicate" in w.lower() for w in report["warnings"])


# ---- L1: assertion coverage ----


def test_low_assertion_coverage_warned(tmp_path):
    at_tree = {"version": "1.0", "tree": [{"id": "n0", "role": "button", "name": "Btn"}]}
    tree_path = tmp_path / "at-tree.yaml"
    tree_path.write_text(yaml.dump(at_tree), encoding="utf-8")

    cases = [
        {
            "id": "s1",
            "status": "active",
            "annotation": {"测试界面": "main", "测试功能": "test"},
            "steps": [
                {"action": "mouse_click", "selector": {"name": "Btn"}},
                {"step_type": "assert", "action": "assert_window"},
            ],
        }
    ]
    path = _write_cases_mapped(tmp_path / "cases_mapped.yaml", cases)
    result = validate_gate3(path, str(tree_path))
    assert any("low_assertion_coverage" in w or "non-assert_window" in w for w in result["warnings"])


def test_good_assertion_coverage_no_warning(tmp_path):
    at_tree = {"version": "1.0", "tree": [{"id": "n0", "role": "button", "name": "Btn"}]}
    tree_path = tmp_path / "at-tree.yaml"
    tree_path.write_text(yaml.dump(at_tree), encoding="utf-8")

    cases = [
        {
            "id": "s1",
            "status": "active",
            "annotation": {"测试界面": "main", "测试功能": "test"},
            "steps": [
                {"action": "mouse_click", "selector": {"name": "Btn"}},
                {"step_type": "assert", "action": "assert_element", "selector": {"name": "Btn"}},
            ],
        }
    ]
    path = _write_cases_mapped(tmp_path / "cases_mapped.yaml", cases)
    result = validate_gate3(path, str(tree_path))
    assert not any("low_assertion_coverage" in w for w in result["warnings"])


# ---- L2/L3: runner functions (mock smoke/verify) ----


def test_select_representative_case_fewest_steps():
    from src.at.executor.runner import _select_representative_case

    cases = [
        {"id": "c1", "steps": [{"step_type": "action"}, {"step_type": "action"}, {"step_type": "assert"}]},
        {"id": "c2", "steps": [{"step_type": "action"}, {"step_type": "assert"}]},
        {"id": "c3", "steps": [{"step_type": "action"}, {"step_type": "action"}, {"step_type": "action"}, {"step_type": "assert"}]},
    ]
    result = _select_representative_case(cases)
    assert result["id"] == "c2"


def test_select_representative_case_empty():
    from src.at.executor.runner import _select_representative_case

    assert _select_representative_case([]) is None


def test_smoke_test_no_suite_file(tmp_path):
    from src.at.executor.runner import smoke_test_module

    module_dir = tmp_path / "test_module"
    module_dir.mkdir()
    result = smoke_test_module(str(module_dir))
    assert result["status"] == "skip"
    assert "no" in result["reason"].lower()


def test_verify_single_case_file_not_found():
    from src.at.executor.runner import verify_single_case

    result = verify_single_case("/nonexistent/path.suite.yaml")
    assert result["status"] == "error"
