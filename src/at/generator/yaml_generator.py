# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import yaml

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

try:
    from src.at.executor.handlers import HANDLERS as _EXEC_HANDLERS
    _VALID_ACTIONS = frozenset(_EXEC_HANDLERS.keys())
except ImportError:
    _VALID_ACTIONS = frozenset({
        "session_start", "session_stop",
        "keyboard_press", "keyboard_hot_key", "keyboard_type", "keyboard_type_text",
        "mouse_click", "mouse_right_click", "mouse_double_click",
        "mouse_scroll", "mouse_drag",
        "element_action", "element_set_value",
        "dtk_main_menu", "dtk_context_menu",
        "dbus_call", "dbus_get_property",
        "wait", "screenshot",
        "assert_element", "assert_not_exists", "assert_window",
        "assert_window_count", "assert_process_running", "assert_process_not_running",
        "assert_file_exists", "assert_file_not_exists",
        "assert_image_exists", "assert_image_not_exists",
        "assert_ocr_exists", "assert_ocr_not_exists",
    })


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


def _extract_elements_from_cases(cases_doc: CasesDoc) -> dict[str, dict]:
    elements: dict[str, dict] = {}
    for suite in cases_doc.suites:
        for step in suite.steps:
            if step.element_ref and step.selector:
                elements[step.element_ref] = step.selector
            elif step.selector and not step.element_ref:
                # v2: selector-only steps — register by name as synthetic ref
                sel = step.selector
                name = sel.get("name", "") if isinstance(sel, dict) else ""
                if name:
                    ref_key = name
                    if ref_key not in elements:
                        elements[ref_key] = sel
    return elements


def _extract_elements_from_at_tree(at_tree_path: str) -> dict[str, dict]:
    try:
        tree_data = _load_yaml(at_tree_path)
    except (FileNotFoundError, OSError):
        return {}
    if not tree_data or not isinstance(tree_data, dict):
        return {}

    elements: dict[str, dict] = {}

    def _walk(nodes: list[dict]) -> None:
        for node in nodes:
            if not isinstance(node, dict):
                continue
            nid = node.get("id", "")
            if nid:
                name = node.get("name", "")
                role = node.get("role", "")
                if name or role:
                    elements[nid] = {"name": name, "role": role}
            children = node.get("children", [])
            if children:
                _walk(children)

    tree_nodes = tree_data.get("tree", [])
    if isinstance(tree_nodes, list):
        _walk(tree_nodes)

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


def _normalize_key(key: str | None) -> str | None:
    if not key:
        return None
    return key.lower().strip()


def _step_to_action_fallback(step: CaseStep) -> SuiteActionStep:
    action_name = STEP_TYPE_MAP.get(step.step_type.value, "element_action")

    if step.element_hint == ElementHint.dtk_main_menu and step.items:
        return SuiteActionStep(action="dtk_main_menu", items=step.items)

    if step.element_hint == ElementHint.dtk_context_menu and step.items:
        return SuiteActionStep(
            action="dtk_context_menu",
            items=step.items,
        )

    if step.element_hint == ElementHint.titlebar:
        return SuiteActionStep(action="element_action", do="click")

    if step.element_hint == ElementHint.keyboard_shortcut:
        return SuiteActionStep(action="keyboard_press", key=step.description)

    if step.element_hint == ElementHint.scroll:
        return SuiteActionStep(action="mouse_scroll", value=-3)

    if step.element_hint == ElementHint.dbus_call:
        return SuiteActionStep(action="dbus_call", value=step.value)

    if step.element_hint == ElementHint.screenshot:
        return SuiteActionStep(action="screenshot")

    if step.element_hint == ElementHint.drag_drop:
        return SuiteActionStep(action="element_action", do="drag")

    if step.element_hint == ElementHint.hover:
        return SuiteActionStep(action="element_action", do="hover")

    if step.element_hint == ElementHint.input_text:
        return SuiteActionStep(action="keyboard_type", text=step.description)

    if step.element_hint == ElementHint.assert_window:
        name_pattern = step.selector.get("name_pattern") if step.selector else None
        return SuiteActionStep(
            action="assert_window",
            name_pattern=name_pattern,
        )

    if step.element_hint == ElementHint.assert_element:
        return SuiteActionStep(action="assert_element")

    if step.element_hint == ElementHint.assert_window_count:
        return SuiteActionStep(action="assert_window_count", expected=1)

    if step.element_hint == ElementHint.assert_not_exists:
        return SuiteActionStep(action="assert_not_exists")

    return SuiteActionStep(action=action_name, do="click")


def _step_to_action(step: CaseStep) -> SuiteActionStep | None:
    if step.action and step.action not in _VALID_ACTIONS:
        print(f"Warning: invalid action '{step.action}' in step '{step.description[:50]}', skipping")
        return None

    if step.action and step.action in _VALID_ACTIONS:
        key = _normalize_key(step.key) if step.action == "keyboard_press" else step.key

        if step.action == "dtk_main_menu":
            return SuiteActionStep(
                action="dtk_main_menu",
                items=step.items or [],
            )

        if step.action == "dtk_context_menu":
            return SuiteActionStep(
                action="dtk_context_menu",
                items=step.items or [],
                ref=step.element_ref,
                selector=step.selector,
            )

        if step.action == "keyboard_press":
            return SuiteActionStep(action="keyboard_press", key=key)

        if step.action == "keyboard_hot_key":
            return SuiteActionStep(action="keyboard_hot_key", key=step.key)

        if step.action == "keyboard_type":
            return SuiteActionStep(action="keyboard_type", text=step.text)

        if step.action == "mouse_click":
            return SuiteActionStep(
                action="mouse_click",
                ref=step.element_ref,
                selector=step.selector,
            )

        if step.action == "mouse_drag":
            return SuiteActionStep(
                action="mouse_drag",
                ref=step.element_ref,
                selector=step.selector,
            )

        if step.action == "element_action":
            do = "click"
            if step.element_hint == ElementHint.drag_drop:
                do = "drag"
            elif step.element_hint == ElementHint.hover:
                do = "hover"
            note = step.description if step.element_hint == ElementHint.dialog else None
            return SuiteActionStep(
                action="element_action",
                ref=step.element_ref,
                selector=step.selector,
                do=do,
                note=note,
            )

        if step.action == "mouse_scroll":
            scroll_val = -3
            if step.text and step.text.lstrip("-").isdigit():
                scroll_val = int(step.text)
            return SuiteActionStep(action="mouse_scroll", value=scroll_val)

        if step.action == "dbus_call":
            return SuiteActionStep(action="dbus_call", value=step.value)

        if step.action == "screenshot":
            return SuiteActionStep(action="screenshot")

        if step.action == "wait":
            return SuiteActionStep(action="wait", wait=1.0)

        if step.action == "assert_element":
            return SuiteActionStep(
                action="assert_element",
                ref=step.element_ref,
                selector=step.selector,
            )

        if step.action == "assert_not_exists":
            return SuiteActionStep(
                action="assert_not_exists",
                ref=step.element_ref,
                selector=step.selector,
            )

        if step.action == "assert_window":
            name_pattern = step.selector.get("name_pattern") if step.selector else None
            return SuiteActionStep(
                action="assert_window",
                name_pattern=name_pattern,
            )

        if step.action == "assert_window_count":
            expected = int(step.text) if step.text and step.text.isdigit() else 1
            return SuiteActionStep(action="assert_window_count", expected=expected)

        if step.action == "session_start":
            return SuiteActionStep(action="session_start", command=step.text or "")

        if step.action == "session_stop":
            return SuiteActionStep(action="session_stop")

        if step.action == "keyboard_type_text":
            return SuiteActionStep(action="keyboard_type_text", text=step.text)

        if step.action == "mouse_right_click":
            return SuiteActionStep(
                action="mouse_right_click",
                ref=step.element_ref,
                selector=step.selector,
            )

        if step.action == "mouse_double_click":
            return SuiteActionStep(
                action="mouse_double_click",
                ref=step.element_ref,
                selector=step.selector,
            )

        if step.action == "element_set_value":
            return SuiteActionStep(
                action="element_set_value",
                ref=step.element_ref,
                selector=step.selector,
                text=step.text,
            )

        if step.action == "dbus_get_property":
            return SuiteActionStep(action="dbus_get_property", value=step.value)

        if step.action == "assert_process_running":
            return SuiteActionStep(action="assert_process_running", app=step.text)

        if step.action == "assert_process_not_running":
            return SuiteActionStep(action="assert_process_not_running", app=step.text)

        if step.action == "assert_file_exists":
            return SuiteActionStep(action="assert_file_exists", path=step.text)

        if step.action == "assert_file_not_exists":
            return SuiteActionStep(action="assert_file_not_exists", path=step.text)

        if step.action == "assert_image_exists":
            return SuiteActionStep(action="assert_image_exists", path=step.text)

        if step.action == "assert_image_not_exists":
            return SuiteActionStep(action="assert_image_not_exists", path=step.text)

        if step.action == "assert_ocr_exists":
            return SuiteActionStep(action="assert_ocr_exists", value=step.text)

        if step.action == "assert_ocr_not_exists":
            return SuiteActionStep(action="assert_ocr_not_exists", value=step.text)

    return _step_to_action_fallback(step)


def _build_suite_cases(suite: CaseSuite) -> list[SuiteCase]:
    suite_cases: list[SuiteCase] = []
    current: SuiteCase | None = None
    case_counter = 0

    for i, step in enumerate(suite.steps):
        if step.element_hint in _SKIP_HINTS:
            continue

        action_step = _step_to_action(step)
        if action_step is None:
            continue

        if action_step.action in ("session_start", "session_stop"):
            if action_step.action == "session_start":
                if current and (current.steps or current.assert_steps):
                    suite_cases.append(current)
                case_counter += 1
                current = SuiteCase(
                    id=f"{suite.id}_s{case_counter}",
                    name=step.description[:60],
                    steps=[],
                )
            continue

        if step.step_type == StepType.assert_:
            if current:
                current.assert_steps.append(action_step)
            else:
                case_counter += 1
                current = SuiteCase(
                    id=f"{suite.id}_s{case_counter}",
                    name=step.description[:60],
                    steps=[],
                    assert_steps=[action_step],
                )
            continue

        if current is None:
            case_counter += 1
            current = SuiteCase(
                id=f"{suite.id}_s{case_counter}",
                name=step.description[:60],
                steps=[action_step],
            )
        else:
            current.steps.append(action_step)

    if current and (current.steps or current.assert_steps):
        suite_cases.append(current)

    return suite_cases


def _resolve_app_name(app_name: str, at_tree_path: str) -> str:
    if app_name:
        return app_name
    if at_tree_path:
        tree_path = Path(at_tree_path)
        if tree_path.exists():
            try:
                tree_data = _load_yaml(at_tree_path)
                if tree_data and isinstance(tree_data, dict):
                    metadata = tree_data.get("metadata", {})
                    if isinstance(metadata, dict):
                        app = metadata.get("app", "")
                        if app:
                            return app
            except Exception:
                pass
    raise ValueError(
        "Cannot determine app name. Use --app <name> or --at-tree <path> with metadata.app"
    )


def _write_app_optimization(cases_doc: CasesDoc, output_dir: str) -> None:
    entries: list[dict] = []
    for suite in cases_doc.suites:
        for i, step in enumerate(suite.steps):
            if step.needs_accessible_name:
                entries.append({
                    "suite_id": suite.id,
                    "step_index": i,
                    "description": step.description,
                    "suggestion": step.accessible_name_suggestion or "",
                    "element_hint": step.element_hint.value if step.element_hint else "",
                })

    if not entries:
        return

    lines = [
        "# App Optimization Recommendations",
        "",
        "The following UI elements need `setAccessibleName()` for AT-SPI automation:",
        "",
        "| Suite | Step | Description | Suggested Name | Hint |",
        "|--------|------|-------------|----------------|------|",
    ]
    for e in entries:
        lines.append(
            "| {} | {} | {} | {} | {} |".format(
                e["suite_id"], e["step_index"], e["description"], e["suggestion"], e["element_hint"]
            )
        )
    lines.append("")

    out_path = Path(output_dir) / "app-optimization.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out_path} ({len(entries)} entries)")


def generate_yaml(
    cases_path: str,
    output_dir: str,
    mappings_path: str = "",
    app_name: str = "",
    at_tree_path: str = "",
) -> None:
    cases_data = _load_yaml(cases_path)
    if not cases_data:
        print(f"Error: {cases_path} is empty or invalid")
        return

    cases_doc = CasesDoc.model_validate(cases_data)

    elements: dict[str, dict] = _extract_elements_from_cases(cases_doc)

    if at_tree_path:
        tree_elements = _extract_elements_from_at_tree(at_tree_path)
        for ref, sel in tree_elements.items():
            if ref not in elements:
                elements[ref] = sel

    if mappings_path:
        mappings_data = _load_yaml(mappings_path)
        if mappings_data:
            mappings_doc = ElementMappingsDoc.model_validate(mappings_data)
            elements.update(_extract_elements(mappings_doc))

    elements_path = str(Path(output_dir) / "elements.yaml")
    _write_yaml({"elements": elements}, elements_path)
    print(f"Wrote {elements_path} ({len(elements)} elements)")

    resolved_app = _resolve_app_name(app_name, at_tree_path)

    _write_app_optimization(cases_doc, output_dir)

    suites_by_module: dict[str, list[CaseSuite]] = defaultdict(list)
    for suite in cases_doc.suites:
        if suite.status == "skipped":
            continue
        safe_module = suite.module.replace("/", "_")
        suites_by_module[safe_module].append(suite)

    for module, module_suites in suites_by_module.items():
        module_dir = Path(output_dir) / module
        module_dir.mkdir(parents=True, exist_ok=True)

        all_suite_cases: list[SuiteCase] = []

        for suite in module_suites:
            suite_cases = _build_suite_cases(suite)
            all_suite_cases.extend(suite_cases)

            case_steps: list[dict] = []
            case_assert_steps: list[dict] = []
            for sc in suite_cases:
                for s in sc.steps:
                    case_steps.append(s.model_dump(mode="json", exclude_none=True))
                for s in sc.assert_steps:
                    case_assert_steps.append(s.model_dump(mode="json", exclude_none=True))

            if not case_steps and not case_assert_steps:
                continue

            case_yaml = {"app": resolved_app, "module": module}
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
            app=resolved_app,
            module=module,
            setup=[SuiteActionStep(action="session_start", command=resolved_app, wait=3.0)],
            specs=all_suite_cases,
            teardown=[SuiteActionStep(action="session_stop")],
        )

        suite_path = module_dir / "suite.suite.yaml"
        _write_yaml(suite_config.model_dump(mode="json", exclude_none=True, by_alias=True), str(suite_path))
        print(f"Wrote {suite_path} ({len(all_suite_cases)} suite cases)")
