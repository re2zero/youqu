# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only

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
    action = _step_to_action(step, None)
    assert action.action == "dtk_main_menu"
    assert action.items == ["文件", "新建窗口"]


def test_step_to_action_element_click():
    from src.at.generator.yaml_generator import _step_to_action
    from src.at.parser.models import CaseStep, ElementHint, MappingEntry, MappingSelector, StepType

    step = CaseStep(step_type=StepType.action, description="点击播放")
    mapping = MappingEntry(case_id="x", step_index=0, description="d", step_type="action", element_ref="play_btn", selector=MappingSelector(name="播放", role="push button"))
    action = _step_to_action(step, mapping)
    assert action.action == "element_action"
    assert action.ref == "play_btn"
    assert action.do == "click"


def test_step_to_action_keyboard():
    from src.at.generator.yaml_generator import _step_to_action
    from src.at.parser.models import CaseStep, ElementHint, StepType

    step = CaseStep(step_type=StepType.action, description="Ctrl+S", element_hint=ElementHint.keyboard_shortcut)
    action = _step_to_action(step, None)
    assert action.action == "keyboard_press"
    assert action.key == "Ctrl+S"


def test_step_to_action_assert_element():
    from src.at.generator.yaml_generator import _step_to_action
    from src.at.parser.models import CaseStep, ElementHint, MappingEntry, MappingSelector, StepType

    step = CaseStep(step_type=StepType.assert_, description="按钮存在", element_hint=ElementHint.assert_element)
    mapping = MappingEntry(case_id="x", step_index=0, description="d", step_type="assert", element_ref="btn1", selector=MappingSelector(name="OK", role="push button"))
    action = _step_to_action(step, mapping)
    assert action.action == "assert_element_exists"
    assert action.ref == "btn1"


def test_step_to_action_titlebar():
    from src.at.generator.yaml_generator import _step_to_action
    from src.at.parser.models import CaseStep, ElementHint, MappingEntry, MappingSelector, StepType

    step = CaseStep(step_type=StepType.action, description="最大化", element_hint=ElementHint.titlebar)
    mapping = MappingEntry(case_id="x", step_index=0, description="d", step_type="action", element_ref="titlebar", selector=MappingSelector(name="标题栏", role="title_bar"))
    action = _step_to_action(step, mapping)
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
    suite_cases = _build_suite_cases(suite, {})
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
    suite_cases = _build_suite_cases(suite, {})
    assert len(suite_cases) == 1
    assert len(suite_cases[0].assert_steps) == 1


def test_generate_yaml_end_to_end():
    from src.at.generator.yaml_generator import generate_yaml

    out = "/tmp/test_at_gen_yaml"
    _write_temp(CASES_YAML, "/tmp/test_at_gen_cases.yaml")
    _write_temp(MAPPINGS_YAML, "/tmp/test_at_gen_mappings.yaml")

    generate_yaml(cases_path="/tmp/test_at_gen_cases.yaml", mappings_path="/tmp/test_at_gen_mappings.yaml", output_dir=out)

    elems = yaml.safe_load(open(f"{out}/elements.yaml", encoding="utf-8"))
    assert "play_btn" in elems["elements"]
    assert "theme_btn" in elems["elements"]

    import os

    assert os.path.isdir(f"{out}/菜单")
    assert os.path.isdir(f"{out}/主题")
    assert not os.path.exists(f"{out}/视觉")

    suite_path = f"{out}/菜单/菜单_suite.suite.yaml"
    assert os.path.isfile(suite_path)
    suite = yaml.safe_load(open(suite_path, encoding="utf-8"))
    assert suite["setup"][0]["action"] == "session_start"
    assert suite["teardown"][0]["action"] == "session_stop"
    assert len(suite["suites"]) >= 1


def test_generate_yaml_empty_cases():
    from src.at.generator.yaml_generator import generate_yaml

    _write_temp({}, "/tmp/test_at_gen_empty.yaml")
    _write_temp(MAPPINGS_YAML, "/tmp/test_at_gen_mappings2.yaml")
    generate_yaml(cases_path="/tmp/test_at_gen_empty.yaml", mappings_path="/tmp/test_at_gen_mappings2.yaml", output_dir="/tmp/test_at_gen_empty_out")
    assert not Path("/tmp/test_at_gen_empty_out").exists() or not list(Path("/tmp/test_at_gen_empty_out").iterdir())


from pathlib import Path
