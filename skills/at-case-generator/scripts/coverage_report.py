# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only

"""AT-SPI test suite coverage report generator.

Post-processing tool that scans generated suite YAML + elements.yaml
and produces a coverage report (report.md). Does NOT modify any
generated files — pure analysis.

Usage:
    youqu at report --testdir <output_dir> [--expected-names <path>]
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


def _load_yaml(path: str) -> dict | list | None:
    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    except (FileNotFoundError, OSError):
        return None


def _load_expected_names(path: str) -> dict[str, str]:
    """Load expected_names.yaml → {accessible_name: source_key}."""
    data = _load_yaml(path)
    if not data or not isinstance(data, dict):
        return {}
    result: dict[str, str] = {}
    for key, entry in data.items():
        if isinstance(entry, dict):
            name = entry.get("accessible_name", "")
            if name:
                result[name] = key
    return result


def _collect_suite_files(testdir: str) -> list[Path]:
    """Recursively find all *.suite.yaml files under testdir."""
    root = Path(testdir)
    if not root.exists():
        return []
    return sorted(root.rglob("*.suite.yaml"))


def _collect_elements(elements_path: str) -> dict[str, dict]:
    """Load elements.yaml → {ref: selector_dict}."""
    data = _load_yaml(elements_path)
    if not data or not isinstance(data, dict):
        return {}
    raw = data.get("elements", data)
    if isinstance(raw, dict):
        return raw
    return {}


def _extract_refs_from_suite(suite_path: Path) -> tuple[set[str], list[dict]]:
    """Scan one suite.yaml → (refs_used, cases_info).

    cases_info: list of {id, name, actions, refs, assert_count}
    """
    data = _load_yaml(str(suite_path))
    if not data or not isinstance(data, dict):
        return set(), []

    refs_used: set[str] = set()
    cases_info: list[dict] = []
    suites = data.get("suites", [])
    if not isinstance(suites, list):
        return set(), []

    for case in suites:
        if not isinstance(case, dict):
            continue
        case_id = case.get("id", "?")
        case_name = case.get("name", "")
        actions: list[str] = []
        case_refs: set[str] = set()

        for step in case.get("steps", []):
            if not isinstance(step, dict):
                continue
            action = step.get("action", "")
            if action:
                actions.append(action)
            ref = step.get("ref", "")
            if ref:
                case_refs.add(ref)
            sel = step.get("selector", {})
            if isinstance(sel, dict):
                name = sel.get("name", "")
                if name:
                    case_refs.add(name)

        for step in case.get("assert_steps", []):
            if not isinstance(step, dict):
                continue
            ref = step.get("ref", "")
            if ref:
                case_refs.add(ref)
            sel = step.get("selector", {})
            if isinstance(sel, dict):
                name = sel.get("name", "")
                if name:
                    case_refs.add(name)

        refs_used.update(case_refs)
        cases_info.append({
            "id": case_id,
            "name": case_name,
            "actions": actions,
            "refs": case_refs,
            "assert_count": len(case.get("assert_steps", [])),
        })

    return refs_used, cases_info


def _detect_duplicates(cases_info: list[dict]) -> list[dict]:
    """Detect cases with identical action sequences.

    Returns list of {action_seq, count, case_ids, names}.
    """
    seq_groups: dict[str, list[dict]] = defaultdict(list)
    for info in cases_info:
        seq = tuple(info["actions"])
        if seq:  # skip empty sequences
            seq_groups[str(seq)].append(info)

    duplicates = []
    for seq_str, group in seq_groups.items():
        if len(group) > 1:
            duplicates.append({
                "action_seq": seq_str,
                "count": len(group),
                "case_ids": [g["id"] for g in group],
                "names": [g["name"] for g in group],
            })

    return sorted(duplicates, key=lambda d: -d["count"])


def _compute_coverage(
    elements: dict[str, dict],
    refs_used: set[str],
    expected_names: dict[str, str] | None = None,
) -> dict:
    """Compute coverage metrics.

    Returns dict with:
      - coverage_a: {covered, available, rate}
      - coverage_b: {covered, total, rate} (only if expected_names provided)
      - uncovered: list of element names not referenced by any case
    """
    # 口径 A: 基于运行时元素表
    available = 0
    for ref, sel in elements.items():
        name = sel.get("name", "") if isinstance(sel, dict) else ""
        if name:
            available += 1

    covered_a = len(refs_used)
    rate_a = (covered_a / available * 100) if available > 0 else 0

    result: dict[str, Any] = {
        "coverage_a": {
            "covered": covered_a,
            "available": available,
            "rate": round(rate_a, 1),
        },
    }

    # 口径 B: 基于源码全集
    if expected_names:
        source_total = len(expected_names)
        source_covered = sum(1 for name in expected_names if name in refs_used)
        rate_b = (source_covered / source_total * 100) if source_total > 0 else 0
        result["coverage_b"] = {
            "covered": source_covered,
            "total": source_total,
            "rate": round(rate_b, 1),
        }

    # 未覆盖元素：比较 ref 键（不是 name 字段）
    uncovered = []
    for ref, sel in elements.items():
        name = sel.get("name", "") if isinstance(sel, dict) else ""
        if name and ref not in refs_used:
            role = sel.get("role", "") if isinstance(sel, dict) else ""
            uncovered.append({"name": name, "role": role, "ref": ref})
    result["uncovered"] = sorted(uncovered, key=lambda x: x["name"])

    return result


def _load_unsupported_cases(cases_mapped_path: str) -> list[dict]:
    """Load unsupported cases from cases_mapped.yaml."""
    data = _load_yaml(cases_mapped_path)
    if not data or not isinstance(data, dict):
        return []
    cases = data.get("cases", [])
    if not isinstance(cases, list):
        return []
    unsupported = []
    for c in cases:
        if not isinstance(c, dict):
            continue
        if c.get("status") == "unsupported":
            unsupported.append({
                "id": c.get("id", "?"),
                "name": c.get("name", ""),
                "reason": c.get("reason", "未指定"),
            })
    return unsupported


def generate_report(
    testdir: str,
    expected_names_path: str = "",
    cases_mapped_path: str = "",
) -> str:
    """Generate coverage report. Returns report file path."""
    root = Path(testdir)
    elements_path = str(root / "elements.yaml")
    elements = _collect_elements(elements_path)

    expected_names: dict[str, str] = {}
    if expected_names_path:
        expected_names = _load_expected_names(expected_names_path)

    suite_files = _collect_suite_files(testdir)
    all_refs: set[str] = set()
    all_cases: list[dict] = []
    module_counts: dict[str, int] = defaultdict(int)

    for sf in suite_files:
        refs, cases = _extract_refs_from_suite(sf)
        all_refs.update(refs)
        all_cases.extend(cases)
        # module name from parent directory
        module_name = sf.parent.name
        module_counts[module_name] += len(cases)

    total_cases = len(all_cases)
    total_assert = sum(1 for c in all_cases if c["assert_count"] > 0)
    total_no_assert = total_cases - total_assert

    # 重复检测
    duplicates = _detect_duplicates(all_cases)

    # 覆盖率
    coverage = _compute_coverage(elements, all_refs, expected_names)

    # 不可自动化用例
    unsupported = _load_unsupported_cases(cases_mapped_path)

    # --- 生成 Markdown ---
    lines = [
        "# AT-SPI Test Suite Coverage Report",
        "",
        f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**测试目录**: {testdir}",
        "",
        "---",
        "",
        "## 1. 用例统计",
        "",
        "| 指标 | 值 |",
        "|------|-----|",
        f"| 总用例数 | {total_cases} |",
        f"| 含断言用例 | {total_assert} |",
        f"| 无断言用例 | {total_no_assert} |",
        f"| 断言覆盖率 | {round(total_assert / total_cases * 100, 1) if total_cases > 0 else 0}% |",
        "",
    ]

    if module_counts:
        lines.append("### 各模块用例分布")
        lines.append("")
        lines.append("| 模块 | 用例数 |")
        lines.append("|------|--------|")
        for mod in sorted(module_counts):
            lines.append(f"| {mod} | {module_counts[mod]} |")
        lines.append("")

    # 覆盖率
    lines.append("## 2. AT-SPI 元素覆盖率")
    lines.append("")
    lines.append("### 口径 A — 基于运行时元素表（elements.yaml）")
    lines.append("")
    ca = coverage["coverage_a"]
    lines.append(f"| 指标 | 值 |")
    lines.append(f"|------|-----|")
    lines.append(f"| 已覆盖元素数 | {ca['covered']} |")
    lines.append(f"| 可用元素数 | {ca['available']} |")
    lines.append(f"| 覆盖率 A | {ca['rate']}% |")
    lines.append("")

    if "coverage_b" in coverage:
        cb = coverage["coverage_b"]
        lines.append("### 口径 B — 基于源码全集（expected_names.yaml）")
        lines.append("")
        lines.append(f"| 指标 | 值 |")
        lines.append(f"|------|-----|")
        lines.append(f"| 已覆盖元素数 | {cb['covered']} |")
        lines.append(f"| 源码元素总数 | {cb['total']} |")
        lines.append(f"| 覆盖率 B | {cb['rate']}% |")
        lines.append("")
    else:
        lines.append("*仅基于运行时元素表（口径 A），无源码全集对照（口径 B）。*")
        lines.append("")

    # 未覆盖元素
    uncovered = coverage["uncovered"]
    if uncovered:
        lines.append("### 未覆盖元素")
        lines.append("")
        lines.append("| 名称 | 角色 | 引用键 |")
        lines.append("|------|------|--------|")
        for u in uncovered[:30]:  # top 30
            lines.append(f"| {u['name']} | {u['role']} | {u['ref']} |")
        if len(uncovered) > 30:
            lines.append(f"| ... 共 {len(uncovered)} 个未覆盖元素，仅显示前 30 | | |")
        lines.append("")

    # 重复检测
    if duplicates:
        lines.append("## 3. 重复用例检测")
        lines.append("")
        lines.append(f"发现 **{len(duplicates)}** 组重复用例（相同操作序列）：")
        lines.append("")
        for dup in duplicates:
            lines.append(f"- **{dup['count']} 个重复**: {', '.join(dup['case_ids'])}")
            lines.append(f"  - 名称: {', '.join(dup['names'][:3])}")
            lines.append(f"  - 操作序列: `{' → '.join(eval(dup['action_seq']))}`")
            lines.append("")
    else:
        lines.append("## 3. 重复用例检测")
        lines.append("")
        lines.append("未发现重复用例。")
        lines.append("")

    # 不可自动化用例
    if unsupported:
        lines.append("## 4. 不可自动化用例")
        lines.append("")
        lines.append("| # | 用例 ID | 标题 | 原因 |")
        lines.append("|---|---------|------|------|")
        for i, u in enumerate(unsupported, 1):
            lines.append(f"| {i} | {u['id']} | {u['name']} | {u['reason']} |")
        lines.append("")

    # 缺口分析
    if uncovered:
        lines.append("## 5. 缺口分析")
        lines.append("")
        lines.append(f"共有 **{len(uncovered)}** 个 AT-SPI 元素未被任何用例引用。")
        lines.append("可能原因：")
        lines.append("- 元素在当前测试场景中不可达（条件渲染、窗口未打开）")
        lines.append("- 元素缺少 `setAccessibleName()`，无法通过名称定位")
        lines.append("- 用例未覆盖该功能路径")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(f"*报告由 coverage.py 自动生成*")

    report_path = str(root / "report.md")
    Path(report_path).parent.mkdir(parents=True, exist_ok=True)
    Path(report_path).write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {report_path}")
    return report_path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate AT-SPI coverage report")
    parser.add_argument("--testdir", default="tests/at/yaml", help="Test directory (output of generate)")
    parser.add_argument("--expected-names", default="", help="Path to expected_names.yaml")
    parser.add_argument("--cases-mapped", default="", help="Path to cases_mapped.yaml")
    args = parser.parse_args()

    generate_report(
        testdir=args.testdir,
        expected_names_path=args.expected_names,
        cases_mapped_path=args.cases_mapped,
    )