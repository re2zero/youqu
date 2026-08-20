#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
# SPDX-License-Identifier: GPL-2.0-only
"""pipeline_assemble.py — Phase 3: Assemble module output.json into suite YAML.

Usage:
    pipeline_assemble.py --modules tests/at/modules/ --output tests/at/ \\
        [--at-tree tests/at/at-tree.yaml]

Reads all *.output.json from modules/ directory (produced by LLM in Phase 2).
Validates each against JSON Schema, then generates:
    - yaml/<module>/<module>.suite.yaml  (per-module suite files)
    - yaml/elements.yaml                 (element reference index)

Can also generate a single merged cases_mapped.yaml for Gate 5 validation.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml


# ─── Schema ───────────────────────────────────────────────────────────

ASSERT_ACTIONS = frozenset(
    {
        "assert_element",
        "assert_not_exists",
        "assert_window",
        "assert_window_count",
        "assert_text",
        "assert_ocr_exists",
        "assert_image_exists",
        "assert_process",
        "assert_file_exists",
    }
)

VALID_ACTIONS = frozenset(
    {
        "session_start",
        "session_stop",
        "element_action",
        "mouse_click",
        "mouse_right_click",
        "mouse_drag",
        "mouse_scroll",
        "dtk_main_menu",
        "dtk_context_menu",
        "keyboard_press",
        "keyboard_hot_key",
        "keyboard_type",
        "file_dialog_select",
        "file_dialog_cancel",
        "wait",
        "wait_for",
        "element_set_value",
        "hide_window",
        "show_window",
        "clipboard_input",
    }
    | ASSERT_ACTIONS
)

MENU_ACTIONS = frozenset({"dtk_main_menu", "dtk_context_menu"})

# Step types that are setup/teardown, not mapped by LLM
SETUP_ACTIONS = frozenset({"session_start", "session_stop"})


def _validate_step(step: dict, case_id: str, step_idx: int) -> list[str]:
    """Validate a single step. Returns list of error messages."""
    errors: list[str] = []
    prefix = f"{case_id}.steps[{step_idx}]"

    step_type = step.get("step_type", "")
    if step_type not in ("action", "assert"):
        errors.append(f"{prefix}: step_type must be 'action' or 'assert', got '{step_type}'")

    action = step.get("action", "")
    if not action:
        errors.append(f"{prefix}: action is required")
    elif action not in VALID_ACTIONS:
        errors.append(f"{prefix}: unknown action '{action}'")

    # Assert steps must have assert_* action
    if step_type == "assert" and action and not action.startswith("assert_"):
        errors.append(f"{prefix}: assert step must use assert_* action, got '{action}'")

    # Menu actions must have items
    if action in MENU_ACTIONS and not step.get("items"):
        errors.append(f"{prefix}: {action} requires 'items' list")

    # keyboard_type must have text
    if action == "keyboard_type":
        text = step.get("text", "")
        if not text:
            errors.append(f"{prefix}: keyboard_type requires 'text'")
        # Check for common description-as-input anti-patterns
        if len(text) > 50:
            errors.append(f"{prefix}: keyboard_type text > 50 chars, likely description not input")

    # keyboard_hot_key must have valid key
    if action == "keyboard_hot_key":
        key = step.get("key", "")
        if not key:
            errors.append(f"{prefix}: keyboard_hot_key requires 'key'")
        elif "鼠" in key or "滚" in key:
            errors.append(f"{prefix}: keyboard_hot_key key='{key}' contains Chinese (mouse wheel), invalid")

    return errors


def _normalize_steps(steps: list[dict]) -> list[dict]:
    """Normalize and filter steps."""
    result = [_normalize_step(s) for s in steps]
    return [s for s in result if s.get("action")]


def _has_session_start(suite: dict) -> bool:
    """Check if suite has a session_start step."""
    for step in suite.get("steps", []):
        if step.get("action") == "session_start":
            return True
    return False


def _inject_session_start(suite: dict, app: str) -> dict:
    """Prepend session_start if missing."""
    steps = _normalize_steps(suite.get("steps", []))
    if not _has_session_start({"steps": steps}):
        steps.insert(0, {"step_type": "action", "action": "session_start", "command": app})
    suite["steps"] = steps
    return suite
def _validate_suite(suite: dict) -> list[str]:
    """Validate a single suite. Returns list of error messages."""
    errors: list[str] = []

    sid = suite.get("id", "(no id)")
    steps = suite.get("steps", [])

    has_assert = False
    has_only_assert_window = True

    for i, step in enumerate(steps):
        errors.extend(_validate_step(step, sid, i))
        action = step.get("action", "")
        if action.startswith("assert_"):
            has_assert = True
            if action != "assert_window":
                has_only_assert_window = False

    if not has_assert:
        errors.append(f"{sid}: no assert steps — suite has no verifiable assertions")

    return errors


def _collect_elements_from_suite(suite: dict) -> dict[str, dict]:
    """Extract element references from suite steps."""
    elements: dict[str, dict] = {}
    for step in suite.get("steps", []):
        selector = step.get("selector")
        if isinstance(selector, dict):
            name = selector.get("name", "")
            role = selector.get("role", "")
            if name:
                ref_key = name
                if ref_key not in elements:
                    elements[ref_key] = {"name": name}
                    if role:
                        elements[ref_key]["role"] = role
            accessible_id = selector.get("accessible_id", "")
            if accessible_id and accessible_id not in elements:
                elements[accessible_id] = {"accessible_id": accessible_id}
    return elements


def _collect_elements_from_at_tree(at_tree_path: str) -> dict[str, dict]:
    """Supplement elements from at-tree interactive nodes."""
    try:
        with open(at_tree_path, encoding="utf-8") as f:
            tree_data = yaml.safe_load(f)
    except (FileNotFoundError, OSError):
        return {}

    if not tree_data or not isinstance(tree_data, dict):
        return {}

    elements: dict[str, dict] = {}

    def _walk(nodes: list[dict]) -> None:
        for node in nodes:
            if not isinstance(node, dict):
                continue
            classification = node.get("classification", "")
            if classification and classification != "interactive":
                children = node.get("children", [])
                if children:
                    _walk(children)
                continue
            name = node.get("name", "")
            role = node.get("role", "")
            if name or role:
                elements[name] = {"name": name, "role": role}
            children = node.get("children", [])
            if children:
                _walk(children)

    tree_nodes = tree_data.get("tree", [])
    if isinstance(tree_nodes, list):
        _walk(tree_nodes)

    return elements


def _build_suite_cases(suite: dict, session_cmd: str) -> list[dict]:
    """Convert one LLM suite into a list of SuiteCase entries.

    Separate session_start/stop, group action steps, attach assert steps.
    Returns list of SuiteCase-compatible dicts.
    """
    # Normalize all steps first (handle old schema field names)
    steps = [_normalize_step(s) for s in steps]
    # Filter out completely empty steps
    steps = [s for s in steps if s.get("action")]

    setup_steps = []
    case_steps = []
    assert_steps = []

    for step in steps:
        action = step.get("action", "")
        if action == "session_start":
            command = step.get("command", session_cmd)
            setup_steps.append(
                {"action": "session_start", "command": command, "wait": 3.0}
            )
        elif action == "session_stop":
            pass  # handled at teardown
        elif action.startswith("assert_"):
            s = _clean_step(step)
            assert_steps.append(s)
        else:
            s = _clean_step(step)
            case_steps.append(s)

    suite_cases: list[dict] = []
    case_counter = 0
    current: dict | None = None

    for step in case_steps:
        if current is None:
            case_counter += 1
            current = {
                "id": f"{suite['id']}_s{case_counter}",
                "name": suite.get("name", "")[:60],
                "description": "",
                "steps": [step],
                "assert_steps": [],
            }
        else:
            current["steps"].append(step)

    if current and assert_steps:
        current["assert_steps"] = assert_steps
        suite_cases.append(current)
    elif current:
        suite_cases.append(current)
    elif assert_steps:
        case_counter += 1
        suite_cases.append(
            {
                "id": f"{suite['id']}_s{case_counter}",
                "name": suite.get("name", "")[:60],
                "description": "",
                "steps": [],
                "assert_steps": assert_steps,
            }
        )

    return suite_cases, setup_steps


def _normalize_step(step: dict) -> dict:
    """Normalize field names from LLM output to canonical form.
    
    LLM may output old schema: {type, operation, target, value, expected}
    Canonical schema:          {step_type, action, selector, do, ...}
    """
    if not step:
        return {}
    
    # If step already uses canonical field names, return as-is (via _clean_step)
    if "action" in step or "step_type" in step:
        return step
    
    old = step.get("operation", "")
    old_type = step.get("type", "")
    if not old and not old_type:
        return step
    
    normalized: dict[str, Any] = {"step_type": "action"}
    if old_type == "assert":
        normalized["step_type"] = "assert"
    
    # Map old operation → canonical action
    op_map = {
        "session_start": "session_start",
        "session_stop": "session_stop",
        "element_action": "element_action",
        "mouse_click": "mouse_click",
        "mouse_right_click": "mouse_right_click",
        "mouse_double_click": "mouse_double_click",
        "mouse_wheel": "mouse_wheel",
        "element_state": "assert_element",  # old assert-style
        "dtk_main_menu": "dtk_main_menu",
        "dtk_context_menu": "dtk_context_menu",
        "keyboard_press": "keyboard_press",
        "keyboard_hot_key": "keyboard_hot_key",
        "keyboard_type": "keyboard_type",
    }
    normalized["action"] = op_map.get(old, old)
    
    # Map target → selector.name
    target = step.get("target", "")
    if target:
        normalized["selector"] = {"name": target}
    
    # Map value → do or value
    value = step.get("value", "")
    if value in ("click", "clear", "set"):
        normalized["do"] = value
    elif value:
        normalized["value"] = value
    
    # Map expected → do (for assert states)
    expected = step.get("expected", "")
    if expected:
        normalized["expected"] = expected
    
    # Carry over other fields
    for k in ("wait", "items", "key", "text", "path", "x", "y", "menu", "prompt"):
        if k in step:
            normalized[k] = step[k]
    return normalized

def _clean_step(step: dict) -> dict:
    """Remove internal fields and ensure consistent keys."""
    allowed = {
        "action", "selector", "do", "command", "wait", "wait_for",
        "wait_after", "items", "key", "text", "path", "prompt",
        "evidence", "app", "expected", "name_pattern", "value", "note",
        "x", "y",
    }
    return {k: v for k, v in step.items() if k in allowed and v is not None}


def _write_yaml(data: dict | list, path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def _slugify_module(name: str) -> str:
    cleaned = re.sub(r"[#()（）\[\]【】]", "", name)
    cleaned = re.sub(r"[^\w\-. ]", "_", cleaned)
    cleaned = cleaned.strip().replace(" ", "_")
    return cleaned[:64] or "misc"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Assemble LLM output.json into executable suite YAML"
    )
    parser.add_argument(
        "--modules", required=True,
        help="Directory containing *.output.json files (from Phase 2)"
    )
    parser.add_argument(
        "--output", required=True,
        help="Output directory (tests/at/ root)"
    )
    parser.add_argument(
        "--at-tree", default="",
        help="Path to at-tree.yaml (for element extraction)"
    )
    parser.add_argument(
        "--app", default="",
        help="Application name (overrides meta.app in output.json)"
    )
    parser.add_argument(
        "--validate-only", action="store_true",
        help="Only validate output.json files, don't generate YAML"
    )
    parser.add_argument(
        "--generate-mapped", default="",
        help="Also generate merged cases_mapped.yaml at this path"
    )
    args = parser.parse_args()

    modules_dir = Path(args.modules)
    if not modules_dir.is_dir():
        print(f"Error: {args.modules} is not a directory")
        sys.exit(1)

    output_dir = Path(args.output)
    yaml_dir = output_dir / "yaml"

    # ── Load all output.json files ───────────────────────────────────
    output_files = sorted(modules_dir.glob("*.output.json"))
    if not output_files:
        print(f"Error: no *.output.json files found in {args.modules}")
        print("  Run Phase 2 LLM mapping first: each *.input.json → *.output.json")
        sys.exit(1)

    print(f"Found {len(output_files)} output.json files")

    all_suite_configs: list[dict] = []
    all_elements: dict[str, dict] = {}
    total_errors = 0
    total_warnings = 0
    module_results: list[dict] = []

    for out_path in output_files:
        mod_name = out_path.stem.replace(".output", "")
        try:
            with open(out_path, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"  ERROR: {out_path.name}: {e}")
            total_errors += 1
            continue

        # Validate meta
        meta = data.get("meta", {})
        app = args.app or meta.get("app", "")
        module = meta.get("module", mod_name)
        module_short = meta.get("module_short", _slugify_module(module))
        suites = data.get("suites", [])

        if not suites:
            print(f"  WARN: {out_path.name} has no suites (all cases unsupported?)")
            total_warnings += 1
            module_results.append(
                {"file": out_path.name, "module": module, "suites": 0, "cases": 0, "errors": 0}
            )
            continue
        # ── Auto-inject session_start if missing ───────────────
        for suite in suites:
            _inject_session_start(suite, app)
        
        # ── Dedup: merge suites with identical action sequences ──
        seen: dict[str, list[dict]] = {}
        for suite in suites:
            if suite.get("status") == "unsupported":
                continue
            steps = suite.get("steps", [])
            # Build signature: action types only (skip session_start which is always first)
            sig = "|".join(
                s.get("action", "") for s in steps
                if s.get("action") not in ("session_start", "session_stop")
                and s.get("action")
            )
            if not sig:
                continue
            if sig in seen:
                seen[sig].append(suite)
            else:
                seen[sig] = [suite]
        
        # Remove duplicate suites, keep first occurrence
        deduped: list[dict] = []
        deduped_ids: set[str] = set()
        dedup_count = 0
        for suite in suites:
            if suite.get("status") == "unsupported":
                deduped.append(suite)
                continue
            steps = suite.get("steps", [])
            sig = "|".join(
                s.get("action", "") for s in steps
                if s.get("action") not in ("session_start", "session_stop")
                and s.get("action")
            )
            if not sig:
                deduped.append(suite)
                continue
            if sig in deduped_ids:
                dedup_count += 1
                continue
            deduped_ids.add(sig)
            deduped.append(suite)
        if dedup_count > 0:
            print(f"  DEDUP: {out_path.name} — removed {dedup_count} duplicate suites")
        suites = deduped
        
        # ── Inject TEST_FILES_DIR path ───────────────────────────
        for suite in suites:
            for step in suite.get("steps", []):
                if step.get("action") == "file_dialog_select" and step.get("path"):
                    p = step["path"]
                    if not p.startswith("${TEST_FILES_DIR}/") and not p.startswith("/"):
                        step["path"] = f"${{TEST_FILES_DIR}}/{p}"
        
        mod_errors = 0
        mod_cases = 0
        for suite in suites:
            errs = _validate_suite(suite)
            if errs:
                mod_errors += len(errs)
                total_errors += len(errs)
                for e in errs:
                    print(f"  ERROR: {out_path.name}: {e}")

        if args.validate_only:
            if mod_errors > 0:
                print(f"  FAIL: {out_path.name} — {mod_errors} errors")
            else:
                print(f"  PASS: {out_path.name} — {len(suites)} suites")
            module_results.append(
                {
                    "file": out_path.name,
                    "module": module,
                    "suites": len(suites),
                    "cases": mod_cases,
                    "errors": mod_errors,
                }
            )
            continue

        # Build suite cases — group by module so one .suite.yaml per module
        safe_module = _slugify_module(module_short)
        session_cmd = app
        module_suite_cases: list[dict] = []
        module_setup: list[dict] = []

        for suite in suites:
            # Get session start command from suite steps
            for step in suite.get("steps", []):
                if step.get("action") == "session_start" and step.get("command"):
                    session_cmd = step["command"]
                    break

            cases, setup = _build_suite_cases(suite, session_cmd)
            module_suite_cases.extend(cases)
            if setup and not module_setup:
                module_setup = setup

            # Collect elements from this suite
            elements = _collect_elements_from_suite(suite)
            all_elements.update(elements)
            mod_cases += len(cases)

        if module_suite_cases:
            config = {
                "name": f"{safe_module}_suite",
                "app": app,
                "module": safe_module,
                "setup": module_setup or [{"action": "session_start", "command": session_cmd, "wait": 3.0}],
                "suites": module_suite_cases,
                "teardown": [{"action": "session_stop"}],
            }
            all_suite_configs.append(config)

        module_results.append(
            {
                "file": out_path.name,
                "module": module,
                "suites": len(suites),
                "cases": mod_cases,
                "errors": mod_errors,
            }
        )

        status = "FAIL" if mod_errors > 0 else "OK"
        print(f"  [{status}] {out_path.name}: {len(suites)} suites, {mod_cases} cases, {mod_errors} errors")

    if args.validate_only:
        print(f"\n{'=' * 60}")
        print(f"Validation: {total_errors} errors, {total_warnings} warnings")
        sys.exit(1 if total_errors > 0 else 0)

    # ── Supplement elements from at-tree ──────────────────────────────
    if args.at_tree:
        tree_elements = _collect_elements_from_at_tree(args.at_tree)
        for ref, sel in tree_elements.items():
            if ref not in all_elements:
                all_elements[ref] = sel

    # ── Write elements.yaml ──────────────────────────────────────────
    if all_elements:
        elements_path = yaml_dir / "elements.yaml"
        _write_yaml({"elements": all_elements}, str(elements_path))
        print(f"Wrote {elements_path} ({len(all_elements)} elements)")

    # ── Write per-module suite files ──────────────────────────────────
    total_suite_cases = 0
    total_no_assert = 0

    for config in all_suite_configs:
        module = config["module"]
        module_dir = yaml_dir / module
        suite_path = module_dir / f"{module}.suite.yaml"

        # Count assertions
        has_assert = False
        for sc in config.get("suites", []):
            if sc.get("assert_steps"):
                has_assert = True
            total_suite_cases += 1
        if not has_assert:
            total_no_assert += 1

        _write_yaml(config, str(suite_path))
        case_count = len(config.get("suites", []))
        print(f"Wrote {suite_path} ({case_count} cases)")

    # ── Generate merged cases_mapped.yaml (optional) ─────────────────
    if args.generate_mapped:
        merged_cases = []
        for config in all_suite_configs:
            module = config["module"]
            for sc in config.get("suites", []):
                entry = {
                    "id": sc["id"],
                    "name": sc.get("name", ""),
                    "module": module,
                    "steps": [],
                }
                for step in sc.get("steps", []):
                    entry["steps"].append(step)
                for step in sc.get("assert_steps", []):
                    entry["steps"].append(step)
                merged_cases.append(entry)

        mapped_data = {
            "version": "1.0",
            "cases": merged_cases,
        }
        _write_yaml(mapped_data, args.generate_mapped)
        print(f"Wrote {args.generate_mapped} ({len(merged_cases)} cases)")

    # ── Summary ──────────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print(f"Summary: {len(all_suite_configs)} suites, {total_suite_cases} cases")
    if total_no_assert > 0:
        print(f"  ⚠ {total_no_assert}/{total_suite_cases} suites have no assertions")
    if total_errors > 0:
        print(f"  ⚠ {total_errors} validation errors (see above)")
    else:
        print("  ✓ All validation passed")
    print(f"  Elements: {len(all_elements)}")
    print(f"  Output: {yaml_dir}/")


if __name__ == "__main__":
    main()