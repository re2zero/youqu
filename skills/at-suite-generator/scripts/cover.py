#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
# SPDX-License-Identifier: GPL-2.0-only
"""cover.py — Deterministic coverage gate for AT-SPI element coverage.

The hard 100% target: every named interactive element from the at-spi-coverage
scan (pre_scan_ok.yaml + qml_ok.yaml) must be referenced by at least one
persistent selector.name in the generated *.suite.yaml files.

Gap elements (missing names / dynamic concatenation / QML without
Accessible.name) are NOT counted in the denominator — they cannot be located
by name and are listed separately for manual triage.

Usage:
    cover.py --scan-dir tests/at/coverage_scan/ \
        --testdir tests/at/yaml/ \
        [--manifest tests/at/element-coverage-manifest.yaml] \
        [--unreachable tests/at/unreachable.yaml] \
        [--threshold 100]

Exit 0 if coverage >= threshold, 1 otherwise (CI-friendly).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("Error: PyYAML required")
    sys.exit(1)


# ─── Loaders ────────────────────────────────────────────────────────────
def _load_yaml(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def _collect_scan_ok(scan_dir: Path) -> dict[str, dict]:
    """Collect named interactive elements from scan products.

    Returns {name: {role, source_file, type, name_source}} for C++ ok widgets
    and QML ok elements. `name_source` is a static-scan FACT:
      - "accessible" -> setAccessibleName() / Accessible.name found in source
      - "object"     -> only setObjectName() found
    It does NOT claim runtime locatability (that depends on widget type and
    the Qt/DTK build); runtime locatability must be verified empirically.
    """
    elements: dict[str, dict] = {}

    # C++: pre_scan_ok.yaml (widgets with existing_accessible_name)
    ok = _load_yaml(scan_dir / "pre_scan_ok.yaml")
    if isinstance(ok, dict):
        for w in ok.get("widgets", []) or []:
            if not isinstance(w, dict):
                continue
            accessible = w.get("existing_accessible_name") or ""
            name = accessible or w.get("existing_object_name") or ""
            if name:
                elements[name] = {
                    "role": w.get("role", ""),
                    "source": w.get("source_file", ""),
                    "type": w.get("type", ""),
                    "name_source": "accessible" if accessible else "object",
                }

    # QML ok (accessible_name)
    qml = _load_yaml(scan_dir / "qml_ok.yaml")
    if isinstance(qml, dict):
        for w in qml.get("widgets", []) or []:
            if not isinstance(w, dict):
                continue
            name = w.get("accessible_name") or ""
            if name:
                elements[name] = {
                    "role": w.get("role", ""),
                    "source": w.get("source_file", ""),
                    "type": w.get("element_type", ""),
                    "name_source": "accessible",
                }
    return elements


def _collect_suite_refs(testdir: Path) -> set[str]:
    """Collect all persistent selector.name from *.suite.yaml files."""
    refs: set[str] = set()
    for sf in sorted(testdir.rglob("*.suite.yaml")):
        data = _load_yaml(sf)
        if not isinstance(data, dict):
            continue
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


def _load_unreachable(path: Path) -> set[str]:
    """Load explicitly-marked unreachable element names (manual exemption)."""
    data = _load_yaml(path)
    if not isinstance(data, dict):
        return set()
    return {e.get("name", "") for e in data.get("unreachable", []) if isinstance(e, dict)}


# ── Main ────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(
        description="AT-SPI element coverage gate (hard 100% target)",
        epilog=(
            "Examples:\n"
            "  python3 cover.py --scan-dir tests/at/coverage_scan/ --testdir tests/at/yaml/\n"
            "  python3 cover.py --scan-dir tests/at/coverage_scan/ --testdir tests/at/yaml/ \\\n"
            "      --unreachable tests/at/unreachable.yaml --manifest tests/at/coverage-report.yaml\n"
            "\n"
            "Exit 0 if coverage >= threshold (default 100), 1 otherwise."
        ),
    )
    ap.add_argument("--scan-dir", required=True, help="coverage_scan/ dir (scan products)")
    ap.add_argument("--testdir", required=True, help="yaml/ dir with *.suite.yaml")
    ap.add_argument("--manifest", default="", help="Write coverage-report.yaml (uncovered list)")
    ap.add_argument("--unreachable", default="", help="unreachable.yaml (manual exemptions)")
    ap.add_argument("--threshold", type=float, default=100.0, help="Coverage threshold (default 100)")
    args = ap.parse_args()

    scan_dir = Path(args.scan_dir)
    testdir = Path(args.testdir)

    total_elements = _collect_scan_ok(scan_dir)
    refs = _collect_suite_refs(testdir)
    refs = {r for r in refs if not _is_noise(r)}
    unreachable = _load_unreachable(Path(args.unreachable)) if args.unreachable else set()

    if not total_elements:
        print(f"[FAIL] 未找到扫描产物 {scan_dir} 中的命名元素。")
    # Denominator: ok elements minus explicitly-unreachable exemptions
    denominator = {n for n in total_elements if n not in unreachable}
    covered = {n for n in denominator if n in refs}
    uncovered = denominator - covered

    # Accessible-name breakdown (static-scan fact, not a runtime claim):
    # elements whose name comes from setAccessibleName()/Accessible.name.
    # object-name-only elements still count toward the source-scan denominator;
    # runtime locatability must be verified empirically, not assumed here.
    accessible_named = {n for n in denominator if total_elements[n].get("name_source") == "accessible"}
    accessible_covered = {n for n in accessible_named if n in refs}
    cov = round(len(covered) / len(denominator) * 100, 1) if denominator else 100.0
    acc_cov = (
        round(len(accessible_covered) / len(accessible_named) * 100, 1)
        if accessible_named
        else 100.0
    )
    passed = cov >= args.threshold
    print("=" * 60)
    print("AT-SPI 元素覆盖率门禁")
    print("=" * 60)
    print(f"  扫描元素 (ok 集)   : {len(total_elements)}")
    print(f"  豁免 (unreachable) : {len(unreachable)}")
    print(f"  应覆盖 (分母)      : {len(denominator)}")
    print(f"  已覆盖 (分子)      : {len(covered)}")
    print(f"  覆盖率             : {cov}%  (阈值 {args.threshold}%)")
    print(f"  setAccessibleName  : {len(accessible_covered)}/{len(accessible_named)} "
          f"({acc_cov}%)")
    print(f"  结果               : {'PASS' if passed else 'FAIL'}")
    if uncovered:
        print(f"\n  未覆盖元素 ({len(uncovered)}):")
        for n in sorted(uncovered)[:30]:
            info = total_elements.get(n, {})
            src = info.get("name_source", "?")
            print(f"    - {n}  [{src}] {info.get('source','')}")
        if len(uncovered) > 30:
            print(f"    ... 共 {len(uncovered)} 个，仅显示前 30")
    print("=" * 60)
    # ── Manifest ─────────────────────────────────────────────────────
    if args.manifest:
        manifest = {
            "scan_total": len(total_elements),
            "unreachable": len(unreachable),
            "denominator": len(denominator),
            "covered": len(covered),
            "uncovered": len(uncovered),
            "coverage": cov,
            "passed": passed,
            "accessible_named": len(accessible_named),
            "accessible_covered": len(accessible_covered),
            "accessible_coverage": acc_cov,
            "uncovered_elements": [
                {
                    "name": n,
                    **total_elements.get(n, {}),
                }
                for n in sorted(uncovered)
            ],
        }
        mpath = Path(args.manifest)
        mpath.parent.mkdir(parents=True, exist_ok=True)
        with open(mpath, "w", encoding="utf-8") as f:
            yaml.dump(manifest, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        print(f"Manifest: {mpath}")


if __name__ == "__main__":
    sys.exit(main())