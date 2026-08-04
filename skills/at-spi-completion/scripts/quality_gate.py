#!/usr/bin/env python3
"""Quality gate for AT-SPI name coverage validation.

Re-runs scan_gaps.py on the source directory, compares results against
a baseline, and checks coverage threshold, uniqueness, and naming conventions.

Usage:
    python3 quality_gate.py --src <dir> --build <dir> --baseline pre_scan_gaps.yaml
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("quality_gate")


def _load_yaml_or_json(path: str) -> Any:
    """Load a YAML or JSON file."""
    p = Path(path)
    if not p.is_file():
        return None
    try:
        import yaml
        with open(p) as f:
            return yaml.safe_load(f)
    except ImportError:
        pass
    try:
        with open(p) as f:
            return json.load(f)
    except json.JSONDecodeError:
        return None


def _load_gaps(gaps_file: str) -> list[dict]:
    """Load gaps from a pre_scan_gaps.yaml file."""
    data = _load_yaml_or_json(gaps_file)
    if not data:
        return []
    return data.get("gaps", data.get("widgets", []))


def check_uniqueness(gaps_file: str) -> list[str]:
    """Check for duplicate object names across the project."""
    gaps = _load_gaps(gaps_file)
    issues: list[str] = []

    name_counts: dict[str, list[str]] = {}
    for g in gaps:
        name = g.get("existing_object_name", "")
        if not name:
            continue  # Only check existing names, not variable names
        if name not in name_counts:
            name_counts[name] = []
        name_counts[name].append(g.get("source_file", "?"))

    for name, files in name_counts.items():
        if len(files) > 1:
            issues.append(f"Duplicate name '{name}' in {len(files)} files: {', '.join(files[:5])}")

    return issues


def check_conventions(gaps_file: str) -> list[str]:
    """Check naming convention compliance."""
    gaps = _load_gaps(gaps_file)
    issues: list[str] = []

    for g in gaps:
        name = g.get("existing_object_name", "")
        if not name:
            continue  # Gaps have no existing name; skip variable name check

        # Check for Chinese characters
        if any('\u4e00' <= c <= '\u9fff' for c in name):
            issues.append(f"Chinese characters in name '{name}' ({g.get('source_file', '?')})")

        # Check for special characters (only allow alphanumeric and underscore)
        if not all(c.isalnum() or c == '_' for c in name):
            issues.append(f"Special characters in name '{name}' ({g.get('source_file', '?')})")

        # Check max length
        if len(name) > 64:
            issues.append(f"Name too long ({len(name)} chars): '{name}' ({g.get('source_file', '?')})")

        # Check PascalCase (starts with uppercase, no underscores except for separators)
        if name and name[0].islower():
            issues.append(f"Name not PascalCase: '{name}' ({g.get('source_file', '?')})")

    return issues


def run_quality_gate(
    src_dir: str,
    build_dir: str | None = None,
    compile_commands: str | None = None,
    baseline_gaps: str = "pre_scan_gaps.yaml",
    threshold: float = 80.0,
    output_dir: str = ".",
) -> dict:
    """Run quality gate checks.

    Returns:
        Dict with passed, coverage, threshold, and detailed results.
    """
    # Import scan_gaps from the same directory
    script_dir = Path(__file__).parent
    sys.path.insert(0, str(script_dir))
    from scan_gaps import scan_source  # type: ignore

    # Run fresh scan
    scan_output = Path(output_dir) / "quality_gate_scan"
    scan_output.mkdir(parents=True, exist_ok=True)

    result = scan_source(
        src_dir=src_dir,
        build_dir=build_dir,
        compile_commands=compile_commands,
        output_dir=str(scan_output),
    )

    total = len(result.widgets)
    ok_count = len(result.ok_widgets)
    gap_count = len(result.gap_widgets)
    coverage = (ok_count / total * 100) if total else 0.0

    # Load baseline gaps
    baseline = _load_gaps(baseline_gaps)
    baseline_vars: set[str] = set()
    for g in baseline:
        var = g.get("variable", "")
        if var:
            baseline_vars.add(var)

    # Current gap variables
    current_gap_vars: set[str] = {g.variable for g in result.gap_widgets}

    # Fixed gaps = in baseline but not in current
    fixed_gaps = baseline_vars - current_gap_vars
    # New gaps = in current but not in baseline
    new_gaps = current_gap_vars - baseline_vars

    # Uniqueness check on both gaps and ok files (gaps may be empty at 100% coverage)
    current_gaps_file = str(scan_output / "pre_scan_gaps.yaml")
    current_ok_file = str(scan_output / "pre_scan_ok.yaml")
    uniqueness_issues = check_uniqueness(current_gaps_file)
    uniqueness_issues += check_uniqueness(current_ok_file)
    convention_issues = check_conventions(current_gaps_file)
    convention_issues += check_conventions(current_ok_file)

    # Determine pass/fail
    coverage_pass = coverage >= threshold
    new_gaps_pass = len(new_gaps) == 0
    uniqueness_pass = len(uniqueness_issues) == 0
    convention_pass = len(convention_issues) == 0
    passed = coverage_pass and new_gaps_pass and uniqueness_pass and convention_pass

    details_parts: list[str] = []
    if not coverage_pass:
        details_parts.append(f"Coverage {coverage:.1f}% < threshold {threshold:.0f}%")
    if not new_gaps_pass:
        details_parts.append(f"{len(new_gaps)} new gap(s) introduced")
    if not uniqueness_pass:
        details_parts.append(f"{len(uniqueness_issues)} uniqueness issue(s)")
    if not convention_pass:
        details_parts.append(f"{len(convention_issues)} convention issue(s)")

    quality_result = {
        "passed": passed,
        "coverage": round(coverage, 1),
        "threshold": threshold,
        "total_widgets": total,
        "with_names": ok_count,
        "missing_names": gap_count,
        "new_gaps": len(new_gaps),
        "fixed_gaps": len(fixed_gaps),
        "new_gap_list": sorted(new_gaps),
        "fixed_gap_list": sorted(fixed_gaps),
        "uniqueness_issues": uniqueness_issues,
        "convention_issues": convention_issues,
        "details": "; ".join(details_parts) if details_parts else "All checks passed",
    }

    # Write report
    report_path = Path(output_dir) / "quality_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(quality_result, f, indent=2, ensure_ascii=False)
    logger.info("Written %s", report_path)

    return quality_result


def main():
    parser = argparse.ArgumentParser(
        description="Quality gate for AT-SPI name coverage",
    )
    parser.add_argument("--src", required=True, help="Source directory")
    parser.add_argument("--build", help="Build directory (for compile_commands.json)")
    parser.add_argument("--compile-commands", help="Path to compile_commands.json")
    parser.add_argument("--baseline", default="pre_scan_gaps.yaml",
                        help="Baseline gaps YAML (default: pre_scan_gaps.yaml)")
    parser.add_argument("--threshold", type=float, default=80.0,
                        help="Coverage threshold %% (default: 80)")
    parser.add_argument("--output", "-o", default=".",
                        help="Output directory (default: current dir)")
    args = parser.parse_args()

    quality_result = run_quality_gate(
        src_dir=args.src,
        build_dir=args.build,
        compile_commands=args.compile_commands,
        baseline_gaps=args.baseline,
        threshold=args.threshold,
        output_dir=args.output,
    )

    print(f"\nQuality Gate: {'PASS' if quality_result['passed'] else 'FAIL'}")
    print(f"  Coverage: {quality_result['coverage']:.1f}% (threshold: {quality_result['threshold']:.0f}%)")
    print(f"  Total: {quality_result['total_widgets']} widgets")
    print(f"  With names: {quality_result['with_names']}")
    print(f"  Missing names: {quality_result['missing_names']}")
    print(f"  Fixed gaps: {quality_result['fixed_gaps']}")
    print(f"  New gaps: {quality_result['new_gaps']}")
    print(f"  Details: {quality_result['details']}")

    if quality_result["uniqueness_issues"]:
        print(f"\n  Uniqueness issues ({len(quality_result['uniqueness_issues'])}):")
        for issue in quality_result["uniqueness_issues"][:5]:
            print(f"    - {issue}")

    if quality_result["convention_issues"]:
        print(f"\n  Convention issues ({len(quality_result['convention_issues'])}):")
        for issue in quality_result["convention_issues"][:5]:
            print(f"    - {issue}")

    return 0 if quality_result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())