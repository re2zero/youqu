#!/usr/bin/env python3
"""scan_to_atree.py — Convert scanned_ok.yaml to at-tree.yaml (no DISPLAY needed).

Usage:
    python3 scan_to_atree.py <scan_dir> <app_name> [at_tree_output]

Reads scanned_ok.yaml from scan_dir, calls merge_trees([], scan_classes)
to produce a static-only at-tree.yaml, then runs tree-info on it.

Requires: youqu source tree importable (from src.at.scanner.merger).
No DISPLAY, no running application needed.
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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert scanned_ok.yaml to at-tree.yaml (no DISPLAY)"
    )
    parser.add_argument("scan_dir", help="Directory containing scanned_ok.yaml")
    parser.add_argument("app", help="Application name (e.g. deepin-terminal)")
    parser.add_argument(
        "output", nargs="?", default="at-tree.yaml",
        help="Output path for at-tree.yaml"
    )
    args = parser.parse_args()

    scan_dir = Path(args.scan_dir)
    scanned_ok = scan_dir / "scanned_ok.yaml"
    if not scanned_ok.is_file():
        print(f"Error: {scanned_ok} not found")
        sys.exit(1)

    # Load scan results
    scan_classes: list[dict] = []
    for doc in yaml.safe_load_all(scanned_ok.read_text(encoding="utf-8")):
        if doc:
            scan_classes.append(doc)
    print(f"Loaded {len(scan_classes)} scanned classes from {scanned_ok}")

    if not scan_classes:
        print("Warning: no classes found, at-tree will be empty")

    # Import and merge (headless-safe)
    from src.at.scanner.merger import (
        merge_trees,
        write_at_tree_yaml,
        write_element_gaps,
    )

    merged = merge_trees([], scan_classes)
    node_count = len(merged)
    static_count = sum(
        1 for n in _flatten(merged) if n.get("source") == "static"
    )
    print(f"Merged tree: {node_count} root nodes ({static_count} static)")

    # Write at-tree.yaml
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_at_tree_yaml(merged, str(out_path), app_name=args.app)
    print(f"Wrote {out_path}")

    # Write element gaps
    gaps_path = out_path.parent / "element_gaps.yaml"
    write_element_gaps(merged, str(gaps_path), app_name=args.app)
    print(f"Wrote {gaps_path}")


def _flatten(nodes: list[dict]) -> list[dict]:
    flat: list[dict] = []
    for n in nodes:
        flat.append(n)
        flat.extend(_flatten(n.get("children", [])))
    return flat


if __name__ == "__main__":
    main()