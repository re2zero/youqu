#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
# SPDX-License-Identifier: GPL-2.0-only
"""element_manifest.py — Build the authoritative element manifest from scan products.

Reads at-spi-coverage scan products (pre_scan_ok.yaml + qml_ok.yaml) and emits
a single element-coverage-manifest.yaml listing every named interactive
element. This is the hard-100% denominator and the selector-name whitelist
that generation sub-agents must reference.

Usage:
    element_manifest.py --scan-dir tests/at/coverage_scan/ \
        --output tests/at/element-coverage-manifest.yaml

Output:
    element-coverage-manifest.yaml:
        version, scan_total, elements: {name: {role, source, type}}
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


def _load_yaml(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def _collect_scan_ok(scan_dir: Path) -> dict[str, dict]:
    """Collect named interactive elements from C++ ok + QML ok products."""
    elements: dict[str, dict] = {}

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
                    # FACT, not inference: which source produced the name.
                    #   accessible -> setAccessibleName() was found in source
                    #   object     -> only setObjectName() was found
                    # This is a static-scan fact. It does NOT claim runtime
                    # locatability: how an element resolves at runtime depends
                    # on widget type (QAction's objectName is a valid locator;
                    # a QWidget's is not) and the Qt/DTK build. Downstream
                    # steps must verify runtime locatability empirically, not
                    # assume it from this field alone.
                    "name_source": "accessible" if accessible else "object",
                }

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


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Build element manifest from scan products",
        epilog=(
            "Example:\n"
            "  python3 element_manifest.py --scan-dir tests/at/coverage_scan/ \\\n"
            "      --output tests/at/element-coverage-manifest.yaml"
        ),
    )
    ap.add_argument("--scan-dir", required=True, help="coverage_scan/ dir")
    ap.add_argument("--output", required=True, help="Output manifest path")
    args = ap.parse_args()

    scan_dir = Path(args.scan_dir)
    elements = _collect_scan_ok(scan_dir)
    if not elements:
        print(f"Error: no named elements found in {scan_dir} "
              f"(check pre_scan_ok.yaml / qml_ok.yaml)")
        return 1

    manifest = {
        "scan_total": len(elements),
        "total": len(elements),
        "elements": elements,
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        yaml.dump(manifest, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    print(f"Wrote {out} ({len(elements)} elements)")
    return 0


if __name__ == "__main__":
    sys.exit(main())