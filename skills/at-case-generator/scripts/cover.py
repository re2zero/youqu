#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
# SPDX-License-Identifier: GPL-2.0-only
"""cover.py — Deterministic coverage gate for AT-SPI element coverage.

Element-driven coverage over at-case-authoring's element-map.yaml (runtime
AT-SPI names), NOT a static source scan. Every named interactive element
(persistent id_name in element-map) must be referenced by at least one
persistent selector.name in the generated *.suite.yaml files.

Terminology (do not conflate):
  - transient_items: menu / menu item roles from element-map. Excluded from the
    denominator — located by dtk_main_menu text, not persistent selector.name.
  - unresolved:      id_name TBD/empty from element-map (see manifest). Never
    enter the denominator (excluded at manifest build).
  - unreachable.yaml (user-provided): manually confirmed runtime-unreachable
    persistent elements. This is the ONLY exemption input this script reads.

Usage:
    cover.py --element-map tests/at/casefile/out/element-map.yaml \
        --testdir tests/at/yaml/ \
        [--coverage-report tests/at/coverage-report.yaml] \
        [--unreachable tests/at/unreachable.yaml] \
        [--threshold 100]

Exit 0 if coverage >= threshold, 1 otherwise (CI-friendly).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("Error: PyYAML required")
    sys.exit(1)

TRANSIENT_ROLES = frozenset({"menu", "menu item", "menuitem", "MenuItem"})


# ─── Loaders ────────────────────────────────────────────────────────────
def _load_yaml(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def _collect_element_map(em_path: Path) -> tuple[dict[str, dict], list[dict]]:
    """Collect persistent named elements + transient items from element-map.

    Returns ({name: {role, ui_name, desc}}, [transient items]).
    id_name TBD/empty entries are dropped here (they never enter the
    denominator).
    """
    em = _load_yaml(em_path)
    if not isinstance(em, dict):
        return {}, []
    elements: dict[str, dict] = {}
    transient: list[dict] = []
    for e in em.get("elements", []) or []:
        if not isinstance(e, dict):
            continue
        id_name = (e.get("id_name") or "").strip()
        role = (e.get("role") or "").strip()
        if not id_name or id_name in ("TBD", "待补充"):
            continue
        if role.lower() in TRANSIENT_ROLES:
            transient.append(
                {"name": id_name, "role": role,
                 "ui_name": (e.get("ui_name") or "").strip()}
            )
            continue
        elements.setdefault(id_name, {"role": role})
    return elements, transient


def _collect_unreachable(unreachable_path: Path) -> set[str]:
    """Manual-exemption id_names from a user-provided unreachable.yaml.

    Only this file is read. The manifest's `unresolved` section lists id_name
    TBD entries — those never enter the denominator (excluded at manifest
    build), so reading them here would report a misleading exemption count that
    never matches a denominator key.
    """
    names: set[str] = set()
    data = _load_yaml(unreachable_path)
    if not isinstance(data, dict):
        return names
    for e in data.get("unreachable", []) or []:
        if isinstance(e, dict) and e.get("name"):
            names.add(e["name"])
    return names


def _collect_suite_refs(testdir: Path) -> set[str]:
    """Collect all persistent selector.name from *.suite.yaml files."""
    refs: set[str] = set()
    for sf in sorted(testdir.rglob("*.suite.yaml")):
        data = _load_yaml(sf)
        if isinstance(data, dict):
            _walk_refs(data, refs)
    return refs


def _walk_refs(node, refs: set[str]) -> None:
    if isinstance(node, dict):
        sel = node.get("selector")
        if isinstance(sel, dict):
            n = sel.get("name")
            if isinstance(n, str) and n:
                refs.add(n.strip())
        for v in node.values():
            _walk_refs(v, refs)
    elif isinstance(node, list):
        for v in node:
            _walk_refs(v, refs)


def _is_noise(name: str) -> bool:
    """Filename-like noise (contains '.'). SPI element names never contain '.'."""
    return "." in name


# ── Main ────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(
        description="AT-SPI element coverage gate over element-map (hard 100% target)",
        epilog=(
            "Examples:\n"
            "  python3 cover.py --element-map tests/at/casefile/out/element-map.yaml \\\n"
            "      --testdir tests/at/yaml/\n"
            "  python3 cover.py --element-map tests/at/casefile/out/element-map.yaml \\\n"
            "      --testdir tests/at/yaml/ --coverage-report tests/at/coverage-report.yaml\n"
            "\n"
            "Exit 0 if coverage >= threshold (default 100), 1 otherwise."
        ),
    )
    ap.add_argument("--element-map", required=True, help="element-map.yaml from at-case-authoring")
    ap.add_argument("--testdir", required=True, help="yaml/ dir with *.suite.yaml")
    ap.add_argument("--coverage-report", default="", help="Write coverage-report.yaml")
    ap.add_argument("--unreachable", default="", help="unreachable.yaml (manual exemptions)")
    ap.add_argument("--threshold", type=float, default=100.0, help="Coverage threshold (default 100)")
    args = ap.parse_args()

    testdir = Path(args.testdir)
    if not testdir.is_dir():
        print(f"[FAIL] 测试目录不存在: {testdir}")
        return 1

    elements, transient = _collect_element_map(Path(args.element_map))
    refs = {r for r in _collect_suite_refs(testdir) if not _is_noise(r)}
    unreachable = (
        _collect_unreachable(Path(args.unreachable)) if args.unreachable else set()
    )

    if not elements:
        print(f"[FAIL] element-map 中没有命名元素: {args.element_map}")
        return 1

    # Denominator: persistent named elements minus unreachable exemptions
    denominator = {n for n in elements if n not in unreachable}
    covered = {n for n in denominator if n in refs}
    uncovered = denominator - covered

    cov = round(len(covered) / len(denominator) * 100, 1) if denominator else 100.0
    passed = cov >= args.threshold
    print("=" * 60)
    print("AT-SPI 元素覆盖率门禁 (element-map)")
    print("=" * 60)
    print(f"  命名元素 (element-map) : {len(elements)}")
    print(f"  瞬态菜单项 (排除)     : {len(transient)}")
    print(f"  豁免 (unreachable)     : {len(unreachable)}")
    print(f"  应覆盖 (分母)          : {len(denominator)}")
    print(f"  已覆盖 (分子)          : {len(covered)}")
    print(f"  覆盖率                 : {cov}%  (阈值 {args.threshold}%)")
    print(f"  结果                   : {'PASS' if passed else 'FAIL'}")
    if uncovered:
        print(f"\n  未覆盖元素 ({len(uncovered)}):")
        for n in sorted(uncovered)[:30]:
            info = elements.get(n, {})
            print(f"    - {n}  [{info.get('role','')}] {info.get('ui_name','')}")
        if len(uncovered) > 30:
            print(f"    ... 共 {len(uncovered)} 个，仅显示前 30")
    print("=" * 60)

    if args.coverage_report:
        report = {
            "scan_total": len(elements),
            "transient_items": transient,
            "unreachable": len(unreachable),
            "denominator": len(denominator),
            "covered": len(covered),
            "uncovered": len(uncovered),
            "coverage": cov,
            "passed": passed,
            "uncovered_elements": [
                {"name": n, **elements.get(n, {})} for n in sorted(uncovered)
            ],
        }
        rpath = Path(args.coverage_report)
        rpath.parent.mkdir(parents=True, exist_ok=True)
        with open(rpath, "w", encoding="utf-8") as f:
            yaml.dump(report, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        print(f"Coverage report: {rpath}")

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
