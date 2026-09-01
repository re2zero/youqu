#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
# SPDX-License-Identifier: GPL-2.0-only
"""pipeline_assemble.py — Assemble module output.json into suite YAML.

Element-driven assembly. Reads per-slice output.json (from generation
sub-agents), validates, assembles suite YAML + elements.yaml, and collects
each suite's declared covered elements for the 100% coverage gate.

Usage:
    pipeline_assemble.py --modules tests/at/modules/ \
        --output tests/at/ \
        [--manifest tests/at/element-coverage-manifest.yaml] \
        [--generate-mapped tests/at/cases_mapped.yaml]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("Error: PyYAML required")
    sys.exit(1)


# ─── Schema (mirrors the installed youqu runtime HANDLERS) ──────────────
# The runtime executor registers exactly these actions; anything else is
# rejected at run time with "unknown action". Keep this in sync with
# youqu/src/at/executor/handlers.py HANDLERS.
ASSERT_ACTIONS = frozenset(
    {
        "assert_element",
        "assert_not_exists",
        "assert_window",
        "assert_window_count",
        "assert_process_running",
        "assert_process_not_running",
        "assert_file_exists",
        "assert_file_not_exists",
        "assert_image_exists",
        "assert_image_not_exists",
        "assert_ocr_exists",
        "assert_ocr_not_exists",
    }
)
VALID_ACTIONS = frozenset(
    {
        "session_start",
        "session_stop",
        "element_action",
        "mouse_click",
        "mouse_right_click",
        "mouse_double_click",
        "mouse_drag",
        "mouse_scroll",
        "dtk_main_menu",
        "dtk_context_menu",
        "keyboard_press",
        "keyboard_hot_key",
        "keyboard_type",
        "keyboard_type_text",
        "file_dialog_select",
        "file_dialog_cancel",
        "element_set_value",
        "dbus_call",
        "dbus_get_property",
        "screenshot",
    }
    | ASSERT_ACTIONS
)

MENU_ACTIONS = frozenset({"dtk_main_menu", "dtk_context_menu"})
SETUP_ACTIONS = frozenset({"session_start", "session_stop"})


def _validate_step(step: dict, case_id: str, step_idx: int) -> list[str]:
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
    if step_type == "assert" and action and not action.startswith("assert_"):
        errors.append(f"{prefix}: assert step must use assert_* action, got '{action}'")
    if action in MENU_ACTIONS and not step.get("items"):
        errors.append(f"{prefix}: {action} requires 'items' list")
    if action == "keyboard_type":
        text = step.get("text", "")
        if not text:
            errors.append(f"{prefix}: keyboard_type requires 'text'")
        elif len(text) > 50:
            errors.append(f"{prefix}: keyboard_type text > 50 chars, likely description not input")
    if action == "keyboard_hot_key":
        key = step.get("key", "")
        if not key:
            errors.append(f"{prefix}: keyboard_hot_key requires 'key'")
        elif "鼠" in key or "滚" in key:
            errors.append(f"{prefix}: keyboard_hot_key key='{key}' contains Chinese, invalid")
    return errors


def _normalize_step(step: dict) -> dict:
    """Normalize field names from LLM output to canonical form."""
    if not isinstance(step, dict):
        return {}
    normalized: dict = {}
    # step_type / type
    st = step.get("step_type") or step.get("type") or ""
    if st in ("action", "assert"):
        normalized["step_type"] = st
    # action / operation
    action = step.get("action") or step.get("operation") or ""
    if action:
        normalized["action"] = action
    # selector / target
    selector = step.get("selector")
    if isinstance(selector, dict):
        normalized["selector"] = selector
    elif step.get("target"):
        normalized["selector"] = {"name": step["target"]}
    # do / value
    if step.get("do") is not None:
        normalized["do"] = step["do"]
    elif step.get("value") is not None and step.get("value") in ("click", "clear", "set"):
        normalized["do"] = step["value"]
    # passthrough scalar fields
    for k in ("key", "text", "items", "path", "command", "wait", "x", "y", "value",
              "name_pattern", "expected", "app", "prompt", "evidence", "note"):
        if step.get(k) is not None:
            normalized[k] = step[k]
    return normalized


def _normalize_steps(steps: list[dict]) -> list[dict]:
    result = [_normalize_step(s) for s in steps]
    return [s for s in result if s.get("action")]


def _clean_step(step: dict) -> dict:
    allowed = {
        "step_type", "action", "selector", "do", "key", "text", "items", "path",
        "command", "wait", "x", "y", "value", "name", "expected", "app",
        "prompt", "evidence", "note",
    }
    return {k: v for k, v in step.items() if k in allowed and v is not None}


def _has_session_start(suite: dict) -> bool:
    return any(s.get("action") == "session_start" for s in suite.get("steps", []))


def _inject_session_start(suite: dict, app: str) -> dict:
    steps = _normalize_steps(suite.get("steps", []))
    if not _has_session_start({"steps": steps}):
        steps.insert(0, {"step_type": "action", "action": "session_start", "command": app})
    suite["steps"] = steps
    return suite


def _validate_suite(suite: dict) -> list[str]:
    errors: list[str] = []
    sid = suite.get("id", "(no id)")
    # Unsupported suites are intentionally skipped: template rule 8 requires
    # status:"unsupported" + empty steps. Do NOT flag them for missing
    # assertions — that is by design, not an error.
    if suite.get("status") == "unsupported":
        return errors
    steps = suite.get("steps", [])
    has_assert = False
    for i, step in enumerate(steps):
        errors.extend(_validate_step(step, sid, i))
        if step.get("action", "").startswith("assert_"):
            has_assert = True
    if not has_assert:
        errors.append(f"{sid}: no assert steps — suite has no verifiable assertions")
    return errors


def _collect_elements_from_suite(suite: dict) -> dict[str, dict]:
    """Extract element references from suite steps (persistent selector.name)."""
    elements: dict[str, dict] = {}
    for step in suite.get("steps", []):
        selector = step.get("selector")
        if isinstance(selector, dict):
            name = selector.get("name", "")
            role = selector.get("role", "")
            if name:
                if name not in elements:
                    elements[name] = {"name": name}
                    if role:
                        elements[name]["role"] = role
            accessible_id = selector.get("accessible_id", "")
            if accessible_id and accessible_id not in elements:
                elements[accessible_id] = {"accessible_id": accessible_id}
    return elements


def _collect_declared_elements(suite: dict) -> set[str]:
    """Collect the suite's declared covered elements (annotation.AT元素引用)."""
    declared: set[str] = set()
    ann = suite.get("annotation") or {}
    refs = ann.get("AT元素引用") or []
    for r in refs:
        if isinstance(r, str):
            declared.add(r.strip("{}").strip())
    return declared


def _build_suite_cases(suite: dict, session_cmd: str) -> tuple[list[dict], list[dict]]:
    steps = _normalize_steps(suite.get("steps", []))
    steps = [s for s in steps if s.get("action")]
    setup_steps: list[dict] = []
    case_steps: list[dict] = []
    assert_steps: list[dict] = []
    for step in steps:
        action = step.get("action", "")
        if action == "session_start":
            command = step.get("command", session_cmd)
            setup_steps.append({"action": "session_start", "command": command, "wait": 3.0})
        elif action == "session_stop":
            pass
        elif action.startswith("assert_"):
            assert_steps.append(_clean_step(step))
        else:
            case_steps.append(_clean_step(step))

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


def _slugify_module(name: str) -> str:
    cleaned = re.sub(r"[#()（）\[\]【】]", "", name)
    cleaned = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", cleaned).strip("_")
    return cleaned[:64] or "misc"


def _write_yaml(data: dict | list, path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def _load_manifest(path: str) -> dict[str, dict]:
    """Load element-coverage-manifest.yaml → {name: {role, source, type}}."""
    if not path:
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except (FileNotFoundError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    elements = data.get("elements", {})
    return elements if isinstance(elements, dict) else {}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Assemble LLM output.json into executable suite YAML (element-driven)",
        epilog=(
            "Examples:\n"
            "  python3 pipeline_assemble.py --modules tests/at/modules/ \\\n"
            "      --output tests/at/ --manifest tests/at/element-coverage-manifest.yaml\n"
            "  python3 pipeline_assemble.py --modules tests/at/modules/ --output tests/at/ \\\n"
            "      --validate-only   # only validate output.json, don't write suites"
        ),
    )
    parser.add_argument("--modules", required=True, help="Directory with *.output.json")
    parser.add_argument("--output", required=True, help="Output directory (tests/at/ root)")
    parser.add_argument("--manifest", default="", help="element-coverage-manifest.yaml")
    parser.add_argument("--app", default="", help="Application name (overrides meta.app)")
    parser.add_argument("--validate-only", action="store_true", help="Only validate output.json")
    parser.add_argument("--generate-mapped", default="", help="Also write cases_mapped.yaml")
    args = parser.parse_args()

    modules_dir = Path(args.modules)
    if not modules_dir.is_dir():
        print(f"Error: {args.modules} is not a directory")
        sys.exit(1)

    output_dir = Path(args.output)
    yaml_dir = output_dir / "yaml"
    manifest_elements = _load_manifest(args.manifest)

    output_files = sorted(modules_dir.glob("*.output.json"))
    if not output_files:
        print(f"Error: no *.output.json files found in {args.modules}")
        sys.exit(1)

    print(f"Found {len(output_files)} output.json files")

    all_suite_configs: list[dict] = []
    all_elements: dict[str, dict] = {}
    all_declared: set[str] = set()
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

        for suite in suites:
            _inject_session_start(suite, app)

        # Dedup: merge suites with identical action sequences
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
                if s.get("action") not in ("session_start", "session_stop") and s.get("action")
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

        # Inject TEST_FILES_DIR path
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
                {"file": out_path.name, "module": module, "suites": len(suites),
                 "cases": mod_cases, "errors": mod_errors}
            )
            continue

        safe_module = _slugify_module(module_short)
        session_cmd = app
        module_suite_cases: list[dict] = []
        module_setup: list[dict] = []

        for suite in suites:
            for step in suite.get("steps", []):
                if step.get("action") == "session_start" and step.get("command"):
                    session_cmd = step["command"]
                    break
            cases, setup = _build_suite_cases(suite, session_cmd)
            module_suite_cases.extend(cases)
            if setup and not module_setup:
                module_setup = setup
            elements = _collect_elements_from_suite(suite)
            all_elements.update(elements)
            all_declared |= _collect_declared_elements(suite)
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
            {"file": out_path.name, "module": module, "suites": len(suites),
             "cases": mod_cases, "errors": mod_errors}
        )
        status = "FAIL" if mod_errors > 0 else "OK"
        print(f"  [{status}] {out_path.name}: {len(suites)} suites, {mod_cases} cases, {mod_errors} errors")

    if args.validate_only:
        print(f"\n{'=' * 60}")
        print(f"Validation: {total_errors} errors, {total_warnings} warnings")
        sys.exit(1 if total_errors > 0 else 0)

    # ── Supplement elements from manifest (authoritative whitelist) ──
    for ref, sel in manifest_elements.items():
        if ref not in all_elements:
            all_elements[ref] = {"name": ref, "role": sel.get("role", "")}

    # ── Write elements.yaml ──────────────────────────────────────────
    if all_elements:
        elements_path = yaml_dir / "elements.yaml"
        _write_yaml({"elements": all_elements}, str(elements_path))
        print(f"Wrote {elements_path} ({len(all_elements)} elements)")

    # ── Write per-module suite files ─────────────────────────────────
    total_suite_cases = 0
    total_no_assert = 0
    for config in all_suite_configs:
        module = config["module"]
        module_dir = yaml_dir / module
        suite_path = module_dir / f"{module}.suite.yaml"
        has_assert = False
        for sc in config.get("suites", []):
            if sc.get("assert_steps"):
                has_assert = True
            total_suite_cases += 1
        if not has_assert:
            total_no_assert += 1
        _write_yaml(config, str(suite_path))
        print(f"Wrote {suite_path} ({len(config.get('suites', []))} cases)")

    # ── Generate merged cases_mapped.yaml (optional) ─────────────────
    if args.generate_mapped:
        merged_cases = []
        for config in all_suite_configs:
            module = config["module"]
            for sc in config.get("suites", []):
                entry = {"id": sc["id"], "name": sc.get("name", ""), "module": module, "steps": []}
                for step in sc.get("steps", []):
                    entry["steps"].append(step)
                for step in sc.get("assert_steps", []):
                    entry["steps"].append(step)
                merged_cases.append(entry)
        _write_yaml({"version": "1.0", "cases": merged_cases}, args.generate_mapped)
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
    print(f"  Declared covered elements: {len(all_declared)}")
    print(f"  Output: {yaml_dir}/")


if __name__ == "__main__":
    main()