#!/usr/bin/env python3
"""AT 用例覆盖率统计 (coverage_atcase).

统计应用项目 AT 用例对 UI 元素的覆盖情况 (接力 coverage_stats.py):

  AT 用例覆盖率 = min(covered_refs, scan_total) / scan_total × 100%  (封顶 100%)

  - covered_refs (分子) : suite 引用全集 = selector.name ∪ items: 菜单项, 去重去噪
      selector.name  : 用例通过元素定位引用的持久元素
      items:         : 用例通过菜单动作 (dtk_main_menu/dtk_context_menu) 引用的瞬态菜单项
  - scan_total (分母)   : coverage_stats.py 扫描出的交互控件总数 (源码扫描结果)
      scan_total 不在此脚本计算, 从扫描产物读取 (pre_report.json 的 summary.total_widgets,
      或 pre_scan_gaps.yaml 的 summary.total_widgets), 也可 --total 直接传入

为什么封顶:
  covered_refs 含瞬态 items 菜单项, 它们不在 scan_total (源码交互控件) 内,
  因此 covered_refs 可能 > scan_total。封顶 100% 表示"用例引用已覆盖全部扫描交互控件"。

elements.yaml 仅用于辅助报告, 不决定分子/分母:
  - covered_in_inventory   : covered_refs ∩ elements.yaml (清单内覆盖)
  - refs_not_in_inventory  : covered_refs - elements.yaml (清单外瞬态引用)
  - scan_named_not_in_inventory: 扫描已命名控件 - elements.yaml (清单缺口)
  - inventory_uncovered    : elements.yaml - covered_refs (用例缺口)
  - noise_removed          : 剔除的文件名噪音 (含 '.')

若项目不存在 AT 用例 (tests/at/yaml/ 下无 *.suite.yaml), 覆盖率记为 0。

Usage:
    # 1. 先运行 coverage_stats.py 得到 scan_total (扫描产物写入 <outdir>/coverage_scan/)
    python3 scripts/coverage_stats.py --src /path/to/repo --cpp-only -o coverage_report.json

    # 2. 接力计算 AT 用例覆盖率 (自动发现 <repo>/coverage_scan/ 或 ./coverage_scan/)
    python3 scripts/coverage_atcase.py --src /path/to/repo

    # 显式指定扫描产物目录 / 直接传 scan_total
    python3 scripts/coverage_atcase.py --src /path/to/repo --scan-dir /path/to/coverage_scan
    python3 scripts/coverage_atcase.py --src /path/to/repo --total <N>
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> Any:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[WARN] 读取 {path} 失败: {e}", file=sys.stderr)
        return None


def _load_yaml(path: Path) -> Any:
    try:
        import yaml
    except ImportError:
        print("[FAIL] 缺少依赖 pyyaml, 请先: pip install pyyaml", file=sys.stderr)
        sys.exit(1)
    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"[WARN] 解析 {path} 失败: {e}", file=sys.stderr)
        return None


def _iter_suite_refs(node: Any, selectors: set[str], items: set[str]) -> None:
    """递归遍历 suite 结构, 收集 selector.name 与 items: 菜单项。"""
    if isinstance(node, dict):
        sel = node.get("selector")
        if isinstance(sel, dict):
            n = sel.get("name")
            if isinstance(n, str):
                selectors.add(n.strip())
        if "items" in node and isinstance(node["items"], list):
            for it in node["items"]:
                if isinstance(it, str):
                    items.add(it.strip())
        for v in node.values():
            _iter_suite_refs(v, selectors, items)
    elif isinstance(node, list):
        for v in node:
            _iter_suite_refs(v, selectors, items)


def _collect_suite_refs(at_dir: Path) -> tuple[set[str], set[str], int]:
    """收集所有 *.suite.yaml 的 selector 与 items 去重集合, 返回 (selectors, items, suite_count)。"""
    selectors: set[str] = set()
    items: set[str] = set()
    suite_count = 0
    for sf in sorted(at_dir.rglob("*.suite.yaml")):
        suite_count += 1
        data = _load_yaml(sf)
        if data is not None:
            _iter_suite_refs(data, selectors, items)
    return selectors, items, suite_count


def _collect_elements_yaml(elements_yaml: Path) -> set[str]:
    """从 elements.yaml 的 `elements` map 收集元素 name 去重集合。"""
    names: set[str] = set()
    data = _load_yaml(elements_yaml)
    if not isinstance(data, dict):
        return names
    elements = data.get("elements") or {}
    if not isinstance(elements, dict):
        return names
    for _, v in elements.items():
        if isinstance(v, dict):
            n = v.get("name")
            if isinstance(n, str):
                names.add(n.strip())
        elif isinstance(v, str):
            names.add(v.strip())
    return names


def _collect_scan_named(scan_dir: Path) -> set[str]:
    """从扫描产物收集已命名控件名 (existing_accessible_name / existing_object_name), 用于清单缺口报告。"""
    names: set[str] = set()
    for fname in ("pre_scan_ok.yaml", "pre_scan_gaps.yaml"):
        p = scan_dir / fname
        if not p.is_file():
            continue
        data = _load_yaml(p)
        if not isinstance(data, dict):
            continue
        items = data.get("widgets") or data.get("gaps") or []
        for w in items:
            if not isinstance(w, dict):
                continue
            n = w.get("existing_accessible_name") or w.get("existing_object_name") or ""
            if isinstance(n, str) and n:
                names.add(n.strip())
    return names


def _is_noise(name: str) -> bool:
    """判断 name 是否为文件名噪音: 包含 '.' 分隔符 (如 normal.pdf)。

    SPI 元素名称不包含 '.', 只有文件名才包含, 因此直接按 '.' 识别。
    """
    return "." in name


def _denoise(names: set[str]) -> set[str]:
    return {n for n in names if n and not _is_noise(n)}


def _load_scan_total(scan_dir: Path) -> int | None:
    """从 coverage_stats.py 扫描产物读取 total (应编写元素总数)。

    优先读 pre_report.json, 回退到 pre_scan_gaps.yaml 的 summary.total_widgets。
    """
    pre_report = scan_dir / "pre_report.json"
    if pre_report.is_file():
        data = _load_json(pre_report)
        if isinstance(data, dict):
            sm = data.get("summary") or {}
            total = sm.get("total_widgets")
            if isinstance(total, int) and total >= 0:
                return total

    pre_gaps = scan_dir / "pre_scan_gaps.yaml"
    if pre_gaps.is_file():
        data = _load_yaml(pre_gaps)
        if isinstance(data, dict):
            sm = data.get("summary") or {}
            total = sm.get("total_widgets")
            if isinstance(total, int) and total >= 0:
                return total
    return None


def _find_scan_dir(src: Path) -> Path | None:
    """自动发现扫描产物目录: <src>/coverage_scan, ./coverage_scan。"""
    for cand in (src / "coverage_scan", Path("coverage_scan")):
        if (cand / "pre_report.json").is_file() or (cand / "pre_scan_gaps.yaml").is_file():
            return cand
    return None


def _pct(numer: int, denom: int) -> float:
    return round(numer / denom * 100, 1) if denom else 0.0


def main() -> int:
    ap = argparse.ArgumentParser(description="AT 用例覆盖率统计 (接力 coverage_stats.py)")
    ap.add_argument("--src", required=True, help="目标项目源码根目录 (repo root)")
    ap.add_argument("--at-dir", help="AT 用例目录 (默认 <src>/tests/at/yaml)")
    ap.add_argument("--scan-dir", help="coverage_stats.py 扫描产物目录 (含 pre_report.json)")
    ap.add_argument("--total", type=int, help="直接指定元素总数 total (跳过扫描产物读取)")
    ap.add_argument("--output", "-o", default="coverage_atcase.json", help="JSON 报告输出路径")
    ap.add_argument("--md-report", default="coverage_atcase.md",
                    help="Markdown 报告输出路径 (默认 coverage_atcase.md; 置空则不生成)")
    ap.add_argument("--threshold", type=float, default=80.0, help="覆盖率阈值 (默认 80)")
    ap.add_argument("--list-elements", action="store_true", help="打印已覆盖元素明细")
    args = ap.parse_args()

    src = Path(args.src)
    if not src.is_dir():
        print(f"[FAIL] --src 不是有效目录: {src}", file=sys.stderr)
        return 1
    at_dir = Path(args.at_dir) if args.at_dir else src / "tests" / "at" / "yaml"

    # ---- total: coverage_stats.py 扫描结果 (本脚本不计算) ----
    total: int | None = args.total
    total_source = f"--total {total}" if total is not None else ""
    scan_dir: Path | None = None
    if total is None:
        scan_dir = Path(args.scan_dir) if args.scan_dir else _find_scan_dir(src)
        if scan_dir is None:
            print("[FAIL] 未找到 coverage_stats.py 扫描产物 (coverage_scan/pre_report.json)。", file=sys.stderr)
            print("       请先运行: python3 scripts/coverage_stats.py --src <repo> -o coverage_report.json", file=sys.stderr)
            print("       或直接传入: --total <元素总数> / --scan-dir <coverage_scan 目录>", file=sys.stderr)
            return 1
        total = _load_scan_total(scan_dir)
        total_source = f"{scan_dir}/pre_report.json"
        if total is None:
            print(f"[FAIL] 扫描产物 {scan_dir} 中未找到 total_widgets 字段。", file=sys.stderr)
            return 1

    # ---- suite 引用: selector ∪ items ----
    if at_dir.is_dir():
        selectors_raw, items_raw, suite_count = _collect_suite_refs(at_dir)
    else:
        selectors_raw, items_raw, suite_count = set(), set(), 0

    # ---- elements.yaml 权威清单 ----
    elements_yaml = at_dir / "elements.yaml"
    has_elements_yaml = at_dir.is_dir() and elements_yaml.is_file()

    if has_elements_yaml:
        ui_raw = _collect_elements_yaml(elements_yaml)
        ui_clean = _denoise(ui_raw)
        noise_removed = sorted({n for n in ui_raw if _is_noise(n)})
        elements_source = "elements.yaml"
    else:
        ui_clean = set()
        noise_removed = sorted(
            {n for n in selectors_raw if _is_noise(n)} | {n for n in items_raw if _is_noise(n)}
        )
        elements_source = "*.suite.yaml"

    # 去噪: selector 与 items 都剔文件名噪音
    selectors = _denoise(selectors_raw)
    items = _denoise(items_raw)

    # 分子: suite 引用全集 (selector ∪ items 去重) —— items 引用也算覆盖
    covered_refs = selectors | items
    # 清单内覆盖 (辅助): covered_refs ∩ elements.yaml
    covered_in_inventory = covered_refs & ui_clean if has_elements_yaml else covered_refs

    covered_n = len(covered_refs)
    # 封顶 100%: covered_refs 可能因瞬态菜单项超过 scan_total
    eff_covered = min(covered_n, total)
    cov = _pct(eff_covered, total)
    no_cases = suite_count == 0
    # ---- 辅助报告 ----
    inventory_uncovered = sorted(ui_clean - covered_refs) if has_elements_yaml else []
    scan_named_not_in_inventory: list[str] = []
    if has_elements_yaml and scan_dir is not None:
        scan_named = _denoise(_collect_scan_named(scan_dir))
        scan_named_not_in_inventory = sorted(scan_named - ui_clean)
    refs_not_in_inventory = sorted(covered_refs - ui_clean) if has_elements_yaml else []

    print("=" * 60)
    print("AT 用例覆盖率统计")
    print("=" * 60)
    print(f"  项目       : {src.name}")
    print(f"  AT 用例目录: {at_dir}")
    print(f"  total 来源 : {total_source}")
    print(f"  suite 文件 : {suite_count}")
    print(f"  elements 来源: {elements_source}")

    if no_cases:
        print("\n[WARN] 未找到 AT 用例 (tests/at/yaml 下无 *.suite.yaml), 覆盖率记为 0。")
    else:
        print(f"  扫描交互控件 (total) : {total}")
        print(f"  用例覆盖引用 (covered): {covered_n} (selector ∪ items 去重, 含瞬态 items)")
        print(f"  其中清单内           : {len(covered_in_inventory)} 个")
        print(f"  覆盖率               : {cov}%")
        if covered_n > total:
            print(f"  [INFO] covered({covered_n}) > total({total}), 覆盖率按 total 封顶。")
        if noise_removed:
            print(f"  [INFO] 已剔除文件名噪音: {', '.join(noise_removed)}")
        if refs_not_in_inventory:
            print(f"  [INFO] 用例引用的清单外元素 ({len(refs_not_in_inventory)} 个, 瞬态菜单项等): "
                  f"{', '.join(refs_not_in_inventory[:20])}")
        if scan_named_not_in_inventory:
            print(f"  [INFO] 扫描已命名但清单缺失 ({len(scan_named_not_in_inventory)} 个): "
                  f"{', '.join(scan_named_not_in_inventory)}")
        if inventory_uncovered:
            print(f"  [INFO] 清单未覆盖 ({len(inventory_uncovered)} 个): "
                  f"{', '.join(inventory_uncovered[:20])}")
        if args.list_elements:
            print("\n--- 已覆盖引用明细 ---")
            for n in sorted(covered_refs):
                print(f"    {n}")
        print(f"       阈值: {args.threshold}%  -> {'PASS' if cov >= args.threshold else 'FAIL'}")

    report = {
        "project": src.name,
        "at_dir": str(at_dir),
        "total_source": total_source,
        "suite_count": suite_count,
        "elements_source": elements_source,
        "no_cases": no_cases,
        "total": total,
        "covered_in_inventory": len(covered_in_inventory),
        "covered_refs": covered_n,
        "coverage": cov,
        "noise_removed": noise_removed,
        "refs_not_in_inventory": refs_not_in_inventory,
        "scan_named_not_in_inventory": scan_named_not_in_inventory,
        "inventory_uncovered": inventory_uncovered,
        "threshold": args.threshold,
        "passed": (not no_cases) and cov >= args.threshold,
    }
    rpath = Path(args.output)
    with open(rpath, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\nJSON 报告已写入: {rpath}")

    if args.md_report:
        md_path = Path(args.md_report)
        L = [
            "# AT 用例覆盖率报告",
            "",
            f"- 项目: `{src.name}`",
            f"- 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"- AT 用例目录: `{at_dir}`",
            f"- total 来源: `{total_source}`",
            f"- suite 文件数: {suite_count}",
            "",
            "## 覆盖率",
            "",
            "| 指标 | 值 |",
            "|------|-----|",
            f"| 用例覆盖引用 (covered_refs, 含瞬态 items) | {covered_n} |",
            f"| 扫描交互控件 (total) | {total} |",
            f"| 阈值 | {args.threshold}% |",
            f"| 结果 | {'PASS' if report['passed'] else 'FAIL'} |",
            "",
        ]
        if noise_removed:
            L += [f"- 已剔除文件名噪音: {', '.join(noise_removed)}"]
        if refs_not_in_inventory:
            L += [f"- suite 引用的清单外元素 (瞬态菜单项等): {', '.join(refs_not_in_inventory)}"]
        if scan_named_not_in_inventory:
            L += [f"- 扫描已命名但清单缺失: {', '.join(scan_named_not_in_inventory)}"]
        if no_cases:
            L += ["> 未找到 AT 用例, 覆盖率记为 0。"]
        md_path.write_text("\n".join(L), encoding="utf-8")
        print(f"MD 报告已写入: {md_path}")

    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
