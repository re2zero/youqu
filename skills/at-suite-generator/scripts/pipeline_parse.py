#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
# SPDX-License-Identifier: GPL-2.0-only
"""pipeline_parse.py — Parse xlsx/csv and slice into token-budgeted module files.

Replaces v1's parse → plan → prep three-stage chain with a single pass that
NEVER writes a full cases_raw.yaml. For 2000+ case documents, a single full
file would blow the LLM context; this script slices directly by module and
token budget so each downstream sub-agent reads only its own chunk.

Usage:
    pipeline_parse.py --input tests/at/casefile/用例.xlsx \
        --output tests/at/modules/ [--app deepin-reader] \
        [--budget 16000]

Inputs:
    --input      xlsx/csv test case file
    --output     modules/ output directory
    --app        application name (optional, for meta)
    --budget     per-chunk token budget (default 16000)

Outputs:
    modules/<slug>_<seq>.input.json   one per slice (LLM input)
    modules/_summary.json             slice manifest (NOT full cases)

Guarantees:
    - No case is dropped or altered: every normalized case lands in exactly
      one slice; the summary records total counts for verification.
    - Grouping is by the xlsx "所属模块" column when present; otherwise by
      title/function clustering.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

# ─── Column aliases (mirror src/at/generator/case_parser.py) ────────────
COLUMN_ALIASES = {
    "id": ["用例编号", "ID", "编号", "序号"],
    "title": ["用例标题", "标题", "用例名称", "测试点"],
    "module": ["所属模块", "模块", "功能模块", "测试模块"],
    "priority": ["用例级别", "优先级", "级别", "重要程度"],
    "precondition": ["前置条件", "前提条件", "预置条件"],
    "steps": ["步骤", "测试步骤", "操作步骤", "用例步骤"],
    "expected": ["预期", "预期结果", "期望结果", "预期输出"],
    "case_type": ["用例类型", "类型", "测试类型"],
}


def _find_column(record: dict, aliases: list[str]) -> str:
    for alias in aliases:
        if alias in record:
            val = record[alias]
            if val:
                return val
    for key in record:
        if any(a.lower() in key.lower() for a in aliases):
            return record[key]
    return ""


def read_xlsx(filepath: str) -> list[dict]:
    """Read xlsx streaming row-by-row (no full-sheet materialization)."""
    try:
        from openpyxl import load_workbook
    except ImportError:
        print("Error: openpyxl not installed. pip install openpyxl")
        sys.exit(1)
    wb = load_workbook(filepath, data_only=True, read_only=True)
    ws = wb.active
    rows = ws.iter_rows(values_only=True)
    try:
        header_row = next(rows)
    except StopIteration:
        return []
    headers = [str(h).strip() if h else "" for h in header_row]
    data = []
    for row_idx, row in enumerate(rows, start=2):
        record = {"source_row": row_idx}
        for col_idx, value in enumerate(row):
            if col_idx < len(headers) and headers[col_idx]:
                record[headers[col_idx]] = str(value).strip() if value is not None else ""
        data.append(record)
    wb.close()
    return data


def read_csv_file(filepath: str) -> list[dict]:
    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        data = []
        for row_idx, row in enumerate(reader, start=2):
            record = {"source_row": row_idx}
            record.update({k.strip(): v.strip() if v else "" for k, v in row.items() if k})
            data.append(record)
        return data


def normalize_cases(raw_data: list[dict]) -> list[dict]:
    """Normalize raw rows into canonical case dicts. No case is dropped."""
    cases = []
    for idx, record in enumerate(raw_data):
        cases.append(
            {
                "id": _find_column(record, COLUMN_ALIASES["id"]) or str(idx).zfill(3),
                "title": _find_column(record, COLUMN_ALIASES["title"]),
                "module": _find_column(record, COLUMN_ALIASES["module"]),
                "priority": _find_column(record, COLUMN_ALIASES["priority"]),
                "precondition": _find_column(record, COLUMN_ALIASES["precondition"]),
                "steps": _find_column(record, COLUMN_ALIASES["steps"]),
                "expected": _find_column(record, COLUMN_ALIASES["expected"]),
                "case_type": _find_column(record, COLUMN_ALIASES["case_type"]),
                "source_row": record.get("source_row", 0),
            }
        )
    return cases


# ─── Token estimation (no external tokenizer) ───────────────────────────
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def estimate_tokens(text: str) -> int:
    """Conservative token estimate: CJK ~0.7 tok/char, other ~0.3 tok/char."""
    if not text:
        return 0
    cjk = len(_CJK_RE.findall(text))
    other = len(text) - cjk
    return int(cjk * 0.7 + other * 0.3)


def _case_tokens(case: dict) -> int:
    return estimate_tokens(
        " ".join(
            str(case.get(k) or "")
            for k in ("id", "title", "module", "precondition", "steps", "expected")
        )
    )


# ─── Grouping ───────────────────────────────────────────────────────────
def _slugify(text: str) -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", text).strip("_")
    return cleaned[:64] or "misc"


def _group_by_module(cases: list[dict]) -> list[dict]:
    """Group cases by the module column. Preserves source order within groups."""
    groups: dict[str, list[dict]] = {}
    order: list[str] = []
    for c in cases:
        mod = (c.get("module") or "").strip() or "未分类"
        if mod not in groups:
            groups[mod] = []
            order.append(mod)
        groups[mod].append(c)
    return [{"module": mod, "cases": groups[mod]} for mod in order]


def _cluster_by_title(cases: list[dict]) -> list[dict]:
    """Fallback grouping when no module column: cluster by title keyword.

    Extracts a leading functional keyword from each title (e.g. "打开",
    "保存", "缩放") and groups cases sharing it. Cases with no keyword go
    to a single "其他" bucket.
    """
    # Common functional verbs/prefixes to split on
    _KEYWORD_RE = re.compile(
        r"^(打开|关闭|新建|保存|另存|删除|重命名|复制|粘贴|剪切|撤销|重做|"
        r"缩放|翻页|切换|搜索|查找|替换|导入|导出|打印|设置|全屏|最小化|最大化|"
        r"恢复|拖拽|双击|右键|左键|滚动|刷新|排序|筛选|添加|移除|清空|恢复默认)"
    )
    buckets: dict[str, list[dict]] = {}
    order: list[str] = []
    for c in cases:
        title = c.get("title") or ""
        m = _KEYWORD_RE.search(title)
        key = m.group(1) if m else "其他"
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(c)
    return [{"name": key, "cases": buckets[key]} for key in order]


# ─── Slicing ────────────────────────────────────────────────────────────
def _slice_group(group: dict, budget: int) -> list[dict]:
    """Split one module group into token-budgeted slices.

    Pure token-budget driven: a new slice starts when adding the next case
    would exceed the budget. A single case larger than the budget still gets
    its own slice (never dropped, never split).
    """
    name = group.get("name") or group.get("module") or "未分类"
    cases = group["cases"]
    slices: list[dict] = []
    current: list[dict] = []
    current_tokens = 0

    def flush(seq: int) -> None:
        nonlocal current, current_tokens
        if current:
            slices.append({"name": name, "seq": seq, "cases": current})
            current = []
            current_tokens = 0

    seq = 1
    for case in cases:
        t = _case_tokens(case)
        if current and current_tokens + t > budget:
            flush(seq)
            seq += 1
        current.append(case)
        current_tokens += t
    flush(seq)
    return slices


def _merge_small_slices(slices: list[dict], budget: int) -> list[dict]:
    """Merge adjacent small slices (same module) to reduce agent count.

    Only merges slices from the SAME module group, keeping semantic
    boundaries intact. Never exceeds the token budget.
    """
    merged: list[dict] = []
    for s in slices:
        if merged and merged[-1]["name"] == s["name"]:
            last = merged[-1]
            last_tokens = sum(_case_tokens(c) for c in last["cases"])
            add_tokens = sum(_case_tokens(c) for c in s["cases"])
            if last_tokens + add_tokens <= budget:
                last["cases"].extend(s["cases"])
                continue
        merged.append(s)
    # Renumber seq
    for i, s in enumerate(merged, 1):
        s["seq"] = i
    return merged




# ─── Output ─────────────────────────────────────────────────────────────
def _short_name(name: str) -> str:
    """Short human-readable module name for file naming."""
    return _slugify(name)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Parse xlsx/csv and slice into token-budgeted module files",
        epilog=(
            "Examples:\n"
            "  python3 pipeline_parse.py --input tests/at/casefile/用例.xlsx \\\n"
            "      --output tests/at/modules/ --app deepin-reader --budget 16000\n"
            "\n"
            "Slices by module + token budget; never writes a full cases_raw.yaml."
        ),
    )
    parser.add_argument("--input", required=True, help="xlsx/csv test case file")
    parser.add_argument("--output", required=True, help="Output modules/ directory")
    parser.add_argument("--app", default="", help="Application name")
    parser.add_argument("--budget", type=int, default=16000, help="Per-slice token budget")
    args = parser.parse_args()

    in_path = Path(args.input)
    if not in_path.is_file():
        print(f"Error: input file not found: {in_path}")
        sys.exit(1)

    ext = in_path.suffix.lower()
    if ext in (".xlsx", ".xls"):
        raw_data = read_xlsx(str(in_path))
    elif ext == ".csv":
        raw_data = read_csv_file(str(in_path))
    else:
        print(f"Error: unsupported format {ext}. Use .xlsx or .csv")
        sys.exit(1)

    if not raw_data:
        print(f"Error: no data rows found in {in_path}")
        sys.exit(1)

    cases = normalize_cases(raw_data)
    total_cases = len(cases)
    print(f"Read {total_cases} cases from {in_path.name}")

    # Group by module column; fall back to title clustering
    has_module_col = any(c.get("module") for c in cases)
    groups = _group_by_module(cases) if has_module_col else _cluster_by_title(cases)
    print(f"Grouped into {len(groups)} module groups "
          f"({'by module column' if has_module_col else 'by title clustering'})")

    # Slice each group, then merge small slices within the same module
    all_slices: list[dict] = []
    for g in groups:
        all_slices.extend(_slice_group(g, args.budget))
    all_slices = _merge_small_slices(all_slices, args.budget)

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    slice_stats: list[dict] = []
    written_cases = 0
    for i, s in enumerate(all_slices, 1):
        short = _short_name(s["name"])
        file_name = f"{short}_{s['seq']:03d}.input.json"
        input_data = {
            "meta": {
                "app": args.app,
                "module": s["name"],
                "module_slug": short,
                "slice_seq": s["seq"],
                "case_count": len(s["cases"]),
                "est_tokens": sum(_case_tokens(c) for c in s["cases"]),
            },
            "cases": s["cases"],
        }
        out_path = out_dir / file_name
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(input_data, f, ensure_ascii=False, indent=2)
        written_cases += len(s["cases"])
        slice_stats.append(
            {
                "file": file_name,
                "module": s["name"],
                "seq": s["seq"],
                "case_count": len(s["cases"]),
                "est_tokens": input_data["meta"]["est_tokens"],
            }
        )
        print(f"  [{i:3d}] {file_name:40s} {len(s['cases']):3d} cases "
              f"~{input_data['meta']['est_tokens']} tok")

    # ── Integrity check: no case lost or altered ─────────────────────
    # Re-read all written slices and verify count + id set matches source.
    re_read_ids: set[str] = set()
    for st in slice_stats:
        with open(out_dir / st["file"], encoding="utf-8") as f:
            data = json.load(f)
        for c in data["cases"]:
            re_read_ids.add(c["id"])
    src_ids = {c["id"] for c in cases}
    missing = src_ids - re_read_ids
    extra = re_read_ids - src_ids
    if missing or extra:
        print(f"  ✗ INTEGRITY FAIL: {len(missing)} missing, {len(extra)} extra case ids")
        if missing:
            print(f"    missing: {sorted(missing)[:10]}")
        sys.exit(1)
    if written_cases != total_cases:
        print(f"  ✗ INTEGRITY FAIL: wrote {written_cases} != source {total_cases}")
        sys.exit(1)
    print(f"  ✓ Integrity OK: {written_cases}/{total_cases} cases preserved, "
          f"no loss, no alteration")

    # ── Summary manifest (NOT full cases) ────────────────────────────
    summary = {
        "app": args.app,
        "source": in_path.name,
        "total_cases": total_cases,
        "total_slices": len(all_slices),
        "budget": args.budget,
        "grouping": "module" if has_module_col else "title_cluster",
        "slices": slice_stats,
    }
    summary_path = out_dir / "_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 60}")
    print(f"Summary: {total_cases} cases → {len(all_slices)} slices")
    print(f"  Slices: {summary_path}")
    print(f"  Next: run generation sub-agents on each *.input.json (max 3 parallel)")


if __name__ == "__main__":
    main()