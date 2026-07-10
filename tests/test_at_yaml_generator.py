# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only

import os
import sys
import types

import pytest
from unittest.mock import MagicMock

_src_mock = sys.modules.get("src")
if not _src_mock or not getattr(_src_mock, "__spec__", None):
    sys.modules["src"] = types.ModuleType("src")
    sys.modules["src"].__path__ = ["/home/zero/work/research/youqu/src"]
    sys.modules["src"].__package__ = "src"
    sys.modules["src"].__file__ = "/home/zero/work/research/youqu/src/__init__.py"
if not isinstance(sys.modules.get("pyatspi"), types.ModuleType):
    sys.modules["pyatspi"] = MagicMock()

import yaml


CASES_YAML = {
    "metadata": {"generated_at": "2026-01-01", "source": "test"},
    "suites": [
        {
            "id": "menu_001",
            "name": "menu_new_window",
            "module": "菜单",
            "status": "active",
            "steps": [
                {"step_type": "navigate", "description": "打开文件菜单", "element_hint": "dtk_main_menu", "menu_path": ["文件", "新建窗口"]},
                {"step_type": "action", "description": "点击播放", "element_hint": "click"},
            ],
        },
        {
            "id": "theme_002",
            "name": "theme_dark",
            "module": "主题",
            "status": "active",
            "steps": [
                {"step_type": "action", "description": "切换暗色主题", "element_hint": "click"},
            ],
        },
        {
            "id": "skipped_003",
            "name": "visual_check",
            "module": "视觉",
            "status": "skipped",
            "reason": "需要人工判断",
            "steps": [
                {"step_type": "action", "description": "查看界面", "element_hint": "visual_check"},
            ],
        },
    ],
}

MAPPINGS_YAML = {
    "metadata": {"generated_at": "2026-01-01", "at_tree_source": "test"},
    "mappings": [
        {
            "case_id": "menu_001",
            "step_index": 0,
            "description": "打开文件菜单",
            "step_type": "navigate",
            "element_hint": "dtk_main_menu",
            "menu_path": ["文件", "新建窗口"],
            "status": "mapped",
        },
        {
            "case_id": "menu_001",
            "step_index": 1,
            "description": "点击播放",
            "step_type": "action",
            "element_hint": "click",
            "element_ref": "play_btn",
            "selector": {"name": "播放", "role": "push button"},
            "status": "mapped",
        },
        {
            "case_id": "theme_002",
            "step_index": 0,
            "description": "切换暗色主题",
            "step_type": "action",
            "element_hint": "click",
            "element_ref": "theme_btn",
            "selector": {"name": "暗色", "role": "radio button"},
            "status": "mapped",
        },
        {
            "case_id": "theme_002",
            "step_index": 1,
            "description": "确认主题变更",
            "step_type": "assert",
            "element_hint": "assert_window",
            "status": "mapped",
        },
    ],
}


def _write_temp(data: dict, path: str):
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True)


def test_extract_elements_from_mappings():
    from src.at.generator.yaml_generator import _extract_elements
    from src.at.parser.models import ElementMappingsDoc

    doc = ElementMappingsDoc.model_validate(MAPPINGS_YAML)
    elements = _extract_elements(doc)
    assert "play_btn" in elements
    assert elements["play_btn"]["name"] == "播放"
    assert elements["play_btn"]["role"] == "push button"
    assert "theme_btn" in elements


def test_extract_elements_skips_unmapped():
    from src.at.generator.yaml_generator import _extract_elements
    from src.at.parser.models import ElementMappingsDoc, MappingEntry, MappingStatus

    doc = ElementMappingsDoc(
        mappings=[
            MappingEntry(case_id="x", step_index=0, description="d", step_type="action", element_ref="r1", selector={"name": "N", "role": "push button"}),
            MappingEntry(case_id="x", step_index=1, description="d", step_type="action", status=MappingStatus.unmapped, reason="not found"),
        ]
    )
    elements = _extract_elements(doc)
    assert "r1" in elements
    assert len(elements) == 1


def test_step_to_action_menu_comb():
    from src.at.generator.yaml_generator import _step_to_action
    from src.at.parser.models import CaseStep, ElementHint, StepType

    step = CaseStep(step_type=StepType.navigate, description="打开文件", element_hint=ElementHint.dtk_main_menu, menu_path=["文件", "新建窗口"])
    action = _step_to_action(step)
    assert action.action == "dtk_main_menu"
    assert action.items == ["文件", "新建窗口"]


def test_step_to_action_element_click():
    from src.at.generator.yaml_generator import _step_to_action
    from src.at.parser.models import CaseStep, ElementHint, StepType

    step = CaseStep(step_type=StepType.action, description="点击播放", action="element_action", element_ref="play_btn", selector={"name": "播放", "role": "push button"})
    action = _step_to_action(step)
    assert action.action == "element_action"
    assert action.ref == "play_btn"
    assert action.do == "click"


def test_step_to_action_keyboard():
    from src.at.generator.yaml_generator import _step_to_action
    from src.at.parser.models import CaseStep, ElementHint, StepType

    step = CaseStep(step_type=StepType.action, description="Ctrl+S", element_hint=ElementHint.keyboard_shortcut)
    action = _step_to_action(step)
    assert action.action == "keyboard_press"
    assert action.key == "Ctrl+S"


def test_step_to_action_assert_element():
    from src.at.generator.yaml_generator import _step_to_action
    from src.at.parser.models import CaseStep, ElementHint, StepType

    step = CaseStep(step_type=StepType.assert_, description="按钮存在", action="assert_element", element_ref="btn1", selector={"name": "OK", "role": "push button"})
    action = _step_to_action(step)
    assert action.action == "assert_element"
    assert action.ref == "btn1"


def test_step_to_action_titlebar():
    from src.at.generator.yaml_generator import _step_to_action
    from src.at.parser.models import CaseStep, ElementHint, StepType

    step = CaseStep(step_type=StepType.action, description="最大化", element_hint=ElementHint.titlebar)
    action = _step_to_action(step)
    assert action.action == "element_action"
    assert action.do == "click"


def test_build_suite_cases_skips_visual():
    from src.at.generator.yaml_generator import _build_suite_cases
    from src.at.parser.models import CaseSuite, CaseStep, ElementHint, StepType

    suite = CaseSuite(
        id="vis_001",
        name="visual_test",
        module="视觉",
        steps=[
            CaseStep(step_type=StepType.action, description="看看界面", element_hint=ElementHint.visual_check),
        ],
    )
    suite_cases = _build_suite_cases(suite)
    assert len(suite_cases) == 0


def test_build_suite_cases_assert_appended():
    from src.at.generator.yaml_generator import _build_suite_cases
    from src.at.parser.models import CaseSuite, CaseStep, ElementHint, StepType

    suite = CaseSuite(
        id="assert_001",
        name="assert_test",
        module="测试",
        steps=[
            CaseStep(step_type=StepType.action, description="点击按钮", element_hint=ElementHint.click),
            CaseStep(step_type=StepType.assert_, description="窗口存在", element_hint=ElementHint.assert_window),
        ],
    )
    suite_cases = _build_suite_cases(suite)
    assert len(suite_cases) == 1
    assert len(suite_cases[0].assert_steps) == 1


def test_generate_yaml_end_to_end():
    from src.at.generator.yaml_generator import generate_yaml

    out = "/tmp/test_at_gen_yaml"
    _write_temp(CASES_YAML, "/tmp/test_at_gen_cases.yaml")
    _write_temp(MAPPINGS_YAML, "/tmp/test_at_gen_mappings.yaml")

    generate_yaml(cases_path="/tmp/test_at_gen_cases.yaml", mappings_path="/tmp/test_at_gen_mappings.yaml", output_dir=out, app_name="test-app")

    elems = yaml.safe_load(open(f"{out}/elements.yaml", encoding="utf-8"))
    assert "play_btn" in elems["elements"]
    assert "theme_btn" in elems["elements"]

    import os

    assert os.path.isdir(f"{out}/菜单")
    assert os.path.isdir(f"{out}/主题")
    assert not os.path.exists(f"{out}/视觉")

    suite_path = f"{out}/菜单/suite.suite.yaml"
    assert os.path.isfile(suite_path)
    suite = yaml.safe_load(open(suite_path, encoding="utf-8"))
    assert suite["setup"][0]["action"] == "session_start"
    assert suite["setup"][0]["command"] == "test-app"
    assert suite["teardown"][0]["action"] == "session_stop"
    assert len(suite["suites"]) >= 1


def test_generate_yaml_empty_cases():
    from src.at.generator.yaml_generator import generate_yaml

    _write_temp({}, "/tmp/test_at_gen_empty.yaml")
    _write_temp(MAPPINGS_YAML, "/tmp/test_at_gen_mappings2.yaml")
    generate_yaml(cases_path="/tmp/test_at_gen_empty.yaml", mappings_path="/tmp/test_at_gen_mappings2.yaml", output_dir="/tmp/test_at_gen_empty_out", app_name="test-app")
    assert not Path("/tmp/test_at_gen_empty_out").exists() or not list(Path("/tmp/test_at_gen_empty_out").iterdir())


def test_step_to_action_keyboard_type():
    from src.at.generator.yaml_generator import _step_to_action
    from src.at.parser.models import CaseStep, ElementHint, StepType

    step = CaseStep(step_type=StepType.action, description="输入文字", action="keyboard_type", text="hello world")
    action = _step_to_action(step)
    assert action.action == "keyboard_type"
    assert action.text == "hello world"


def test_step_to_action_scroll():
    from src.at.generator.yaml_generator import _step_to_action
    from src.at.parser.models import CaseStep, ElementHint, StepType

    step = CaseStep(step_type=StepType.action, description="向下滚动", action="mouse_scroll", value=-3)
    action = _step_to_action(step)
    assert action.action == "mouse_scroll"
    assert action.value == -3


def test_step_to_action_assert_window():
    from src.at.generator.yaml_generator import _step_to_action
    from src.at.parser.models import CaseStep, ElementHint, StepType

    step = CaseStep(step_type=StepType.assert_, description="窗口存在", action="assert_window", selector={"name_pattern": "终端.*"})
    action = _step_to_action(step)
    assert action.action == "assert_window"
    assert action.name_pattern == "终端.*"


def test_step_to_action_dtk_context_menu():
    from src.at.generator.yaml_generator import _step_to_action
    from src.at.parser.models import CaseStep, ElementHint, StepType

    step = CaseStep(step_type=StepType.navigate, description="右键菜单", action="dtk_context_menu", menu_path=["复制", "粘贴"])
    action = _step_to_action(step)
    assert action.action == "dtk_context_menu"
    assert action.items == ["复制", "粘贴"]


def test_step_to_action_dialog_note():
    from src.at.generator.yaml_generator import _step_to_action
    from src.at.parser.models import CaseStep, ElementHint, StepType

    step = CaseStep(step_type=StepType.action, description="在对话框中勾选背景模糊", element_hint=ElementHint.dialog, action="element_action", element_ref="blur_checkbox", selector={"name": "背景模糊", "role": "check box"})
    action = _step_to_action(step)
    assert action.action == "element_action"
    assert action.ref == "blur_checkbox"
    assert action.do == "click"
    assert action.note == "在对话框中勾选背景模糊"


def test_step_to_action_needs_accessible_name():
    from src.at.generator.yaml_generator import _step_to_action
    from src.at.parser.models import CaseStep, ElementHint, StepType

    step = CaseStep(
        step_type=StepType.action,
        description="点击自定义控件",
        element_hint=ElementHint.click,
        needs_accessible_name=True,
        accessible_name_suggestion="custom_widget_settings",
    )
    action = _step_to_action(step)
    assert action.action == "element_action"
    assert action.do == "click"


def test_generate_yaml_app_name_in_command():
    from src.at.generator.yaml_generator import generate_yaml

    out = "/tmp/test_at_gen_appname"
    _write_temp(CASES_YAML, "/tmp/test_at_appname_cases.yaml")
    generate_yaml(cases_path="/tmp/test_at_appname_cases.yaml", mappings_path="", output_dir=out, app_name="deepin-terminal")
    suite_path = f"{out}/菜单/suite.suite.yaml"
    assert os.path.isfile(suite_path)
    suite = yaml.safe_load(open(suite_path, encoding="utf-8"))
    assert suite["setup"][0]["command"] == "deepin-terminal"


def test_generate_yaml_module_name_safe():
    from src.at.generator.yaml_generator import generate_yaml

    cases_with_slash = {
        "metadata": {"generated_at": "2026-01-01", "source": "test"},
        "suites": [
            {
                "id": "slash_001",
                "name": "test_slash",
                "module": "文件/编辑",
                "status": "active",
                "steps": [
                    {"step_type": "action", "description": "test", "element_hint": "click"},
                ],
            },
        ],
    }
    _write_temp(cases_with_slash, "/tmp/test_at_slash_cases.yaml")
    out = "/tmp/test_at_gen_slash"
    generate_yaml(cases_path="/tmp/test_at_slash_cases.yaml", mappings_path="", output_dir=out, app_name="test-app")
    assert os.path.isdir(f"{out}/文件_编辑")


from pathlib import Path


def test_valid_actions_matches_handlers():
    from src.at.generator.yaml_generator import _VALID_ACTIONS
    from src.at.executor.handlers import HANDLERS

    assert _VALID_ACTIONS == frozenset(HANDLERS.keys())


def test_step_to_action_invalid_action_returns_none():
    from src.at.generator.yaml_generator import _step_to_action
    from src.at.parser.models import CaseStep, StepType

    step = CaseStep(step_type=StepType.action, description="bad", action="nonexistent_action")
    result = _step_to_action(step)
    assert result is None


def test_build_suite_cases_session_start_breaks_context():
    from src.at.generator.yaml_generator import _build_suite_cases
    from src.at.parser.models import CaseSuite, CaseStep, StepType

    suite = CaseSuite(
        id="ctx_001",
        name="context_test",
        module="测试",
        steps=[
            CaseStep(step_type=StepType.action, description="打开应用", action="session_start", text="test-app"),
            CaseStep(step_type=StepType.action, description="点击按钮", action="element_action", element_ref="btn1", selector={"name": "OK", "role": "push button"}),
            CaseStep(step_type=StepType.action, description="重启", action="session_start", text="test-app"),
            CaseStep(step_type=StepType.action, description="再次点击", action="element_action", element_ref="btn2", selector={"name": "Cancel", "role": "push button"}),
        ],
    )
    suite_cases = _build_suite_cases(suite)
    assert len(suite_cases) == 2
    assert len(suite_cases[0].steps) == 1
    assert len(suite_cases[1].steps) == 1


def test_build_suite_cases_accumulates_steps():
    from src.at.generator.yaml_generator import _build_suite_cases
    from src.at.parser.models import CaseSuite, CaseStep, StepType

    suite = CaseSuite(
        id="acc_001",
        name="accumulate_test",
        module="测试",
        steps=[
            CaseStep(step_type=StepType.action, description="第一步", action="element_action", element_ref="r1", selector={"name": "A", "role": "push button"}),
            CaseStep(step_type=StepType.action, description="第二步", action="element_action", element_ref="r2", selector={"name": "B", "role": "push button"}),
            CaseStep(step_type=StepType.assert_, description="断言", action="assert_element", element_ref="r3", selector={"name": "C", "role": "label"}),
        ],
    )
    suite_cases = _build_suite_cases(suite)
    assert len(suite_cases) == 1
    assert len(suite_cases[0].steps) == 2
    assert len(suite_cases[0].assert_steps) == 1


def test_extract_elements_from_at_tree(tmp_path):
    from src.at.generator.yaml_generator import _extract_elements_from_at_tree

    at_tree_file = tmp_path / "at-tree.yaml"
    at_tree_file.write_text(
        "tree:\n"
        "  - id: n1\n"
        "    role: push button\n"
        "    name: OK\n"
        "    children:\n"
        "      - id: n2\n"
        "        role: label\n"
        "        name: label1\n"
        "  - id: n3\n"
        "    role: menu item\n"
        "    name: 帮助\n",
        encoding="utf-8",
    )
    elements = _extract_elements_from_at_tree(str(at_tree_file))
    assert "n1" in elements
    assert elements["n1"]["name"] == "OK"
    assert elements["n1"]["role"] == "push button"
    assert "n2" in elements
    assert "n3" in elements
    assert elements["n3"]["name"] == "帮助"


def test_extract_elements_from_at_tree_empty():
    from src.at.generator.yaml_generator import _extract_elements_from_at_tree

    assert _extract_elements_from_at_tree("/nonexistent/path") == {}
