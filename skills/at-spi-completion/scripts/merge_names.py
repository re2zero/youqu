#!/usr/bin/env python3
"""Merge persistent + transient AT-SPI names into the regression baseline.

Combines Phase 1-4 output (pre_scan_ok.yaml) with Phase 5 output
(menu_structure.yaml) into a single expected_names.yaml that is committed
with the app code as the AT-SPI regression baseline.

Usage:
    merge_names.py --input <dir> [--scan-dir <dir>] [--output <path>]

  --input     Directory containing menu_structure.yaml (default: tests/at/spi)
  --scan-dir Directory containing the FRESH scan output (pre_scan_ok.yaml),
             e.g. quality_gate_scan/.  If omitted, reads pre_scan_ok.yaml
             from <input>/ instead (Phase 1 snapshot — not recommended after
             Phase 3 fixes have been applied).
  --output    Target expected_names.yaml path. MUST be inside the target app
             project, e.g. deepin-terminal/tests/at/spi/expected_names.yaml.
             (default: <input>/expected_names.yaml)

Output schema:
    version: '1.0'
    widgets:                # persistent, already-named widgets
      - variable, type, object_name, accessible_name,
        source_file, class_name, line
    transient_elements:     # menus / tr()-sourced items (EN + ZH)
      - menu_var, type, text_en, text_zh, file, line
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def load_yaml(path: Path) -> dict:
    try:
        import yaml
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        sys.exit("PyYAML not installed. Run: pip install pyyaml")
    except FileNotFoundError:
        sys.exit(f"Missing input file: {path}")


def main():
    parser = argparse.ArgumentParser(
        description="Merge persistent + transient AT-SPI names into expected_names.yaml",
    )
    parser.add_argument("--input", "-i", default="tests/at/spi",
                        help="Dir with menu_structure.yaml (default: tests/at/spi)")
    parser.add_argument("--scan-dir",
                        help="Optional dir with fresh pre_scan_ok.yaml "
                             "(e.g. output/quality_gate_scan). "
                             "If omitted, reads from <input>/ instead.")
    parser.add_argument("--output", "-o", default=None,
                        help="Target expected_names.yaml path (default: <input>/expected_names.yaml)")
    args = parser.parse_args()

    in_dir = Path(args.input)
    if args.scan_dir:
        ok_path = Path(args.scan_dir) / "pre_scan_ok.yaml"
    else:
        ok_path = in_dir / "pre_scan_ok.yaml"
    menu_path = in_dir / "menu_structure.yaml"
    if not ok_path.is_file():
        sys.exit(f"Missing {ok_path} — run scan_gaps.py first")
    if not menu_path.is_file():
        sys.exit(f"Missing {menu_path} — run menu_extractor.py first (Phase 5)")

    data = {"version": "1.0", "widgets": [], "transient_elements": []}

    # Persistent: already-named widgets from scan_gaps
    ok = load_yaml(ok_path)
    for w in ok.get("widgets", []):
        data["widgets"].append({
            "variable": w.get("variable", ""),
            "type": w.get("type", ""),
            "object_name": w.get("existing_object_name", ""),
            "accessible_name": w.get("existing_accessible_name", ""),
            "source_file": w.get("source_file", ""),
            "class_name": w.get("class_name", ""),
            "line": w.get("line", 0),
        })

    # Transient: menus / tr()-items from menu_extractor (EN + ZH)
    # Includes both addAction (leaf items) and addMenu (submenu titles).
    # Separators are excluded (they have no text).
    menu = load_yaml(menu_path)
    for menu_group in menu.get("menus", []):
        for it in menu_group.get("items", []):
            if it.get("type") == "separator":
                continue
            if it.get("text_en"):
                data["transient_elements"].append({
                    "menu_var": menu_group.get("menu_var", ""),
                    "type": it.get("type", "addAction"),
                    "text_en": it.get("text_en", ""),
                    "text_zh": it.get("text_zh", ""),
                    "file": it.get("file", ""),
                    "line": it.get("line", 0),
                })

    out_path = Path(args.output) if args.output else in_dir / "expected_names.yaml"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    import yaml
    with open(out_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    n_zh = sum(1 for t in data["transient_elements"] if t["text_zh"])
    print(f"Written: {out_path}")
    print(f"  Persistent widgets: {len(data['widgets'])}")
    print(f"  Transient elements: {len(data['transient_elements'])} "
          f"({n_zh} with ZH translation)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
