#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
# SPDX-License-Identifier: GPL-2.0-only
"""element_manifest.py — Build the authoritative element manifest from element-map.yaml.

This skill does NOT run a source scan (at-spi-coverage). The runtime element
names come from at-case-authoring's element-map.yaml, whose `id_name` is the
runtime AT-SPI name (setAccessibleName / acTextDefine macros / QAction text).
That is the authority for the 100% denominator and the selector-name whitelist
— a static libclang scan cannot resolve names produced via helper functions
(Utils::setAccessibility) or macros, so it is NOT used here.

Reads element-map.yaml and emits:
    element-coverage-manifest.yaml:
        elements:       {name: {role, ui_name, desc}}   (100% denominator, persistent)
        transient_items: [{name, role, ui_name, desc}]  (menu/menu-item, excluded)
        unresolved:      [{name, role, ui_name, desc, reason}] (id_name TBD/empty)

Naming:
  - `unresolved` = id_name TBD/empty in element-map. These never enter the
    denominator (runtime cannot locate by name). They are documented here for
    the human to fill in; they are NOT the same as cover.py's `unreachable.yaml`
    manual exemptions. The two terms must not be conflated.
  - `transient_items` = menu / menu item roles, excluded from denominator,
    located at runtime by dtk_main_menu text.

Usage:
    element_manifest.py --element-map tests/casefile/out/element-map.yaml \
        --output tests/at/element-coverage-manifest.yaml
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


def _load_yaml(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Build element manifest from element-map.yaml")
    ap.add_argument("--element-map", required=True, help="element-map.yaml from at-case-authoring")
    ap.add_argument("--output", required=True, help="Output manifest path")
    args = ap.parse_args()

    em_path = Path(args.element_map)
    em = _load_yaml(em_path)
    if not isinstance(em, dict) or not em.get("elements"):
        print(f"Error: no elements in {em_path}")
        return 1

    elements: dict[str, dict] = {}
    transient: list[dict] = []
    unresolved: list[dict] = []
    seen_ids: set[str] = set()
    for e in em["elements"]:
        if not isinstance(e, dict):
            continue
        id_name = (e.get("id_name") or "").strip()
        role = (e.get("role") or "").strip()
        ui_name = (e.get("ui_name") or "").strip()
        desc = (e.get("desc") or "").strip()
        if not id_name or id_name in ("TBD", "待补充"):
            unresolved.append(
                {
                    # id_name is literally "TBD" — use ui_name so entries are
                    # distinguishable (a shared "TBD" name collapses the set).
                    "name": ui_name or id_name,
                    "role": role,
                    "ui_name": ui_name,
                    "desc": desc,
                    "reason": "id_name 未填 (TBD)，运行时无法按名定位",
                }
            )
            continue
        if role.lower() in TRANSIENT_ROLES:
            transient.append(
                {"name": id_name, "role": role, "ui_name": ui_name, "desc": desc}
            )
            continue
        if id_name in seen_ids:
            continue  # element-map may list the same id_name for several ui_names
        seen_ids.add(id_name)
        elements[id_name] = {
            "role": role,
            "ui_name": ui_name,
            "desc": desc,
        }

    manifest = {
        "version": "1.0",
        "source": "at-case-authoring:element-map.yaml",
        "scan_total": len(elements),
        "elements": elements,
        "transient_items": transient,
        "unresolved": unresolved,
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        yaml.dump(manifest, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    print(f"Wrote {out}")
    print(f"  elements (denominator): {len(elements)}")
    print(f"  transient (menu, excluded): {len(transient)}")
    print(f"  unresolved (TBD/empty id_name): {len(unresolved)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
