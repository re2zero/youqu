#!/usr/bin/env python3
"""Apply AT-SPI fixes to C++ source files based on pre_scan_gaps.yaml.

Reads pre_scan_gaps.yaml and name_map.txt, then for each gap:
1. Opens the source file
2. Finds the insertion point (new expression, setupUi, addAction, etc.)
3. Checks if the missing calls already exist
4. Inserts only the missing calls

Gaps that can't be handled automatically are marked UNSUPPORTED
and should be passed to the LLM for manual fix.

Usage:
    apply_fixes.py pre_scan_gaps.yaml --name-map name_map.txt [--src-dir ...] [--dry-run]

Output: apply_fixes_report.json — per-gap status + summary.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def _load_yaml(path: str) -> dict[str, Any]:
    try:
        import yaml
    except ImportError:
        sys.exit("PyYAML not installed. Run: pip install pyyaml")
    with open(path) as f:
        return yaml.safe_load(f)


def _load_name_map(path: str) -> dict[str, str]:
    """Load name_map.txt into {variable_name: canonical_name}.

    Format per line:
        m_okButton     -> OkButton       # src/a.cpp:42
    """
    result: dict[str, str] = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or "->" not in line:
                continue
            var_part = line.split("->")[0].strip()
            after_arrow = line.split("->")[1].strip()
            name = after_arrow.split("#")[0].strip()
            result[var_part] = name
    return result


# ---------------------------------------------------------------------------
# Pattern matching
# ---------------------------------------------------------------------------

# Patterns for insertion point detection
# m_var = new Type(this);
_PAT_NEW = re.compile(r'(\w+)\s*=\s*new\s+\w+\s*\(')
# ui->setupUi(this);
_PAT_SETUP_UI = re.compile(r'\bui\s*->\s*setupUi\s*\(')
# ->addAction(...)
_PAT_ADD_ACTION = re.compile(r'->\s*addAction\s*\(')
# Existing calls (to check before inserting)
_PAT_OBJ_NAME = re.compile(r'->\s*setObjectName\s*\(')
_PAT_ACC_NAME = re.compile(r'->\s*setAccessibleName\s*\(')

# Types that only support setObjectName (no setAccessibleName)
_NON_WIDGET_SET: frozenset[str] = frozenset({
    "QAction", "QActionGroup", "QShortcut", "QButtonGroup", "DAction",
})


def _is_non_widget(type_name: str) -> bool:
    """Check if a type is NOT a QWidget subclass (no setAccessibleName)."""
    base = type_name.replace(" *", "").replace("&", "").split("<")[0].strip()
    return base in _NON_WIDGET_SET


def _has_existing_call(lines: list[str], var_name: str, call_type: str) -> bool:
    """Check if var_name->setObjectName/setAccessibleName already exists in file."""
    pat = _PAT_OBJ_NAME if call_type == "setObjectName" else _PAT_ACC_NAME
    for line in lines:
        if var_name in line and pat.search(line):
            return True
    return False


def _try_find_impl_file(file_path: Path) -> Path | None:
    """Given a .h file, find the matching .cpp implementation file."""
    if file_path.suffix in (".h", ".hpp", ".hxx"):
        for ext in (".cpp", ".cc", ".cxx"):
            impl = file_path.with_suffix(ext)
            if impl.exists():
                return impl
    return None


def _find_insertion_point(
    lines: list[str], var_name: str, start_line: int = 0,
) -> tuple[int, str] | None:
    """Find the line index (0-based) of the insertion anchor.

    Returns (line_index, prefix) where prefix is either 'ui->' for Ui_*
    patterns or '' for direct member variables.
    Insertion happens on the NEXT line after line_index.
    """
    ui_var = f"ui->{var_name}"
    search_end = len(lines)

    for i in range(start_line, search_end):
        line = lines[i]

        # (a) m_var = new Type(this) — direct member pointer
        if var_name in line and "=" in line and "new" in line:
            m = _PAT_NEW.search(line)
            if m and m.group(1) == var_name:
                return (i, "")

        # (b) ui->var = new Type(this) — Ui_* form member
        if ui_var in line and "=" in line and "new" in line:
            return (i, "ui->")

        # (c) ui->setupUi(this) — insert after setupUi with ui->varName prefix
        if ui_var in line or "ui->setupUi" in line:
            if _PAT_SETUP_UI.search(line):
                return (i, "ui->")
            if i > 0 and _PAT_SETUP_UI.search(lines[i - 1]):
                return (i - 1, "ui->")

        # (d) ->addAction(...) — var is the menu/action object
        if var_name in line and "addAction" in line:
            if _PAT_ADD_ACTION.search(line):
                return (i, "")

        # (e) new QAction(...) or new QShortcut(...)
        if var_name in line and "new" in line:
            if "QAction" in line or "QShortcut" in line:
                return (i, "")

    return None


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def apply_fixes(
    gaps_file: str,
    name_map_file: str,
    src_dir: str = ".",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Apply fixes for all gaps in pre_scan_gaps.yaml."""
    gaps_data = _load_yaml(gaps_file)
    gaps = gaps_data.get("gaps", gaps_data.get("widgets", []))
    name_map = _load_name_map(name_map_file)

    fixed = 0
    unsupported = 0
    skipped = 0
    already_ok = 0
    results: list[dict[str, Any]] = []
    src_root = Path(src_dir)

    for gap in gaps:
        var = gap.get("variable", "")
        source_file = gap.get("source_file", "")
        type_name = gap.get("type", "")
        has_obj = gap.get("has_object_name", False)
        has_acc = gap.get("has_accessible_name", False)
        existing_obj = gap.get("existing_object_name", "")
        existing_acc = gap.get("existing_accessible_name", "")

        # Skip: missing data
        if not var or not source_file:
            skipped += 1
            results.append({"variable": var, "file": source_file, "status": "skipped", "reason": "missing variable or source_file"})
            continue

        # Skip: no canonical name mapping
        canonical = name_map.get(var, "")
        if not canonical:
            unsupported += 1
            results.append({"variable": var, "file": source_file, "status": "unsupported", "reason": "no name mapping"})
            continue

        # Determine what needs to be added
        needs_object_name = not has_obj
        needs_accessible_name = not has_acc and not _is_non_widget(type_name)
        if not needs_object_name and not needs_accessible_name:
            already_ok += 1
            results.append({"variable": var, "file": source_file, "status": "already_ok"})
            continue

        # Resolve file path
        file_path = src_root / source_file
        if not file_path.exists():
            file_path = Path(source_file)
            if not file_path.exists():
                unsupported += 1
                results.append({"variable": var, "file": source_file, "status": "unsupported", "reason": "file not found"})
                continue

        content = file_path.read_text()
        lines = content.split("\n")

        # Search for insertion point in this file, then try .cpp
        result = _find_insertion_point(lines, var, 0)
        insert_idx = None
        prefix = ""
        if result is not None:
            insert_idx, prefix = result
        else:
            impl_path = _try_find_impl_file(file_path)
            if impl_path and impl_path.exists():
                impl_content = impl_path.read_text()
                impl_lines = impl_content.split("\n")
                result = _find_insertion_point(impl_lines, var, 0)
                if result is not None:
                    insert_idx, prefix = result
                    file_path = impl_path
                    lines = impl_lines

        if insert_idx is None:
            unsupported += 1
            results.append({"variable": var, "file": source_file, "status": "unsupported", "reason": "no insertion point found"})
            continue

        # Determine indentation from the insertion line
        indent = ""
        if insert_idx < len(lines):
            m = re.match(r"^(\s*)", lines[insert_idx])
            if m:
                indent = m.group(1)

        # Build the full expression prefix: "ui->nameEdit->" or "m_nameEdit->"
        call_prefix = f"{prefix}{var}->"

        obj_name = existing_obj if existing_obj else canonical
        acc_name = existing_acc if existing_acc else canonical
        insert_lines: list[str] = []

        if needs_object_name:
            call = f'{indent}{call_prefix}setObjectName("{obj_name}");'
            if not _has_existing_call(lines, var, "setObjectName"):
                insert_lines.append(call)

        if needs_accessible_name:
            call = f'{indent}{call_prefix}setAccessibleName("{acc_name}");'
            if not _has_existing_call(lines, var, "setAccessibleName"):
                insert_lines.append(call)

        if not insert_lines:
            already_ok += 1
            results.append({"variable": var, "file": source_file, "status": "already_ok", "reason": "calls already exist"})
            continue

        # Insert calls after the insertion line (no blank line added — the
        # caller's code already has the correct spacing between statements).
        insert_pos = insert_idx + 1
        if dry_run:
            preview = "\n".join(f"  + {l}" for l in insert_lines)
            print(f"  [DRY-RUN] {source_file}: insert after line {insert_idx + 1}")
            print(f"            {preview}")
        else:
            for il in reversed(insert_lines):
                lines.insert(insert_pos, il)
            file_path.write_text("\n".join(lines))

        fixed += 1
        results.append({"variable": var, "file": source_file, "status": "fixed", "inserted_lines": len(insert_lines), "inserted_after_line": insert_idx + 1})

    return {
        "fixed": fixed, "unsupported": unsupported, "skipped": skipped,
        "already_ok": already_ok, "total": len(gaps), "results": results,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Apply AT-SPI fixes to C++ source files",
    )
    parser.add_argument("gaps_file",
                        help="Path to pre_scan_gaps.yaml")
    parser.add_argument("--name-map", "-n", default="name_map.txt",
                        help="Path to name_map.txt (default: name_map.txt)")
    parser.add_argument("--src-dir", "-s", default=".",
                        help="Source root directory (default: current dir)")
    parser.add_argument("--dry-run", "-d", action="store_true",
                        help="Print what would be done without modifying files")
    parser.add_argument("--output", "-o", default="apply_fixes_report.json",
                        help="Output report path (default: apply_fixes_report.json)")
    args = parser.parse_args()

    if not Path(args.gaps_file).is_file():
        sys.exit(f"Gaps file not found: {args.gaps_file}")
    if not Path(args.name_map).is_file():
        sys.exit(f"Name map file not found: {args.name_map}")

    result = apply_fixes(
        args.gaps_file, args.name_map,
        src_dir=args.src_dir, dry_run=args.dry_run,
    )

    print(f"\n{'=' * 50}")
    print(f"Apply Fixes Report")
    print(f"{'=' * 50}")
    print(f"  Total gaps:     {result['total']}")
    print(f"  Fixed:          {result['fixed']}  ✅")
    print(f"  Unsupported:    {result['unsupported']}  ❌ (need LLM)")
    print(f"  Already OK:     {result['already_ok']}  ⚠️")
    print(f"  Skipped:        {result['skipped']}  ⏭️")
    print(f"  Coverage:       {result['fixed'] / max(result['total'], 1) * 100:.0f}%")
    print()

    report_path = Path(args.output)
    with open(report_path, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"Report written: {report_path}")

    if result["unsupported"] > 0:
        print(f"\n⚠️ {result['unsupported']} gap(s) could not be auto-fixed.")
        print("   Pass them to the LLM with: apply_fixes_report.json")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())