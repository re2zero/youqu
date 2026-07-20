# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only

import logging
import re
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_NOISE_NAME_RE = re.compile(r"^(Form_|qt_\w+$|\d+$|DMainWindow|DTitlebar)")

_INTERACTIVE_ROLES = frozenset(
    {
        "push button",
        "check box",
        "radio button",
        "toggle button",
        "combo box",
        "entry",
        "text",
        "spin button",
        "slider",
        "list item",
        "menu item",
        "menu",
        "tab",
        "tree item",
        "link",
        "button",
    }
)

_COMMENT_FORMAT_RE = re.compile(r"GUI位置:\s*.+\|\s*功能:\s*.+")

_VALID_ACTIONS = frozenset(
    {
        "mouse_click",
        "mouse_double_click",
        "mouse_right_click",
        "mouse_scroll",
        "mouse_drag",
        "keyboard_type",
        "keyboard_type_text",
        "keyboard_press",
        "keyboard_hot_key",
        "element_action",
        "element_set_value",
        "wait",
        "assert_element",
        "assert_file_exists",
        "assert_file_not_exists",
        "assert_image_exists",
        "assert_image_not_exists",
        "assert_not_exists",
        "assert_ocr_exists",
        "assert_ocr_not_exists",
        "assert_process_running",
        "assert_process_not_running",
        "assert_window",
        "assert_window_count",
        "dbus_call",
        "dbus_get_property",
        "screenshot",
        "dtk_main_menu",
        "dtk_context_menu",
        "session_start",
        "session_stop",
    }
)


def _load_yaml(path: str) -> dict | None:
    p = Path(path)
    if not p.exists():
        return None
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _flatten_tree(
    nodes: list[dict], parent_path: list[str] | None = None
) -> list[tuple[dict, list[str]]]:
    if parent_path is None:
        parent_path = []
    result = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        nid = node.get("id", "")
        path = parent_path + [nid] if nid else parent_path
        result.append((node, path))
        children = node.get("children", [])
        if children:
            result.extend(_flatten_tree(children, path))
    return result


def validate_gate1(at_tree_annotated_path: str, element_gaps_path: str = "") -> dict:
    report = {
        "gate": 1,
        "name": "Denoising & Annotation Gate",
        "errors": [],
        "warnings": [],
        "passed": True,
    }

    tree_data = _load_yaml(at_tree_annotated_path)
    if not tree_data:
        report["errors"].append(f"File not found or empty: {at_tree_annotated_path}")
        report["passed"] = False
        return report

    tree_nodes = tree_data.get("tree", [])
    if not isinstance(tree_nodes, list):
        report["errors"].append("at-tree-annotated.yaml missing 'tree' key")
        report["passed"] = False
        return report

    all_nodes = _flatten_tree(tree_nodes)

    for node, path in all_nodes:
        nid = node.get("id", "?")
        name = node.get("name", "")
        role = node.get("role", "")
        classification = node.get("classification", "")
        comment = node.get("comment", "")
        annotation_status = node.get("annotation_status", "")
        children = node.get("children", [])

        if _NOISE_NAME_RE.match(name) and not children:
            report["errors"].append(f"[{nid}] noise name: '{name}' (role: {role})")
            report["passed"] = False

        if not children and classification == "container" and role not in ("filler", "unknown"):
            report["warnings"].append(f"[{nid}] leaf container node: role={role} name='{name}'")

        if classification == "interactive":
            if not comment:
                report["errors"].append(
                    f"[{nid}] interactive element missing comment: name='{name}' role={role}"
                )
                report["passed"] = False
            elif not _COMMENT_FORMAT_RE.match(comment):
                report["errors"].append(
                    f"[{nid}] comment format invalid: '{comment}' (expected 'GUI位置: ... | 功能: ...')"
                )
                report["passed"] = False

            if not annotation_status:
                report["errors"].append(f"[{nid}] interactive element missing annotation_status")
                report["passed"] = False
            elif annotation_status not in ("draft", "reviewed"):
                report["errors"].append(f"[{nid}] invalid annotation_status: '{annotation_status}'")
                report["passed"] = False

    if element_gaps_path:
        gaps = _load_yaml(element_gaps_path)
        if not gaps:
            report["warnings"].append(f"element_gaps.yaml not found: {element_gaps_path}")
        else:
            summary = gaps.get("summary", {})
            missing = summary.get("missing_accessible_id", 0)
            if missing > 0:
                report["warnings"].append(
                    f"{missing} interactive elements missing accessible_id (see element_gaps.yaml)"
                )

    return report


def validate_gate2(suite_cases_path: str, at_tree_annotated_path: str = "") -> dict:
    report = {
        "gate": 2,
        "name": "Normalization & Suite Annotation Gate",
        "errors": [],
        "warnings": [],
        "passed": True,
    }

    cases_data = _load_yaml(suite_cases_path)
    if not cases_data:
        report["errors"].append(f"File not found or empty: {suite_cases_path}")
        report["passed"] = False
        return report

    cases = cases_data.get("cases", [])
    if not cases:
        report["errors"].append("suite-cases.yaml has no cases")
        report["passed"] = False
        return report

    tree_names: set[str] | None = None
    if at_tree_annotated_path:
        tree_data = _load_yaml(at_tree_annotated_path)
        if tree_data:
            tree_nodes = tree_data.get("tree", [])
            tree_names = set()
            for node, _ in _flatten_tree(tree_nodes):
                n = node.get("name", "")
                if n:
                    tree_names.add(n)
                on = node.get("object_name", "")
                if on:
                    tree_names.add(on)

    required_annotation_fields = ("测试界面", "测试功能", "前置条件", "AT元素引用")

    for suite in cases:
        sid = suite.get("id", "?")
        sname = suite.get("name", "")
        status = suite.get("status", "active")

        if status == "non_gui":
            continue

        annotation = suite.get("annotation") or suite.get("suite_annotation") or {}
        for field in required_annotation_fields:
            if not annotation.get(field):
                report["errors"].append(f"[{sid}] missing suite annotation field: {field}")
                report["passed"] = False

        at_refs = annotation.get("AT元素引用", "")
        if at_refs and tree_names is not None:
            for ref in [r.strip() for r in at_refs.split(",")]:
                if ref and ref not in tree_names:
                    report["errors"].append(
                        f"[{sid}] AT元素引用 '{ref}' not found in annotated tree"
                    )
                    report["passed"] = False

        steps = suite.get("steps", [])
        has_action = any(s.get("step_type") == "action" or s.get("action") for s in steps)
        has_assert = any(s.get("step_type") == "assert" or s.get("assertion") for s in steps)

        if not has_action:
            report["errors"].append(f"[{sid}] no action steps")
            report["passed"] = False
        if not has_assert:
            report["errors"].append(f"[{sid}] no assert steps")
            report["passed"] = False

    return report


def validate_gate3(cases_mapped_path: str, at_tree_annotated_path: str = "") -> dict:
    report = {
        "gate": 3,
        "name": "Mapping Completeness & Format Gate",
        "errors": [],
        "warnings": [],
        "passed": True,
    }

    raw = (
        Path(cases_mapped_path).read_text(encoding="utf-8")
        if Path(cases_mapped_path).exists()
        else ""
    )
    if not raw:
        report["errors"].append(f"File not found or empty: {cases_mapped_path}")
        report["passed"] = False
        return report

    if "格式范例" not in raw and "format_example" not in raw:
        report["errors"].append("File header missing format example (=== 格式范例 ===)")
        report["passed"] = False

    cases_data = _load_yaml(cases_mapped_path)
    if not cases_data:
        report["errors"].append("Failed to parse cases_mapped.yaml")
        report["passed"] = False
        return report

    tree_names: set[str] | None = None
    if at_tree_annotated_path:
        tree_data = _load_yaml(at_tree_annotated_path)
        if tree_data:
            tree_nodes = tree_data.get("tree", [])
            tree_names = set()
            for node, _ in _flatten_tree(tree_nodes):
                n = node.get("name", "")
                if n:
                    tree_names.add(n)
                on = node.get("object_name", "")
                if on:
                    tree_names.add(on)

    cases = cases_data.get("cases", [])

    for suite in cases:
        sid = suite.get("id", "?")
        status = suite.get("status", "active")
        if status == "non_gui":
            continue

        annotation = suite.get("annotation") or {}
        for field in ("测试界面", "测试功能"):
            if not annotation.get(field):
                report["errors"].append(f"[{sid}] missing suite annotation: {field}")
                report["passed"] = False

        steps = suite.get("steps", [])
        for i, step in enumerate(steps):
            action = step.get("action", "")
            if action and action not in _VALID_ACTIONS:
                report["errors"].append(f"[{sid}] step {i}: invalid action '{action}'")
                report["passed"] = False

            selector = step.get("selector") or {}
            sel_name = selector.get("name", "")
            if sel_name:
                if tree_names is not None and sel_name in tree_names:
                    pass
                elif _NOISE_NAME_RE.match(sel_name):
                    report["errors"].append(
                        f"[{sid}] step {i}: selector name '{sel_name}' is noise"
                    )
                    report["passed"] = False
                elif tree_names is not None and sel_name not in tree_names:
                    report["errors"].append(
                        f"[{sid}] step {i}: selector name '{sel_name}' not found in annotated tree"
                    )
                    report["passed"] = False

            sel_role = selector.get("role", "")
            if not sel_name and not sel_role and not selector.get("name_pattern"):
                report["warnings"].append(
                    f"[{sid}] step {i}: selector is empty (no name/role/name_pattern)"
                )

    return report


def validate_gate4(generate_output_dir: str, at_tree_annotated_path: str = "") -> dict:
    report = {"gate": 4, "name": "Generation Gate", "errors": [], "warnings": [], "passed": True}

    out_dir = Path(generate_output_dir)
    if not out_dir.exists():
        report["errors"].append(f"Output directory not found: {generate_output_dir}")
        report["passed"] = False
        return report

    suite_files = list(out_dir.rglob("*.suite.yaml"))
    if not suite_files:
        report["errors"].append("No .suite.yaml files found in output directory")
        report["passed"] = False
        return report

    tree_names: set[str] | None = None
    if at_tree_annotated_path:
        tree_data = _load_yaml(at_tree_annotated_path)
        if tree_data:
            tree_nodes = tree_data.get("tree", [])
            tree_names = set()
            for node, _ in _flatten_tree(tree_nodes):
                n = node.get("name", "")
                if n:
                    tree_names.add(n)
                on = node.get("object_name", "")
                if on:
                    tree_names.add(on)

    for suite_file in suite_files:
        suite_data = _load_yaml(str(suite_file))
        if not suite_data:
            report["errors"].append(f"Failed to parse: {suite_file.name}")
            report["passed"] = False
            continue

        suites = suite_data.get("suites", [])
        for suite in suites:
            sid = suite.get("id", "?")
            steps = suite.get("steps", [])
            for i, step in enumerate(steps):
                action = step.get("action", "")
                if action and action not in _VALID_ACTIONS:
                    report["errors"].append(
                        f"[{suite_file.name}:{sid}] step {i}: invalid action '{action}'"
                    )
                    report["passed"] = False

                selector = step.get("selector") or {}
                sel_name = selector.get("name", "")
                if sel_name:
                    if tree_names and sel_name in tree_names:
                        pass
                    elif _NOISE_NAME_RE.match(sel_name):
                        report["errors"].append(
                            f"[{suite_file.name}:{sid}] step {i}: selector name '{sel_name}' is noise"
                        )
                        report["passed"] = False

    return report


def validate_gate5(cases_mapped_path: str, at_tree_annotated_path: str = "") -> dict:
    report = {
        "gate": 5,
        "name": "Semantic Safety Gate",
        "errors": [],
        "warnings": [],
        "passed": True,
    }

    cases_data = _load_yaml(cases_mapped_path)
    if not cases_data:
        report["errors"].append(f"File not found or empty: {cases_mapped_path}")
        report["passed"] = False
        return report

    cases = cases_data.get("cases", [])
    _DESC_KEYWORDS = frozenset(
        {"显示", "被清空", "可以重新", "正常", "异常", "检查", "查看", "应当", "应该"}
    )
    _PANEL_OPENER_ACTIONS = frozenset(
        {
            "element_action",
            "dtk_main_menu",
            "dtk_context_menu",
            "mouse_click",
            "mouse_right_click",
            "keyboard_hot_key",
        }
    )
    _ESCAPE_KEYS = frozenset({"escape", "esc", "tab"})

    for suite in cases:
        sid = suite.get("id", "?")
        status = suite.get("status", "active")
        if status in ("non_gui", "unsupported"):
            continue

        steps = suite.get("steps", [])
        for i, step in enumerate(steps):
            action = step.get("action", "")

            if action in ("keyboard_type", "keyboard_type_text"):
                text = step.get("text", "")
                if text:
                    hit = _DESC_KEYWORDS & {kw for kw in _DESC_KEYWORDS if kw in text}
                    if hit or (len(text) > 20 and any(c in text for c in "，。；")):
                        report["warnings"].append(
                            f"[{sid}] step {i}: keyboard_type text疑似描述文本 "
                            f"(keywords={hit or 'long+cn-punct'}): '{text[:40]}'"
                        )

            if action == "keyboard_press":
                key = (step.get("key") or "").lower()
                if key in _ESCAPE_KEYS and i > 0:
                    prev = steps[i - 1] if i > 0 else {}
                    prev_action = prev.get("action", "") if isinstance(prev, dict) else ""
                    if prev_action not in _PANEL_OPENER_ACTIONS:
                        report["warnings"].append(
                            f"[{sid}] step {i}: keyboard_press '{key}' "
                            f"前无打开面板操作 (prev={prev_action})"
                        )

            if action in (
                "element_action",
                "mouse_click",
                "mouse_right_click",
                "mouse_double_click",
                "assert_element",
            ):
                selector = step.get("selector") or {}
                has_name = bool(selector.get("name"))
                has_accessible = bool(selector.get("accessible_id"))
                has_xy = step.get("x") is not None and step.get("y") is not None
                if not has_name and not has_accessible and not has_xy and not step.get("ref"):
                    report["errors"].append(
                        f"[{sid}] step {i}: {action} selector缺 name 和 accessible_id "
                        f"(会导致运行时 ElementNotFound)"
                    )
                    report["passed"] = False

    return report


def run_all_gates(
    at_tree_annotated_path: str = "",
    suite_cases_path: str = "",
    cases_mapped_path: str = "",
    generate_output_dir: str = "",
    element_gaps_path: str = "",
) -> list[dict]:
    results = []
    if at_tree_annotated_path:
        results.append(validate_gate1(at_tree_annotated_path, element_gaps_path))
    if suite_cases_path:
        results.append(validate_gate2(suite_cases_path, at_tree_annotated_path))
    if cases_mapped_path:
        results.append(validate_gate3(cases_mapped_path, at_tree_annotated_path))
        results.append(validate_gate5(cases_mapped_path, at_tree_annotated_path))
    if generate_output_dir:
        results.append(validate_gate4(generate_output_dir, at_tree_annotated_path))
    return results
