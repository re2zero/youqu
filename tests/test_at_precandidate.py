# SPDX-FileCopyrightText: 2026 Uniontech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only

"""Tests for precandidate pipeline: pre-filter, scoring, candidate embedding."""

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

from src.at.generator.action_rules import (
    classify_menu_type,
    get_action_for_role,
    get_menu_action,
    guess_role_from_description,
)
from src.at.generator.precandidate import (
    _build_index,
    _find_candidates,
    _score_node,
    _tokenize,
    precandidate_from_cases,
    precandidate_from_module,
)


# ---- action_rules tests ----


def test_get_action_for_button():
    action = get_action_for_role("button")
    assert action["action"] == "element_action"
    assert action["do"] == "click"
    assert action["wait"] == 0.3


def test_get_action_for_menu_item():
    action = get_action_for_role("menu item")
    assert action["action"] == "element_action"
    assert action["do"] == "click"


def test_classify_menu_type_context():
    assert classify_menu_type("右键菜单选择复制") == "dtk_context_menu"
    assert classify_menu_type("right-click the workspace") == "dtk_context_menu"


def test_classify_menu_type_main():
    assert classify_menu_type("点击标题栏菜单设置") == "dtk_main_menu"
    assert classify_menu_type("open the menu bar") == "dtk_main_menu"


def test_classify_menu_type_default():
    assert classify_menu_type("选择菜单项") == "dtk_context_menu"


def test_get_menu_action_context():
    action = get_menu_action("右键点击工作区")
    assert action["action"] == "dtk_context_menu"
    assert action["requires"] == "dtk_context_menu"


def test_get_menu_action_main():
    action = get_menu_action("点击主菜单设置")
    assert action["action"] == "dtk_main_menu"
    assert action["requires"] == "dtk_main_menu"


def test_get_action_for_unknown_role_defaults():
    action = get_action_for_role("unknown_role")
    assert action["action"] == "element_action"


def test_guess_role_from_description_button():
    assert guess_role_from_description("点击确认按钮") == "button"
    assert guess_role_from_description("click the button") == "button"


def test_guess_role_from_description_menu():
    assert guess_role_from_description("选择菜单项") == "menu item"


def test_guess_role_from_description_none():
    assert guess_role_from_description("do something") is None


# ---- tokenizer tests ----


def test_tokenize_chinese():
    tokens = _tokenize("打开终端，点击设置按钮")
    assert "打开终端" in tokens
    assert "点击设置按钮" in tokens


def test_tokenize_strips_numbers():
    tokens = _tokenize("1. 打开终端")
    assert all(not t.startswith("1") for t in tokens)
    assert "打开终端" in tokens


# ---- scoring tests ----


def test_score_node_name_exact_match():
    node = {"name": "搜索", "role": "button", "comment": "", "accessible_id": ""}
    score = _score_node("搜索", ["搜索"], node)
    assert score >= 3.0


def test_score_node_name_substring():
    node = {"name": "search_btn", "role": "button", "comment": "", "accessible_id": ""}
    score = _score_node("点击search", ["点击", "search"], node)
    assert score > 0


def test_score_node_comment_keyword():
    node = {"name": "", "role": "", "comment": "查找按钮", "accessible_id": ""}
    score = _score_node("查找内容", ["查找", "内容"], node)
    assert score > 0


def test_score_node_no_match():
    node = {"name": "xyz", "role": "label", "comment": "无关", "accessible_id": ""}
    score = _score_node("点击搜索", ["点击", "搜索"], node)
    assert score == 0.0


# ---- index building ----


def test_build_index(tmp_path):
    at_tree = {
        "version": "1.0",
        "tree": [
            {
                "id": "n0",
                "role": "frame",
                "name": "",
                "classification": "container",
                "comment": "主窗口",
                "children": [
                    {
                        "id": "n1",
                        "role": "button",
                        "name": "SearchBtn",
                        "classification": "interactive",
                        "comment": "查找按钮",
                    },
                    {
                        "id": "n2",
                        "role": "label",
                        "name": "status",
                        "classification": "static",
                        "comment": "状态栏",
                    },
                ],
            }
        ],
    }
    tree_path = tmp_path / "at-tree.yaml"
    tree_path.write_text(yaml.dump(at_tree, allow_unicode=True), encoding="utf-8")

    index = _build_index(str(tree_path))
    ids = [n["id"] for n in index]
    assert "n1" in ids


# ---- candidate finding ----


def test_find_candidates_returns_top_k(tmp_path):
    at_tree = {
        "version": "1.0",
        "tree": [
            {
                "id": "n0",
                "role": "frame",
                "classification": "container",
                "children": [
                    {
                        "id": "n1",
                        "role": "button",
                        "name": "SearchBtn",
                        "classification": "interactive",
                        "comment": "查找",
                    },
                    {
                        "id": "n2",
                        "role": "button",
                        "name": "OpenBtn",
                        "classification": "interactive",
                        "comment": "打开",
                    },
                ],
            }
        ],
    }
    tree_path = tmp_path / "at-tree.yaml"
    tree_path.write_text(yaml.dump(at_tree, allow_unicode=True), encoding="utf-8")

    index = _build_index(str(tree_path))
    candidates = _find_candidates("点击查找按钮", index)
    assert len(candidates) >= 1
    assert candidates[0]["id"] == "n1"
    assert candidates[0]["score"] > 0


def test_find_candidates_no_match():
    index = [{"id": "n1", "name": "xyz", "role": "label", "comment": "无关", "accessible_id": ""}]
    candidates = _find_candidates("点击搜索", index)
    assert candidates == []


def test_find_candidates_menu_item_requires(tmp_path):
    at_tree = {
        "version": "1.0",
        "tree": [
            {
                "id": "n0",
                "role": "frame",
                "classification": "container",
                "children": [
                    {
                        "id": "n1",
                        "role": "menu item",
                        "name": "Settings",
                        "classification": "interactive",
                        "comment": "设置菜单项",
                    },
                ],
            }
        ],
    }
    tree_path = tmp_path / "at-tree.yaml"
    tree_path.write_text(yaml.dump(at_tree, allow_unicode=True), encoding="utf-8")
    index = _build_index(str(tree_path))
    candidates = _find_candidates("点击设置菜单项", index)
    assert len(candidates) == 1
    assert candidates[0].get("requires") == "dtk_main_menu"


# ---- precandidate_from_cases integration ----


def _write_at_tree(path):
    tree = {
        "version": "1.0",
        "tree": [
            {
                "id": "n0",
                "role": "frame",
                "classification": "container",
                "comment": "主窗口",
                "children": [
                    {
                        "id": "n1",
                        "role": "button",
                        "name": "SearchBtn",
                        "classification": "interactive",
                        "comment": "查找按钮",
                    },
                    {
                        "id": "n2",
                        "role": "menu item",
                        "name": "Settings",
                        "classification": "interactive",
                        "comment": "设置菜单项",
                    },
                ],
            }
        ],
    }
    path.write_text(yaml.dump(tree, allow_unicode=True), encoding="utf-8")


def _write_cases(path):
    data = {
        "metadata": {"source": "test.xlsx"},
        "cases": [
            {
                "id": "case_001",
                "name": "查找测试",
                "module": "/V25/查找",
                "description": "查找测试",
                "status": "active",
                "steps": [
                    {"step_type": "action", "description": "点击查找按钮"},
                    {"step_type": "assert", "description": "查找框显示"},
                    {"step_type": "action", "description": "做一些无关操作"},
                ],
            }
        ],
    }
    path.write_text(yaml.dump(data, allow_unicode=True), encoding="utf-8")


def test_precandidate_from_cases(tmp_path):
    cases_path = tmp_path / "cases_raw.yaml"
    at_tree_path = tmp_path / "at-tree.yaml"
    output_path = tmp_path / "suite-cases.yaml"

    _write_cases(cases_path)
    _write_at_tree(at_tree_path)

    result = precandidate_from_cases(
        cases_path=str(cases_path),
        at_tree_path=str(at_tree_path),
        output_path=str(output_path),
    )

    assert result["cases"] == 1
    assert result["steps"] == 3
    assert output_path.exists()

    suite = yaml.safe_load(output_path.read_text(encoding="utf-8"))
    case = suite["cases"][0]
    assert len(case["steps"]) == 3

    step0 = case["steps"][0]
    assert len(step0["candidates"]) > 0
    assert step0["candidates"][0]["name"] == "SearchBtn"
    assert step0["selected"] is None
    assert step0["intent"] is None

    step2 = case["steps"][2]
    assert step2["candidates"] == []
    assert step2["confidence"] == "unsupported"
    assert step2["status"] == "UNSUPPORTED"


def test_precandidate_menu_item_has_requires(tmp_path):
    cases_path = tmp_path / "cases.yaml"
    at_tree_path = tmp_path / "at-tree.yaml"
    output_path = tmp_path / "out.yaml"

    _write_at_tree(at_tree_path)
    data = {
        "metadata": {"source": "t.xlsx"},
        "cases": [
            {
                "id": "c1",
                "name": "test",
                "module": "",
                "description": "test",
                "status": "active",
                "steps": [{"step_type": "action", "description": "点击设置菜单项"}],
            }
        ],
    }
    cases_path.write_text(yaml.dump(data, allow_unicode=True), encoding="utf-8")

    precandidate_from_cases(str(cases_path), str(at_tree_path), str(output_path))
    suite = yaml.safe_load(output_path.read_text(encoding="utf-8"))
    step = suite["cases"][0]["steps"][0]
    assert len(step["candidates"]) == 1
    assert step["candidates"][0].get("requires") == "dtk_main_menu"
