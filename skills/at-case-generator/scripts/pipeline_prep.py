#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
# SPDX-License-Identifier: GPL-2.0-only
"""pipeline_prep.py — Phase 1: Split cases_raw.yaml into per-module input.json.

Usage:
    pipeline_prep.py --plan tests/at/plan.yaml --cases tests/at/cases_raw.yaml \\
        --output tests/at/modules/ [--app deepin-reader]

Reads plan.yaml (module → case_ids mapping) and cases_raw.yaml (full case list).
Outputs one input.json per module, containing only the cases belonging to that
module. The LLM reads each input.json independently in Phase 2.

Inputs (YAML, structured, script-friendly):
    plan.yaml        — app, modules[].slug, modules[].case_ids

Output (JSON, per module):
    modules/<slug>.input.json
    modules/_summary.json
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


def _load_yaml(path: str) -> dict | None:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        print(f"Error: {path} is not a valid YAML mapping")
        return None
    return data


def _build_case_index(cases: list[dict]) -> dict[str, dict]:
    """Build case_id → case dict lookup from cases_raw.yaml."""
    return {c["id"]: c for c in cases}


def _short_module_name(slug: str) -> str:
    """Extract short human-readable module name from plan.yaml slug.

    Input:  v25_2500_测试部专用_b类解耦商店应用_文档查看器_缩略图_书签_114165
    Output: 缩略图_书签

    The slug format is: <prefix>_<hierarchy>_<PMS_ID>
    We strip the common prefix and trailing PMS ID.
    """
    # Strip trailing _digits (PMS ID)
    m = re.search(r"_(\d+)$", slug)
    if m:
        base = slug[: m.start()]
    else:
        base = slug

    # Strip known prefixes from shortest to longest
    prefixes = [
        "v25_2500_测试部专用_b类解耦商店应用_文档查看器_",
        "v25_2500_测试部专用_b类解耦商店应用_",
        "v25_2500_测试部专用_",
        "v25_2500_",
    ]
    for prefix in prefixes:
        if base.startswith(prefix):
            base = base[len(prefix) :]
            break

    # If remaining is empty (top-level module), use descriptive name
    if not base:
        return "应用管理"

    return base


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Split cases_raw.yaml into per-module input.json files"
    )
    parser.add_argument("--plan", required=True, help="Path to plan.yaml")
    parser.add_argument("--cases", required=True, help="Path to cases_raw.yaml")
    parser.add_argument("--output", required=True, help="Output directory for modules/")
    parser.add_argument("--app", default="", help="Application name (overrides plan.yaml)")
    args = parser.parse_args()

    # ── Load inputs ──────────────────────────────────────────────────
    plan_data = _load_yaml(args.plan)
    if plan_data is None:
        sys.exit(1)

    cases_data = _load_yaml(args.cases)
    if cases_data is None:
        sys.exit(1)

    app = args.app or plan_data.get("app", "")
    modules_raw = plan_data.get("modules", [])
    cases_list = cases_data.get("cases", [])
    if not modules_raw:
        print("Error: plan.yaml has no modules")
        sys.exit(1)
    if not cases_list:
        print("Error: cases_raw.yaml has no cases")
        sys.exit(1)

    case_index = _build_case_index(cases_list)

    # ── Split by module ──────────────────────────────────────────────
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    total_modules = 0
    total_cases = 0
    module_stats: list[dict] = []

    for mod in modules_raw:
        slug = mod.get("slug", "")
        case_ids = mod.get("case_ids", [])
        module_name = mod.get("name", slug)

        if not slug or not case_ids:
            continue

        # Collect cases belonging to this module
        module_cases: list[dict] = []
        for cid in case_ids:
            case = case_index.get(cid)
            if case:
                module_cases.append(case)
            else:
                print(f"  Warning: case {cid} not found in cases_raw.yaml")

        if not module_cases:
            print(f"  Warning: module {slug} has no matching cases, skipping")
            continue

        short_name = _short_module_name(slug)

        input_data = {
            "meta": {
                "app": app,
                "module": module_name,
                "module_slug": slug,
                "module_short": short_name,
                "case_count": len(module_cases),
            },
            "cases": module_cases,
        }

        # Write per-module input.json
        file_name = f"{short_name}.input.json"
        out_path = out_dir / file_name
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(input_data, f, ensure_ascii=False, indent=2)

        print(f"  [{total_modules + 1}] {short_name:30s} → {file_name}  ({len(module_cases)} cases)")
        module_stats.append(
            {
                "slug": slug,
                "short_name": short_name,
                "file": file_name,
                "case_count": len(module_cases),
            }
        )
        total_modules += 1
        total_cases += len(module_cases)

    # ── Write summary ────────────────────────────────────────────────
    summary = {
        "app": app,
        "total_modules": total_modules,
        "total_cases": total_cases,
        "modules_dir": str(out_dir),
        "modules": module_stats,
    }
    summary_path = out_dir / "_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 60}")
    print(f"Summary: {total_modules} modules, {total_cases} cases")
    print(f"Modules: {summary_path}")
    print(f"  Phase 2: For each *.input.json, run LLM mapping → *.output.json")
    print(f"  Phase 3: pipeline_assemble.py --modules <dir> --output tests/at/")


if __name__ == "__main__":
    main()