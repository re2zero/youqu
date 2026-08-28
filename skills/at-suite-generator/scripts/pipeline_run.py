#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
# SPDX-License-Identifier: GPL-2.0-only
"""pipeline_run.py — Element-driven deterministic pipeline.

Runs all deterministic (non-AI) steps of the pipeline in one shot:
  scan (at-spi-coverage) → parse/slice (pipeline_parse) → element manifest

Usage:
    pipeline_run.py --app <app> --src <source_dir> \\
        --xlsx <casefile.xlsx> \\
        --output tests/at/

    pipeline_run.py --app <app> --src <source_dir> \\
        --output tests/at/               # no xlsx (feature-driven mode)

    pipeline_run.py --app <app> --scan-dir tests/at/coverage_scan/ \\
        --xlsx <casefile.xlsx> \\
        --output tests/at/               # reuse existing scan products

Inputs:
    --src        source code directory (REQUIRED unless --scan-dir given)
    --xlsx/--csv test case document (optional, feature-driven mode)
    --scan-dir   existing coverage_scan/ (skip scan)

Outputs (under tests/at/):
    coverage_scan/                      (from at-spi-coverage scan)
    element-coverage-manifest.yaml       (from element_manifest)
    modules/_summary.json                (from pipeline_parse)
    modules/*.input.json                 (per-slice, for LLM)
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
SCRIPT_DIR = Path(__file__).resolve().parent
SKILLS_DIR = SCRIPT_DIR.parent.parent  # skills/
COVERAGE_STATS = Path(os.environ.get(
    "AT_SPI_COVERAGE_SCRIPT", SKILLS_DIR / "at-spi-coverage" / "scripts" / "coverage_stats.py"
))


def _run(cmd: list[str], cwd: str | None = None, label: str = "") -> bool:
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


def _file_exists(path: str) -> bool:
    p = Path(path)
    return p.is_file() and p.stat().st_size > 0


def stage_scan(src: str, output_dir: str) -> str | None:
    """Run at-spi-coverage scan → coverage_scan/."""
    if not COVERAGE_STATS.is_file():
        print(f"  ⚠ at-spi-coverage scan script not found: {COVERAGE_STATS}")
        print("    Install the at-spi-coverage skill, set AT_SPI_COVERAGE_SCRIPT,")
        print("    or pass --scan-dir to reuse existing coverage_scan/.")
        return None

    scan_dir = os.path.join(output_dir, "coverage_scan")
    if os.path.isdir(scan_dir) and not args.force:
        print(f"  ⏩ coverage_scan/ exists, skip scan (use --force to redo)")
        return scan_dir
    report = os.path.join(output_dir, "coverage_report.json")
    if _run(
        ["python3", str(COVERAGE_STATS), "--src", src, "-o", report],
        label="at-spi-coverage scan",
    ):
        return scan_dir
    return None


def stage_manifest(scan_dir: str | None, output_dir: str) -> str | None:
    """Build element-coverage-manifest.yaml from scan products."""
    if not scan_dir or not os.path.isdir(scan_dir):
        return None
    manifest = os.path.join(output_dir, "element-coverage-manifest.yaml")
    if _file_exists(manifest) and not args.force:
        print(f"  ⏩ element-coverage-manifest.yaml exists, skip (use --force to redo)")
        return manifest
    script = SCRIPT_DIR / "element_manifest.py"
    if _run(
        ["python3", str(script), "--scan-dir", scan_dir, "--output", manifest],
        label="element_manifest",
    ):
        return manifest
    return None



def stage_parse(xlsx: str | None, csv: str | None, app: str, output_dir: str) -> str | None:
    """Parse xlsx/csv → token-budgeted slices (no full cases_raw.yaml)."""
    source = xlsx or csv
    if not source:
        return None
    modules_dir = os.path.join(output_dir, "modules")
    summary = os.path.join(modules_dir, "_summary.json")
    if _file_exists(summary) and not args.force:
        print(f"  ⏩ modules/ exists, skip parse (use --force to redo)")
        return modules_dir
    script = SCRIPT_DIR / "pipeline_parse.py"
    cmd = [
        "python3", str(script),
        "--input", source,
        "--output", modules_dir,
        "--budget", str(args.budget),
    ]
    if app:
        cmd += ["--app", app]
    if _run(cmd, label="pipeline_parse"):
        return modules_dir
    return None




def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run all deterministic AT-SPI pipeline steps (element-driven)"
    )
    parser.add_argument("--app", required=True, help="Application name")
    parser.add_argument("--src", help="Source code directory (for scan)")
    parser.add_argument("--xlsx", help="xlsx test case file")
    parser.add_argument("--csv", help="csv test case file")
    parser.add_argument("--output", required=True, help="Output directory (e.g. tests/at/)")
    parser.add_argument("--scan-dir", help="Existing coverage_scan/ (skip scan)")
    parser.add_argument("--budget", type=int, default=16000, help="Per-slice token budget")
    parser.add_argument("--force", action="store_true", help="Redo all stages even if outputs exist")

    global args
    args = parser.parse_args()


    # 前置校验：100% 门禁依赖元素全集，必须能拿到扫描产物
    if not args.src and not args.scan_dir:
        print("[FAIL] 需要 --src（触发源码扫描）或 --scan-dir（复用已有扫描产物）")
        print("       元素全集（pre_scan_ok.yaml / qml_ok.yaml）是 100% 覆盖门禁的分母，无法跳过。")
        sys.exit(1)

    output_dir = args.output
    os.makedirs(output_dir, exist_ok=True)

    print(f"=== Pipeline Run: {args.app} ===")
    print(f"  Output: {output_dir}")
    print()

    # ── Stage 1: Scan (at-spi-coverage) ─────────────────────────────
    scan_dir = args.scan_dir
    if not scan_dir and args.src:
        print("[Stage 1/3] Source scan (at-spi-coverage)")
        scan_dir = stage_scan(args.src, output_dir)
        if not scan_dir:
            print("[FAIL] 源码扫描失败，无法生成元素全集。检查 --src 路径与 libclang 依赖。")
            sys.exit(1)
        print()

    # ── Stage 2: Element manifest ────────────────────────────────────
    print("[Stage 2/3] Element manifest")
    manifest = stage_manifest(scan_dir, output_dir)
    if not manifest:
        print("[FAIL] 元素清单生成失败：扫描产物缺失或为空。")
        print("       检查 coverage_scan/ 下是否有 pre_scan_ok.yaml / qml_ok.yaml。")
        sys.exit(1)
    print(f"  ✓ element-coverage-manifest.yaml: {manifest}")
    print()

    # ── Stage 3: Parse + slice (token-budgeted) ─────────────────────
    if args.xlsx or args.csv:
        print("[Stage 3/3] Parse + slice (token-budgeted)")
        modules_dir = stage_parse(args.xlsx, args.csv, args.app, output_dir)
        if modules_dir:
            print(f"  ✓ modules: {modules_dir}")
        print()

    # ── Summary ──────────────────────────────────────────────────────
    print("=" * 60)
    print("Pipeline complete. Next steps:")
    print()
    print("  Phase 2 (AI):")
    print("    For each modules/*.input.json, run LLM mapping → *.output.json")
    print("    Use stage-2-generate reference + at-case-mapping-prompt-template.")
    print("    Adaptive sub-agent pool, max 3 parallel.")
    print()
    print("  Phase 3 (Script):")
    print("    pipeline_assemble.py --modules tests/at/modules/ \\")
    print("        --output tests/at/ --manifest tests/at/element-coverage-manifest.yaml")
    print("    cover.py --scan-dir tests/at/coverage_scan/ --testdir tests/at/yaml/")
    print()
    print("  Outputs:")
    for path in sorted(Path(output_dir).iterdir()):
        if path.is_file() and path.suffix in (".yaml", ".json", ".md"):
            print(f"    {path.name} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()