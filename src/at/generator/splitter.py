# SPDX-FileCopyrightText: 2026 Uniontech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only

"""Split cases_raw.yaml into per-module directories.

Each module gets:
  modules/<slug>/cases.md          — cases as markdown table
  modules/<slug>/at-tree-subtree.yaml — relevant AT-SPI nodes subset
  manifest.yaml                   — global status tracking

Splitting is pure-rule (no LLM): module field in cases_raw is used.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import yaml

from src.at.generator.manifest import (
    build_manifest,
    make_module_entry,
    write_manifest,
)
from src.at.generator.tree_subset import extract_subtree


def _slugify(name: str) -> str:
    cleaned = re.sub(r"[#()（）\[\]【】]", "", name)
    cleaned = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned.lower()[:64] or "misc"


def _extract_module_name(module_field: str) -> str:
    """Extract the leaf module name from the module path string.

    Input example: '/V25.../终端/104X/设置界面高级设置(#116119)'
    Output: '设置界面高级设置'
    """
    if not module_field:
        return "misc"
    parts = re.split(r"[/.]", module_field)
    for part in reversed(parts):
        cleaned = re.sub(r"\(#[^)]*\)", "", part).strip()
        if cleaned:
            return cleaned
    return "misc"


def _load_cases(cases_path: str) -> dict[str, Any]:
    raw = Path(cases_path).read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    if not data or not isinstance(data, dict):
        print(f"Error: invalid cases_raw format: {cases_path}", file=sys.stderr)
        sys.exit(1)
    return data


def _group_by_module(cases: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for case in cases:
        module_field = case.get("module", "")
        module_name = _extract_module_name(module_field)
        slug = _slugify(module_name)
        groups.setdefault(slug, []).append(case)
    return groups


def _write_cases_md(cases: list[dict], output_path: str) -> None:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = ["| ID | Title | Steps | Expected |", "|---|---|---|---|"]
    for case in cases:
        cid = case.get("id", "")
        title = case.get("name", "") or case.get("description", "")
        steps_list = case.get("steps", [])
        steps_text = "<br>".join(
            s.get("description", "") if isinstance(s, dict) else str(s) for s in steps_list
        )
        expected = [s for s in steps_list if isinstance(s, dict) and s.get("step_type") == "assert"]
        expected_text = "<br>".join(s.get("description", "") for s in expected)
        lines.append(f"| {cid} | {title} | {steps_text} | {expected_text} |")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def split_cases(
    cases_path: str,
    at_tree_path: str,
    output_dir: str,
    app_name: str = "",
) -> dict[str, Any]:
    """Split cases_raw.yaml into per-module directories.

    Returns summary dict with module count and total cases.
    """
    data = _load_cases(cases_path)
    metadata = data.get("metadata", {})
    source = metadata.get("source", Path(cases_path).name)
    if not app_name:
        app_name = source

    cases = data.get("cases", [])
    if not cases:
        print(f"Error: no cases found in {cases_path}", file=sys.stderr)
        sys.exit(1)

    groups = _group_by_module(cases)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    module_entries = []
    total_subtree_stats: list[dict[str, Any]] = []

    for slug, module_cases in sorted(groups.items()):
        module_dir = out / "modules" / slug
        module_dir.mkdir(parents=True, exist_ok=True)

        cases_md = module_dir / "cases.md"
        _write_cases_md(module_cases, str(cases_md))

        descriptions: list[str] = []
        for case in module_cases:
            for step in case.get("steps", []):
                if isinstance(step, dict):
                    desc = step.get("description", "")
                    if desc:
                        descriptions.append(desc)

        subtree_path = module_dir / "at-tree-subtree.yaml"
        stats = extract_subtree(
            at_tree_path,
            descriptions,
            str(subtree_path),
        )
        total_subtree_stats.append(stats)

        entry = make_module_entry(
            slug=slug,
            cases=len(module_cases),
            has_manual=False,
        )
        module_entries.append(entry)

        print(
            f"  module '{slug}': {len(module_cases)} cases, "
            f"subtree {stats['subtree_nodes']}/{stats['total_nodes']} nodes "
            f"({stats['coverage']:.1%})"
        )

    manifest = build_manifest(
        app=app_name,
        source=source,
        modules=module_entries,
    )
    manifest_path = write_manifest(manifest, str(out))

    total_cases = sum(m["cases"] for m in module_entries)
    print(
        f"\nSplit complete: {len(module_entries)} modules, "
        f"{total_cases} cases -> {out}"
    )
    print(f"  manifest: {manifest_path}")

    return {
        "modules": len(module_entries),
        "total_cases": total_cases,
        "output_dir": str(out),
    }
