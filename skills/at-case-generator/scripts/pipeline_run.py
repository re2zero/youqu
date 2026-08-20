#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
# SPDX-License-Identifier: GPL-2.0-only
"""pipeline_run.py — Unified deterministic pipeline for AT-SPI case generation.

Runs all deterministic (non-AI) steps of the pipeline in one shot:
  parse → docs → plan → scan → dump → merge → tree-info → prep

Usage:
    pipeline_run.py --app deepin-reader --src /path/to/source \\
        --xlsx tests/at/casefile/用例.xlsx \\
        --binary /usr/bin/deepin-reader \\
        --output tests/at/

    pipeline_run.py --app deepin-terminal --src /path/to/source \\
        --output tests/at/           # no xlsx (feature-driven mode)

    pipeline_run.py --app deepin-reader --at-tree tests/at/at-tree.yaml \\
        --xlsx tests/at/casefile/用例.xlsx \\
        --output tests/at/           # reuse existing at-tree, skip scan/dump/merge

Inputs:
    --xlsx / --csv     xlsx/csv test case document (optional, feature-driven mode)
    --src              source code directory for static scan (optional)
    --binary           app binary for runtime dump (optional, requires DISPLAY)
    --at-tree          existing at-tree.yaml (skip scan/dump/merge, optional)

Outputs:
    tests/at/cases_raw.yaml         (from parse, or empty if no xlsx)
    tests/at/plan.yaml              (from plan, or minimal if no xlsx)
    tests/at/suite-cases.yaml       (from plan)
    tests/at/at-tree.yaml           (from merge)
    tests/at/at-tree-annotated.yaml (from tree-info)
    tests/at/modules/_summary.json  (from prep)
    tests/at/modules/*.input.json   (per-module, for LLM)
"""

from __future__ import annotations

import argparse
import os

import subprocess

from pathlib import Path


# ─── Helpers ───────────────────────────────────────────────────────────


def _run(cmd: list[str], cwd: str | None = None, label: str = "") -> bool:
    """Run a command, print status. Returns True on success."""
    label_str = f" [{label}]" if label else ""
    print(f"  → {' '.join(cmd)}{label_str}")
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ✗ FAILED (exit {result.returncode})")
        if result.stderr.strip():
            for line in result.stderr.strip().splitlines()[-5:]:
                print(f"    stderr: {line}")
        return False
    if result.stdout.strip():
        last = result.stdout.strip().splitlines()[-1]
        print(f"    {last}")
    return True


def _youqu(cmd: list[str], cwd: str | None = None, label: str = "") -> bool:
    """Run a youqu at subcommand."""
    return _run(["youqu", "at"] + cmd, cwd=cwd, label=label)


def _file_exists(path: str) -> bool:
    p = Path(path)
    return p.is_file() and p.stat().st_size > 0


# ─── Stages ────────────────────────────────────────────────────────────


def stage_parse(xlsx: str | None, csv: str | None, output_dir: str) -> str | None:
    """Parse xlsx/csv → cases_raw.yaml."""
    source = xlsx or csv
    if not source:
        return None

    cases_raw = os.path.join(output_dir, "cases_raw.yaml")
    if _file_exists(cases_raw) and not args.force:
        print(f"  ⏩ cases_raw.yaml exists, skip parse (use --force to redo)")
        return cases_raw

    cmd = ["parse", "--input", source, "--output", cases_raw]
    if _youqu(cmd, label="parse"):
        return cases_raw
    return None


def stage_docs(xlsx: str | None, csv: str | None, app: str, output_dir: str) -> str | None:
    """Import help manual chapters (requires xlsx)."""
    if not xlsx and not csv:
        return None

    docs_dir = os.path.join(output_dir, "docs")
    if os.path.isdir(docs_dir) and not args.force:
        print(f"  ⏩ docs/ exists, skip docs (use --force to redo)")
        return docs_dir

    cmd = ["docs", app, "--output", docs_dir]
    if _youqu(cmd, label="docs"):
        return docs_dir
    return None

def stage_plan(output_dir: str, app: str) -> str | None:
    """Generate plan.yaml from cases_raw + docs → module-by-module plan."""
    cases_raw = os.path.join(output_dir, "cases_raw.yaml")
    if not _file_exists(cases_raw):
        print(f"  ⚠ cases_raw.yaml not found, skip plan")
        return None

    plan_yaml = os.path.join(output_dir, "plan.yaml")
    if _file_exists(plan_yaml) and not args.force:
        print(f"  ⏩ plan.yaml exists, skip plan (use --force to redo)")
        return plan_yaml

    docs_dir = os.path.join(output_dir, "docs")
    cmd = ["plan", "--cases", cases_raw, "--app", app, "--output", output_dir]
    if os.path.isdir(docs_dir):
        cmd += ["--docs", docs_dir]
    if _youqu(cmd, label="plan"):
        return plan_yaml
    return None


def stage_scan(src_dir: str | None, app: str, output_dir: str) -> str | None:
    """Static source code scan → scanned_ok.yaml + element_gaps.yaml."""
    if not src_dir:
        return None

    scan_dir = os.path.join(output_dir, "scan")
    if os.path.isdir(scan_dir) and not args.force:
        print(f"  ⏩ scan/ exists, skip scan (use --force to redo)")
        return scan_dir

    cmd = ["scan", "--src", src_dir, "--app", app, "--output", scan_dir]
    if _youqu(cmd, label="scan"):
        return scan_dir
    return None


def stage_dump(binary: str | None, app: str, output_dir: str) -> str | None:
    """Runtime AT-SPI dump (requires DISPLAY + app binary)."""
    if not binary:
        return None
    if not os.environ.get("DISPLAY"):
        print(f"  ⚠ No DISPLAY, skip runtime dump")
        return None

    dump_dir = os.path.join(output_dir, "dump")
    if os.path.isdir(dump_dir) and not args.force:
        print(f"  ⏩ dump/ exists, skip dump (use --force to redo)")
        return dump_dir

    cmd = ["dump", "dtk", "--app", app, "--launch", binary, "--output", dump_dir]
    if _youqu(cmd, label="dump"):
        return dump_dir
    return None


def stage_merge(scan_dir: str | None, dump_dir: str | None, output_dir: str) -> str | None:
    """Merge scan + dump → at-tree.yaml (or headless fallback)."""
    at_tree = os.path.join(output_dir, "at-tree.yaml")
    if _file_exists(at_tree) and not args.force:
        print(f"  ⏩ at-tree.yaml exists, skip merge (use --force to redo)")
        return at_tree

    # Headless fallback: scan_to_atree.py
    if not dump_dir and scan_dir:
        scanned_ok = os.path.join(scan_dir, "scanned_ok.yaml")
        if _file_exists(scanned_ok):
            print(f"  → No dump data, using headless static merge")
            # Use scan_to_atree.py
            script = os.path.join(
                os.path.dirname(__file__), "scan_to_atree.py"
            )
            if _run(
                ["python3", script, scan_dir, args.app, at_tree],
                label="scan_to_atree",
            ):
                return at_tree
            return None

    if not scan_dir and not dump_dir:
        print(f"  ⚠ No scan or dump data, skip merge")
        return None

    cmd = ["merge", "--output", output_dir]
    if scan_dir:
        cmd += ["--scan", scan_dir]
    if dump_dir:
        cmd += ["--record", dump_dir]
    if _youqu(cmd, label="merge"):
        return at_tree
    return None


def stage_tree_info(at_tree: str, output_dir: str) -> str | None:
    """Generate at-tree-annotated.yaml from at-tree.yaml."""
    if not at_tree or not _file_exists(at_tree):
        return None

    annotated = os.path.join(output_dir, "at-tree-annotated.yaml")
    if _file_exists(annotated) and not args.force:
        print(f"  ⏩ at-tree-annotated.yaml exists, skip tree-info (use --force to redo)")
        return annotated

    cmd = ["tree-info", "--at-tree", at_tree, "--output", annotated, "--format", "yaml"]
    if _youqu(cmd, label="tree-info"):
        return annotated
    return None


def stage_prep(output_dir: str) -> str | None:
    """Split cases_raw.yaml into per-module input.json files."""
    plan_yaml = os.path.join(output_dir, "plan.yaml")
    cases_raw = os.path.join(output_dir, "cases_raw.yaml")
    modules_dir = os.path.join(output_dir, "modules")

    if not _file_exists(plan_yaml):
        print(f"  ⚠ plan.yaml not found, skip module split")
        return None
    if not _file_exists(cases_raw):
        print(f"  ⚠ cases_raw.yaml not found, skip module split")
        return None

    summary_path = os.path.join(modules_dir, "_summary.json")
    if _file_exists(summary_path) and not args.force:
        print(f"  ⏩ modules/ exists, skip prep (use --force to redo)")
        return modules_dir

    script = os.path.join(os.path.dirname(__file__), "pipeline_prep.py")
    if _run(
        [
            "python3", script,
            "--plan", plan_yaml,
            "--cases", cases_raw,
            "--output", modules_dir,
            "--app", args.app,
        ],
        label="pipeline_prep",
    ):
        return modules_dir
    return None


def stage_validate_gate(at_tree_annotated: str | None, output_dir: str) -> bool:
    """Run Gate 1 validation (at-tree annotation completeness)."""
    if not at_tree_annotated or not _file_exists(at_tree_annotated):
        return True  # Not available yet, skip

    # Gate 1 needs element_gaps.yaml
    scan_dir = os.path.join(output_dir, "scan")
    element_gaps = os.path.join(scan_dir, "element_gaps.yaml")
    if not _file_exists(element_gaps):
        element_gaps = os.path.join(output_dir, "element_gaps.yaml")
    if not _file_exists(element_gaps):
        print(f"  ⚠ element_gaps.yaml not found, skip Gate 1")
        return True

    cmd = [
        "validate", "--gate", "1",
        "--at-tree-annotated", at_tree_annotated,
        "--element-gaps", element_gaps,
    ]
    return _youqu(cmd, label="gate 1")


# ─── Main ──────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run all deterministic AT-SPI pipeline steps in one shot"
    )
    parser.add_argument("--app", required=True, help="Application name")
    parser.add_argument("--src", help="Source code directory for static scan")
    parser.add_argument("--binary", help="App binary path for runtime dump")
    parser.add_argument("--xlsx", help="xlsx test case file")
    parser.add_argument("--csv", help="csv test case file")
    parser.add_argument("--output", required=True, help="Output directory (e.g. tests/at/)")
    parser.add_argument("--at-tree", help="Existing at-tree.yaml (skip scan/dump/merge)")
    parser.add_argument("--force", action="store_true", help="Redo all stages even if outputs exist")
    parser.add_argument("--skip-parse", action="store_true", help="Skip parse step")
    parser.add_argument("--skip-scan", action="store_true", help="Skip source scan")
    parser.add_argument("--skip-dump", action="store_true", help="Skip runtime dump")
    parser.add_argument("--skip-merge", action="store_true", help="Skip merge")
    parser.add_argument("--skip-tree-info", action="store_true", help="Skip tree-info")
    parser.add_argument("--skip-prep", action="store_true", help="Skip module split")
    parser.add_argument("--headless", action="store_true", help="Equivalent to --skip-dump")
    global args
    args = parser.parse_args()

    output_dir = args.output
    os.makedirs(output_dir, exist_ok=True)

    print(f"=== Pipeline Run: {args.app} ===")
    print(f"  Output: {output_dir}")
    print(f"  Mode: {'headless' if args.headless else 'standard'}")
    print()


    # ── Stage 0: Parse ────────────────────────────────────────────────
    if not args.skip_parse and (args.xlsx or args.csv):
        print("[Stage 0/8] Parse xlsx/csv → cases_raw.yaml")
        cases_raw = stage_parse(args.xlsx, args.csv, output_dir)
        if cases_raw:
            print(f"  ✓ cases_raw.yaml: {cases_raw}")
        else:
            print(f"  ⚠ Parse produced no output")
        print()

    # ── Stage 0.5: Docs ───────────────────────────────────────────────
    if not args.skip_parse and (args.xlsx or args.csv):
        print("[Stage 0.5/8] Import help manual docs")
        docs_dir = stage_docs(args.xlsx, args.csv, args.app, output_dir)
        if docs_dir:
            print(f"  ✓ docs: {docs_dir}")
        print()

    # ── Stage 0.75: Plan ──────────────────────────────────────────────
    if not args.skip_parse and (args.xlsx or args.csv):
        print("[Stage 0.75/8] Generate module plan (plan.yaml)")
        plan_yaml = stage_plan(output_dir, args.app)
        if plan_yaml:
            print(f"  ✓ plan.yaml: {plan_yaml}")
        else:
            print(f"  ⚠ Plan not generated")
        print()

    # ── Stage 1: Scan ─────────────────────────────────────────────────
    if not args.skip_scan and args.src:
        print("[Stage 1/8] Static source scan")
        scan_dir = stage_scan(args.src, args.app, output_dir)
        print()

    # ── Stage 2: Dump ─────────────────────────────────────────────────
    if not args.skip_dump and not args.headless:
        print("[Stage 2/8] Runtime AT-SPI dump")
        dump_dir = stage_dump(args.binary, args.app, output_dir)
        print()

    # ── Stage 3: Merge ────────────────────────────────────────────────
    if not args.skip_merge:
        print("[Stage 3/8] Merge scan + dump → at-tree.yaml")
        scan_dir = os.path.join(output_dir, "scan") if os.path.isdir(os.path.join(output_dir, "scan")) else None
        dump_dir = os.path.join(output_dir, "dump") if os.path.isdir(os.path.join(output_dir, "dump")) else None
        at_tree = args.at_tree or stage_merge(scan_dir, dump_dir, output_dir)
        if at_tree:
            print(f"  ✓ at-tree.yaml: {at_tree}")
        print()

    # ── Stage 4: Tree info ────────────────────────────────────────────
    if not args.skip_tree_info:
        print("[Stage 4/8] Generate at-tree-annotated.yaml")
        at_tree = args.at_tree or os.path.join(output_dir, "at-tree.yaml")
        annotated = stage_tree_info(at_tree, output_dir)
        if annotated:
            print(f"  ✓ at-tree-annotated.yaml: {annotated}")
        print()

    # ── Stage 5: Validate Gate 1 ──────────────────────────────────────
    print("[Stage 5/8] Gate 1 validation (annotation completeness)")
    annotated = os.path.join(output_dir, "at-tree-annotated.yaml")
    stage_validate_gate(annotated if _file_exists(annotated) else None, output_dir)
    print()

    # ── Stage 6: Module split ────────────────────────────────────────
    if not args.skip_prep:
        print("[Stage 6/8] Module split (pipeline_prep.py)")
        stage_prep(output_dir)
        print()

    # ── Summary ───────────────────────────────────────────────────────
    print("=" * 60)
    print("Pipeline complete. Next steps:")
    print()
    print("  Phase 2 (AI):")
    print("    For each modules/*.input.json, run LLM mapping → *.output.json")
    print("    Use the stage-3-mapping reference for sub-agent instructions.")
    print()
    print("  Phase 3 (Script):")
    print("    pipeline_assemble.py --modules tests/at/modules/ \\")
    print("        --output tests/at/ --at-tree tests/at/at-tree.yaml")
    print()
    print("  Outputs:")
    for path in sorted(Path(output_dir).iterdir()):
        if path.is_file() and path.suffix in (".yaml", ".json", ".md"):
            print(f"    {path.name} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()