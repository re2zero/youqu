#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
# SPDX-License-Identifier: GPL-2.0-only
"""gen_schedule.py — Deterministic sub-agent batch scheduler (Stage 2).

Enforces the hard "max 3 parallel" rule mechanically. The main agent MUST
call this before spawning generation sub-agents; it reads the slice manifest
(_summary.json from pipeline_parse.py) and emits a batch plan where every
batch has at most `--max-parallel` (default 3) slices. Batches run serially.

Why a script instead of prose: the parallel cap was previously stated only in
markdown and agents routinely ignored it (firing 27 agents at once). A
precomputed schedule makes the constraint observable and testable.

Usage:
    gen_schedule.py --modules tests/at/modules/ [--max-parallel 3] [--output -]

Output (stdout or --output file):
    {
      "max_parallel": 3,
      "total_slices": 27,
      "total_batches": 9,
      "batches": [
        {"batch": 1, "slices": [{"file": "...", "seq": 1, "case_count": 13}]},
        ...
      ]
    }

Rules:
    - Each batch has <= max_parallel slices.
    - Slices are dispatched in manifest order (stable, deterministic).
    - A single batch is never split; a slice always belongs to exactly one batch.
    - If max_parallel >= total_slices, a single batch holds everything
      (still capped by --max-parallel).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def build_batches(slices: list[dict], max_parallel: int) -> list[list[dict]]:
    if max_parallel < 1:
        raise ValueError("--max-parallel must be >= 1")
    batches: list[list[dict]] = []
    for sl in slices:
        if not batches or len(batches[-1]) >= max_parallel:
            batches.append([])
        batches[-1].append(sl)
    return batches


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Deterministic sub-agent batch scheduler (max N parallel)"
    )
    parser.add_argument("--modules", required=True, help="modules/ dir with _summary.json")
    parser.add_argument("--max-parallel", type=int, default=3, help="Max slices per batch (default 3)")
    parser.add_argument("--output", default="-", help="Output file ('-' for stdout)")
    args = parser.parse_args()

    summary_path = Path(args.modules) / "_summary.json"
    if not summary_path.is_file():
        print(f"Error: {summary_path} not found. Run pipeline_parse.py first.")
        sys.exit(1)
    with open(summary_path, encoding="utf-8") as f:
        summary = json.load(f)
    slices = summary.get("slices", [])

    batches = build_batches(slices, args.max_parallel)
    plan = {
        "max_parallel": args.max_parallel,
        "total_slices": len(slices),
        "total_batches": len(batches),
        "batches": [
            {"batch": i + 1, "slices": sl} for i, sl in enumerate(batches)
        ],
    }
    text = json.dumps(plan, ensure_ascii=False, indent=2)
    if args.output == "-":
        print(text)
    else:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"Wrote {args.output} ({len(batches)} batches, "
              f"max {args.max_parallel} parallel)")


if __name__ == "__main__":
    main()
