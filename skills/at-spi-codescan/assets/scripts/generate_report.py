#!/usr/bin/env python3
"""覆盖率报告生成器 — 合并两条分析线的结果，输出对比报告。

输入：
  --pipeline-a-dir: 静态扫描输出目录（含 pre_scan_gaps.yaml, pre_scan_ok.yaml, qml_*.yaml）
  --pipeline-b-data: 代码图谱数据 JSON（可选，AI 调用 MCP 工具产出）
  --output: 报告输出目录

输出：
  coverage-report.md — 汇总对比报告
  coverage-data.json — 结构化数据
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("coverage_report")


def load_yaml(path: Path) -> dict:
    import yaml
    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}
    except Exception as e:
        logger.warning("Failed to load %s: %s", path, e)
        return {}


def load_json(path: Path) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        logger.warning("Failed to load %s: %s", path, e)
        return {}


def calc_coverage_from_scan(ok_path: Path, gaps_path: Path) -> dict:
    """从 scan_gaps 输出计算覆盖率。"""
    ok_data = load_yaml(ok_path)
    gaps_data = load_yaml(gaps_path)
    ok_widgets = ok_data.get("widgets", [])
    gap_widgets = gaps_data.get("gaps", gaps_data.get("widgets", []))
    total = len(ok_widgets) + len(gap_widgets)
    ok_count = len(ok_widgets)
    coverage = (ok_count / total * 100) if total else 0.0
    return {
        "total": total,
        "ok": ok_count,
        "gaps": len(gap_widgets),
        "coverage": round(coverage, 1),
        "gap_list": gap_widgets,
        "ok_list": ok_widgets,
    }


def calc_qml_coverage_from_scan(ok_path: Path, gaps_path: Path) -> dict:
    """从 scan_qml 输出计算覆盖率。"""
    ok_data = load_yaml(ok_path)
    gaps_data = load_yaml(gaps_path)
    ok_elements = ok_data.get("widgets", [])
    gap_elements = gaps_data.get("gaps", gaps_data.get("widgets", []))
    total = len(ok_elements) + len(gap_elements)
    ok_count = len(ok_elements)
    coverage = (ok_count / total * 100) if total else 0.0
    return {
        "total": total,
        "ok": ok_count,
        "gaps": len(gap_elements),
        "coverage": round(coverage, 1),
        "gap_list": gap_elements,
        "ok_list": ok_elements,
    }


def group_by_module(items: list[dict], key_field: str = "source_file") -> dict[str, list[dict]]:
    """按源文件目录分组。"""
    groups: dict[str, list[dict]] = {}
    for item in items:
        sf = item.get(key_field, "unknown")
        parts = sf.split("/")
        module = parts[0] if len(parts) > 1 else sf
        if module not in groups:
            groups[module] = []
        groups[module].append(item)
    return groups


def calc_module_coverage(groups: dict[str, list[dict]], ok_groups: dict[str, list[dict]]) -> list[dict]:
    """计算每个模块的覆盖率。"""
    modules: list[dict] = []
    all_modules = set(groups.keys()) | set(ok_groups.keys())
    for mod in sorted(all_modules):
        total = len(groups.get(mod, [])) + len(ok_groups.get(mod, []))
        ok_count = len(ok_groups.get(mod, []))
        coverage = (ok_count / total * 100) if total else 0.0
        modules.append({
            "module": mod,
            "total": total,
            "ok": ok_count,
            "gaps": total - ok_count,
            "coverage": round(coverage, 1),
        })
    return modules


def generate_report(
    project_name: str,
    project_path: str,
    a_cpp: dict | None,
    a_qml: dict | None,
    b_data: dict | None,
    output_dir: str,
) -> None:
    """生成汇总对比报告。"""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ── 结构化数据 ──────────────────────────────────────────
    data: dict[str, Any] = {
        "project": {"name": project_name, "path": project_path, "timestamp": now},
        "static_scan": {"cpp": a_cpp, "qml": a_qml},
        "codebase_graph": b_data,
    }
    data_path = out / "coverage-data.json"
    with open(data_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    logger.info("Written %s", data_path)

    # ── Markdown 报告 ──────────────────────────────────────
    lines: list[str] = []
    lines.append("# AT-SPI Coverage Report")
    lines.append("")
    lines.append("## 项目信息")
    lines.append(f"- 项目: {project_name}")
    lines.append(f"- 路径: {project_path}")
    lines.append(f"- 分析时间: {now}")
    lines.append("")

    # 覆盖率概览表
    lines.append("## 覆盖率概览")
    lines.append("")
    lines.append("| 分析线 | 语言 | 期望控件 | 已有名称 | 覆盖率 |")
    lines.append("|--------|------|---------------|---------------|--------|")

    if a_cpp:
        lines.append(f"| 静态扫描 | C++ | {a_cpp['total']} | {a_cpp['ok']} | {a_cpp['coverage']}% |")
    if a_qml:
        lines.append(f"| 静态扫描 | QML | {a_qml['total']} | {a_qml['ok']} | {a_qml['coverage']}% |")
    if b_data:
        if b_data.get("available", True):
            b_cov = b_data.get("coverage", 0)
            b_total = b_data.get("total", 0)
            b_ok = b_data.get("ok", 0)
            lines.append(f"| 代码图谱 | C++ | {b_total} | {b_ok} | {b_cov}% |")
        else:
            lines.append(f"| 代码图谱 | C++ | — | — | 不可用（{b_data.get('reason','')}） |")
    lines.append("")

    # 按模块覆盖率
    lines.append("## 按模块覆盖率")
    lines.append("")

    if a_cpp:
        lines.append("### 静态扫描 — C++")
        lines.append("")
        gap_groups = group_by_module(a_cpp["gap_list"])
        ok_groups = group_by_module(a_cpp["ok_list"])
        modules = calc_module_coverage(gap_groups, ok_groups)
        lines.append("| 模块 | 期望 | 已有 | 覆盖率 | Gap 数 |")
        lines.append("|------|---|---|--------|--------|")
        for m in modules:
            lines.append(f"| {m['module']} | {m['total']} | {m['ok']} | {m['coverage']}% | {m['gaps']} |")
        lines.append("")

    if a_qml:
        lines.append("### 静态扫描 — QML")
        lines.append("")
        gap_groups = group_by_module(a_qml["gap_list"])
        ok_groups = group_by_module(a_qml["ok_list"])
        modules = calc_module_coverage(gap_groups, ok_groups)
        lines.append("| 模块 | 期望 | 已有 | 覆盖率 | Gap 数 |")
        lines.append("|------|---|---|--------|--------|")
        for m in modules:
            lines.append(f"| {m['module']} | {m['total']} | {m['ok']} | {m['coverage']}% | {m['gaps']} |")
        lines.append("")

    if b_data:
        lines.append("### 代码图谱")
        lines.append("")
        b_modules = b_data.get("modules", [])
        if b_modules:
            lines.append("| 模块 | 期望 | 已有 | 覆盖率 | Gap 数 |")
            lines.append("|------|---|---|--------|--------|")
            for m in b_modules:
                lines.append(f"| {m.get('module','?')} | {m.get('total',0)} | {m.get('ok',0)} | {m.get('coverage',0)}% | {m.get('gaps',0)} |")
        lines.append("")

    # Gap 列表
    lines.append("## Gap 明细")
    lines.append("")

    if a_cpp and a_cpp["gap_list"]:
        lines.append("### 静态扫描 — C++ Gap 列表")
        lines.append("")
        lines.append("| 变量名 | 类型 | 文件 | 行号 | 缺 objectName | 缺 accessibleName |")
        lines.append("|--------|------|------|------|--------------|------------------|")
        for g in a_cpp["gap_list"][:50]:  # 最多 50 条
            var = g.get("variable", "?")
            typ = g.get("type", "?")
            sf = g.get("source_file", "?")
            ln = g.get("line", 0)
            no_obj = "✓" if not g.get("has_object_name") else ""
            no_acc = "✓" if not g.get("has_accessible_name") else ""
            lines.append(f"| {var} | {typ} | {sf} | {ln} | {no_obj} | {no_acc} |")
        if len(a_cpp["gap_list"]) > 50:
            lines.append(f"| ... 共 {len(a_cpp['gap_list'])} 条，仅显示前 50 |")
        lines.append("")

    if a_qml and a_qml["gap_list"]:
        lines.append("### 静态扫描 — QML Gap 列表")
        lines.append("")
        lines.append("| 元素类型 | ID | 文件 | 行号 | 建议名称 |")
        lines.append("|----------|----|------|------|---------|")
        for g in a_qml["gap_list"][:50]:
            et = g.get("element_type", "?")
            eid = g.get("id", "")
            sf = g.get("source_file", "?")
            ln = g.get("line", 0)
            sn = g.get("suggested_name", "")
            lines.append(f"| {et} | {eid} | {sf} | {ln} | {sn} |")
        if len(a_qml["gap_list"]) > 50:
            lines.append(f"| ... 共 {len(a_qml['gap_list'])} 条，仅显示前 50 |")
        lines.append("")

    if b_data:
        b_gaps = b_data.get("gap_list", [])
        if b_gaps:
            lines.append("### 代码图谱 — Gap 列表")
            lines.append("")
            lines.append("| 类名 | 类型 | 文件 | 推断原因 |")
            lines.append("|------|------|------|---------|")
            for g in b_gaps[:50]:
                cls = g.get("class", g.get("name", "?"))
                typ = g.get("type", "?")
                sf = g.get("file", g.get("source_file", "?"))
                reason = g.get("reason", g.get("inference", ""))
                lines.append(f"| {cls} | {typ} | {sf} | {reason} |")
            if len(b_gaps) > 50:
                lines.append(f"| ... 共 {len(b_gaps)} 条，仅显示前 50 |")
            lines.append("")

    # 差异分析
    lines.append("## 差异分析")
    lines.append("")

    a_cov = a_cpp["coverage"] if a_cpp else 0
    b_available = bool(b_data and b_data.get("available", True))
    b_cov = b_data.get("coverage", 0) if b_available else 0
    diff = abs(a_cov - b_cov)

    if a_cpp and b_available:
        lines.append(f"- **覆盖率差异**: 静态扫描 = {a_cov}%, 代码图谱 = {b_cov}%, 差异 = {diff}%")
        lines.append("- **粒度差异**: 静态扫描是实例级（每个 `m_xxx` 变量），代码图谱是类级（每个控件类）")
        lines.append("- **静态扫描独有**: 能发现同一类不同实例的命名不一致")
        lines.append("- **代码图谱独有**: 能发现头文件中声明的控件类（即使没有实例化）")
    elif a_cpp and b_data:
        lines.append(f"- **代码图谱不可用**（{b_data.get('reason','')}）")
        lines.append("- 覆盖率以静态扫描（纯源码）为准")
    lines.append("")

    # 缺口模式分析
    lines.append("## 缺口模式分析")
    lines.append("")

    if a_cpp:
        only_obj = sum(1 for g in a_cpp["gap_list"] if g.get("has_object_name") and not g.get("has_accessible_name"))
        only_acc = sum(1 for g in a_cpp["gap_list"] if not g.get("has_object_name") and g.get("has_accessible_name"))
        both_missing = sum(1 for g in a_cpp["gap_list"] if not g.get("has_object_name") and not g.get("has_accessible_name"))
        lines.append(f"- **完全无名称**: {both_missing} 个控件既无 setObjectName 也无 setAccessibleName")
        lines.append(f"- **只有 objectName**: {only_obj} 个控件缺 setAccessibleName（QWidget 子类需要两者）")
        lines.append(f"- **只有 accessibleName**: {only_acc} 个控件缺 setObjectName")
        lines.append("")

    # 建议
    lines.append("## 建议")
    lines.append("")
    if a_cpp and a_cpp["coverage"] < 80:
        lines.append(f"1. **覆盖率低于 80%**（当前 {a_cpp['coverage']}%），建议使用 at-spi-completion 技能补全")
    if a_cpp and only_obj > 0:
        lines.append(f"2. **{only_obj} 个控件只有 objectName**，需补充 setAccessibleName() 调用")
    if a_cpp and both_missing > 0:
        lines.append(f"3. **{both_missing} 个控件完全无名称**，需补充 setObjectName() + setAccessibleName()")
    lines.append("")

    report_path = out / "coverage-report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    logger.info("Written %s", report_path)


def main():
    parser = argparse.ArgumentParser(description="AT-SPI coverage report generator")
    parser.add_argument("--project-name", default="unknown", help="Project name")
    parser.add_argument("--project-path", default=".", help="Project path")
    parser.add_argument("--pipeline-a-dir", required=True, help="Static scan output directory")
    parser.add_argument("--pipeline-b-data", help="Codebase graph data JSON file (optional)")
    parser.add_argument("--output", "-o", default=".", help="Report output directory")
    args = parser.parse_args()

    a_dir = Path(args.pipeline_a_dir)

    # C++ coverage
    a_cpp = calc_coverage_from_scan(
        a_dir / "pre_scan_ok.yaml",
        a_dir / "pre_scan_gaps.yaml",
    ) if (a_dir / "pre_scan_ok.yaml").is_file() else None

    # QML coverage
    a_qml = calc_qml_coverage_from_scan(
        a_dir / "qml_ok.yaml",
        a_dir / "qml_gaps.yaml",
    ) if (a_dir / "qml_ok.yaml").is_file() else None

    # Codebase graph data
    b_data = load_json(Path(args.pipeline_b_data)) if args.pipeline_b_data else None

    generate_report(
        project_name=args.project_name,
        project_path=args.project_path,
        a_cpp=a_cpp,
        a_qml=a_qml,
        b_data=b_data,
        output_dir=args.output,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())