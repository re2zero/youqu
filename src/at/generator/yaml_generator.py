# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

import yaml
from pydantic import ValidationError

from src.at.generator.mapping_rules import STEP_TYPE_MAP
from src.at.parser.models import (
    CaseSuite,
    CaseStep,
    CasesDoc,
    ElementHint,
    ElementMappingsDoc,
    MappingEntry,
    MappingSelector,
    StepType,
    SuiteActionStep,
    SuiteCase,
    SuiteConfig,
)

_SKIP_HINTS = {ElementHint.visual_check, ElementHint.physical_device, ElementHint.cross_device}


def _load_yaml(path: str) -> dict | list | None:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _extract_elements(mappings: ElementMappingsDoc) -> dict[str, dict]:
    elements: dict[str, dict] = {}
    for m in mappings.mappings:
        if m.status != "mapped" or not m.element_ref or not m.selector:
            continue
        sel = m.selector.model_dump(mode="json", exclude_none=True)
        elements[m.element_ref] = sel
    return elements


def _write_yaml(data: dict | list, path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    try:
        import yaml as pyyaml

        with open(path, "w", encoding="utf-8") as f:
            pyyaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    except ImportError:
        import json

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


def _step_to_action(step: CaseStep, mapping: MappingEntry | None) -> SuiteActionStep:
    action_name = STEP_TYPE_MAP.get(step.step_type.value, "element_action")

    if step.element_hint == ElementHint.main_menu_comb and step.menu_path:
        return SuiteActionStep(action="main_menu_comb", items=step.menu_path)

    if step.element_hint == ElementHint.context_menu_comb and step.menu_path:
        return SuiteActionStep(action="context_menu_comb", items=step.menu_path)

    if step.element_hint == ElementHint.titlebar:
        selector = mapping.selector.model_dump(mode="json", exclude_none=True) if mapping and mapping.selector else None
        return SuiteActionStep(action="element_action", ref=mapping.element_ref if mapping else None, selector=selector, do="click")

    if step.element_hint == ElementHint.keyboard_shortcut:
        return SuiteActionStep(action="keyboard_press", key=step.description)

    if step.element_hint == ElementHint.scroll:
        return SuiteActionStep(action="mouse_scroll", amount=-3)

    if step.element_hint == ElementHint.dbus_call:
        return SuiteActionStep(action="dbus_call", command=step.description)

    if step.element_hint == ElementHint.screenshot:
        return SuiteActionStep(action="screenshot_save", path=step.description)

    if step.element_hint == ElementHint.vlm_assert:
        return SuiteActionStep(action="assert_vlm", prompt=step.description)

    if step.element_hint == ElementHint.drag_drop:
        return SuiteActionStep(action="element_action", ref=mapping.element_ref if mapping else None, do="drag")

    if step.element_hint == ElementHint.hover:
        selector = mapping.selector.model_dump(mode="json", exclude_none=True) if mapping and mapping.selector else None
        return SuiteActionStep(action="element_action", ref=mapping.element_ref if mapping else None, selector=selector, do="hover")

    if step.element_hint == ElementHint.input_text:
        return SuiteActionStep(action="keyboard_type", text=step.description)

    if step.element_hint == ElementHint.assert_window:
        return SuiteActionStep(action="assert_window_exists", selector={"role": "window", "name_pattern": step.description})

    if step.element_hint == ElementHint.assert_element:
        selector = mapping.selector.model_dump(mode="json", exclude_none=True) if mapping and mapping.selector else None
        return SuiteActionStep(action="assert_element_exists", ref=mapping.element_ref if mapping else None, selector=selector)

    if step.element_hint == ElementHint.assert_window_count:
        return SuiteActionStep(action="assert_window_count", app="", expected=1)

    if step.element_hint == ElementHint.assert_not_exists:
        selector = mapping.selector.model_dump(mode="json", exclude_none=True) if mapping and mapping.selector else None
        return SuiteActionStep(action="assert_element_not_exists", ref=mapping.element_ref if mapping else None, selector=selector)

    selector = mapping.selector.model_dump(mode="json", exclude_none=True) if mapping and mapping.selector else None
    return SuiteActionStep(action=action_name, ref=mapping.element_ref if mapping else None, selector=selector, do="click")


def _build_suite_cases(
    suite: CaseSuite,
    mappings_by_case: dict[str, list[MappingEntry]],
) -> list[SuiteCase]:
    suite_mappings = mappings_by_case.get(suite.id, [])
    suite_cases: list[SuiteCase] = []

    for i, step in enumerate(suite.steps):
        mapping = None
        for m in suite_mappings:
            if m.step_index == i:
                mapping = m
                break

        if step.element_hint in _SKIP_HINTS:
            continue

        if step.step_type == StepType.assert_:
            assert_step = _step_to_action(step, mapping)
            if suite_cases:
                suite_cases[-1].assert_steps.append(assert_step)
            continue

        action_step = _step_to_action(step, mapping)
        suite_case = SuiteCase(
            id=f"{suite.id}_s{i}",
            steps=[action_step],
        )
        suite_cases.append(suite_case)

    return suite_cases


def generate_yaml(cases_path: str, mappings_path: str, output_dir: str) -> None:
    cases_data = _load_yaml(cases_path)
    mappings_data = _load_yaml(mappings_path)

    if not cases_data:
        print(f"Error: {cases_path} is empty or invalid")
        return
    if not mappings_data:
        print(f"Error: {mappings_path} is empty or invalid")
        return

    cases_doc = CasesDoc.model_validate(cases_data)
    mappings_doc = ElementMappingsDoc.model_validate(mappings_data)

    mappings_by_case: dict[str, list[MappingEntry]] = defaultdict(list)
    for m in mappings_doc.mappings:
        if m.case_id:
            mappings_by_case[m.case_id].append(m)

    elements = _extract_elements(mappings_doc)
    elements_path = str(Path(output_dir) / "elements.yaml")
    _write_yaml({"elements": elements}, elements_path)
    print(f"Wrote {elements_path} ({len(elements)} elements)")

    suites_by_module: dict[str, list[CaseSuite]] = defaultdict(list)
    for suite in cases_doc.suites:
        if suite.status == "skipped":
            continue
        suites_by_module[suite.module].append(suite)

    for module, module_suites in suites_by_module.items():
        module_dir = Path(output_dir) / module
        module_dir.mkdir(parents=True, exist_ok=True)

        all_suite_cases: list[SuiteCase] = []
        app_name = ""

        for suite in module_suites:
            suite_cases = _build_suite_cases(suite, mappings_by_case)
            all_suite_cases.extend(suite_cases)
            if suite.id and not app_name:
                app_name = suite.name.split("_")[0] if "_" in suite.id else ""

            case_steps: list[dict] = []
            case_assert_steps: list[dict] = []
            for sc in suite_cases:
                for s in sc.steps:
                    case_steps.append(s.model_dump(mode="json", exclude_none=True))
                for s in sc.assert_steps:
                    case_assert_steps.append(s.model_dump(mode="json", exclude_none=True))

            if not case_steps and not case_assert_steps:
                continue

            case_yaml = {"app": app_name, "module": module}
            if case_steps:
                case_yaml["steps"] = case_steps
            if case_assert_steps:
                case_yaml["assert_steps"] = case_assert_steps
            case_path = module_dir / f"test_{suite.id}.yaml"
            _write_yaml(case_yaml, str(case_path))

        if not all_suite_cases:
            continue

        suite_config = SuiteConfig(
            name=f"{module}_suite",
            app=app_name,
            module=module,
            setup=[SuiteActionStep(action="session_start", command=app_name, wait=3000)],
            suites=all_suite_cases,
            teardown=[SuiteActionStep(action="session_stop")],
        )

        suite_path = module_dir / f"{module}_suite.suite.yaml"
        _write_yaml(suite_config.model_dump(mode="json", exclude_none=True, by_alias=True), str(suite_path))
        print(f"Wrote {suite_path} ({len(all_suite_cases)} suite cases)")
