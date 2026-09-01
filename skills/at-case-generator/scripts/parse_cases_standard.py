#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
# SPDX-License-Identifier: GPL-2.0-only
"""parse_cases_standard.py — Convert at-case-authoring output into module input.json.

Reads at-case-authoring mode-B products and emits one modules/<slug>_<seq>.input.json
per module (the input for AT-SPI suite mapping). No token-budget re-slicing:
at-case-authoring already normalized and grouped by module (normalized/), and
the user chose to map a whole module at once.

Input (either):
    --input <cases_standard.yaml>     full file (cases: [...])
    --input <normalized dir>          normalized/*.yaml (app/cases per module)
Output:
    modules/<slug>_<seq>.input.json   one per module (LLM/mapping input)
    modules/_summary.json             slice manifest (module, case_count, manual_count)

The output JSON schema matches at-suite-generator's pipeline_parse.py so that
pipeline_assemble.py consumes it unchanged. meta.module_short is set (assemble
reads it for the output file name).

Usage:
    parse_cases_standard.py --input tests/casefile/out/cases_standard.yaml \
        --output tests/at/modules/ --app deepin-screen-recorder
    parse_cases_standard.py --input tests/casefile/out/normalized/ \
        --output tests/at/modules/ --app deepin-screen-recorder
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


_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def estimate_tokens(text: str) -> int:
    """Same estimator as at-suite-generator: CJK ~0.7 tok/char, other ~0.3."""
    if not text:
        return 0
    cjk = len(_CJK_RE.findall(text))
    other = len(text) - cjk
    return int(cjk * 0.7 + other * 0.3)


def _case_tokens(case: dict) -> int:
    return estimate_tokens(
        " ".join(
            str(case.get(k) or "")
            for k in ("id", "title", "module", "precondition", "steps", "expected")
        )
    )


def _slugify(text: str) -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", str(text or "")).strip("_")
    return cleaned[:64] or "misc"


def load_cases(input_path: Path) -> tuple[list[dict], str]:
    """Load cases from a cases_standard.yaml file or a directory of module files.

    Directory mode reads every *.yaml that has a `cases` key (normalized/).
    Returns (cases, source_label) where source_label records the input origin.
    """
    if input_path.is_dir():
        cases: list[dict] = []
        for f in sorted(input_path.glob("*.yaml")):
            data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            cases.extend(data.get("cases", []) or [])
        return cases, f"{input_path.name}/"
    if input_path.is_file():
        data = yaml.safe_load(input_path.read_text(encoding="utf-8")) or {}
        return list(data.get("cases", []) or []), input_path.name
    print(f"Error: {input_path} not found")
    sys.exit(1)


def _group_by_module(cases: list[dict]) -> list[dict]:
    """Group by the module field, preserving first-seen order."""
    groups: dict[str, list[dict]] = {}
    order: list[str] = []
    for c in cases:
        mod = (c.get("module") or "").strip() or "未分类"
        if mod not in groups:
            groups[mod] = []
            order.append(mod)
        groups[mod].append(c)
    return [{"module": mod, "cases": groups[mod]} for mod in order]


def _unique_slugs(groups: list[dict]) -> dict[str, str]:
    """Map module name -> unique slug (collision-safe)."""
    result: dict[str, str] = {}
    used: set[str] = set()
    for g in groups:
        mod = g["module"]
        base = _slugify(mod)
        slug = base
        i = 2
        while slug in used:
            slug = f"{base}_{i}"
            i += 1
        used.add(slug)
        result[mod] = slug
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert at-case-authoring output into module input.json",
        epilog=(
            "Examples:\n"
            "  parse_cases_standard.py --input tests/casefile/out/cases_standard.yaml \\\n"
            "      --output tests/at/modules/ --app deepin-screen-recorder\n"
            "  parse_cases_standard.py --input tests/casefile/out/normalized/ \\\n"
            "      --output tests/at/modules/ --app deepin-screen-recorder\n"
            "\n"
            "Emits one input.json per module (no token re-slicing)."
        ),
    )
    parser.add_argument("--input", required=True,
                        help="cases_standard.yaml or a directory of module YAMLs (normalized/)")
    parser.add_argument("--output", required=True, help="modules/ output directory")
    parser.add_argument("--app", default="", help="Application name")
    args = parser.parse_args()

    in_path = Path(args.input)
    cases, source_name = load_cases(in_path)
    if not cases:
        print(f"Error: no cases found in {in_path}")
        sys.exit(1)

    groups = _group_by_module(cases)
    slug_map = _unique_slugs(groups)

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    slice_stats: list[dict] = []
    total_cases = 0
    for seq, g in enumerate(groups, 1):
        mod = g["module"]
        mod_cases = g["cases"]
        slug = slug_map[mod]
        file_name = f"{slug}_{seq:03d}.input.json"
        input_data = {
            "meta": {
                "app": args.app,
                "module": mod,
                "module_short": slug,
                "slice_seq": seq,
                "case_count": len(mod_cases),
                "est_tokens": sum(_case_tokens(c) for c in mod_cases),
                "source": f"at-case-authoring:{source_name}",
            },
            "cases": mod_cases,
        }
        out_path = out_dir / file_name
        out_path.write_text(
            json.dumps(input_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        total_cases += len(mod_cases)
        manual_count = sum(1 for c in mod_cases if c.get("manual"))
        slice_stats.append(
            {
                "file": file_name,
                "module": mod,
                "seq": seq,
                "case_count": len(mod_cases),
                "manual_count": manual_count,
                "est_tokens": input_data["meta"]["est_tokens"],
            }
        )
        print(f"  [{seq:2d}] {file_name:40s} {len(mod_cases):3d} cases "
              f"({manual_count} manual) ~{input_data['meta']['est_tokens']} tok")

    # ── Integrity check: no case lost ───────────────────────────────
    re_read_ids: set[str] = set()
    for st in slice_stats:
        data = json.loads((out_dir / st["file"]).read_text(encoding="utf-8"))
        re_read_ids.update(c["id"] for c in data["cases"])
    src_ids = {c.get("id") for c in cases}
    missing = src_ids - re_read_ids
    extra = re_read_ids - src_ids
    if missing or extra:
        print(f"  ✗ INTEGRITY FAIL: {len(missing)} missing, {len(extra)} extra case ids")
        sys.exit(1)
    if total_cases != len(cases):
        print(f"  ✗ INTEGRITY FAIL: wrote {total_cases} != source {len(cases)}")
        sys.exit(1)
    print(f"  ✓ Integrity OK: {total_cases}/{len(cases)} cases preserved")

    summary = {
        "app": args.app,
        "source": source_name,
        "total_cases": total_cases,
        "total_slices": len(slice_stats),
        "slices": slice_stats,
    }
    (out_dir / "_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nSummary: {total_cases} cases → {len(slice_stats)} modules")
    print(f"  Slices: {out_dir / '_summary.json'}")
    print("  Next: main agent maps each *.input.json → *.output.json")


if __name__ == "__main__":
    main()
