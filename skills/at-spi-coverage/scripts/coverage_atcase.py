#!/usr/bin/env python3
"""AT 用例覆盖率统计 (coverage_atcase).

统计应用项目 AT 用例对 UI 元素的覆盖情况 (接力 coverage_stats.py):

  AT 用例覆盖率 = min(covered_refs, scan_total) / scan_total × 100%  (封顶 100%)

  - covered_refs (分子) : suite 引用的持久元素全集 = selector.name, 去重去噪
      selector.name  : 用例通过元素定位引用的持久元素
      瞬态菜单项 (dtk_main_menu/dtk_context_menu 的 items) 不计入覆盖,
      单独在报告 (transient_items) 中列出, 仅供查看
  - scan_total (分母)   : coverage_stats.py 扫描出的交互控件总数 (源码扫描结果)
      scan_total 不在此脚本计算, 从扫描产物读取 (pre_report.json 的 summary.total_widgets,
      或 pre_scan_gaps.yaml 的 summary.total_widgets), 也可 --total 直接传入

为什么封顶:
  即使剔除瞬态 items, 分子仍可能与扫描口径不完全一致, 保留封顶 100% 表示
  "用例引用已覆盖全部扫描交互控件"。

AT 用例目录 (默认 <src>/tests/at/yaml):
  - 显式 --at-dir 指定
  - 否则自动发现 <src>/tests/at/ 下含 *.suite.yaml 的子目录
    (支持 tests/at/yaml, tests/at/yaml_xxx 等任意命名; 不存在则覆盖率为 0)
  - elements.yaml 按上述发现的目录就近查找, 仅用于辅助报告
    (清单内覆盖 / 清单缺口), 不决定分子/分母; 无 elements.yaml 时
    直接从 *.suite.yaml 计算分子, 不报 0

elements.yaml 仅用于辅助报告:
  - covered_in_inventory   : covered_refs ∩ elements.yaml (清单内覆盖)
  - refs_not_in_inventory  : covered_refs - elements.yaml (清单外引用)
  - transient_items        : suite 中瞬态菜单项 (不参与覆盖计算)
  - scan_named_not_in_inventory: 扫描已命名控件 - elements.yaml (清单缺口)
  - inventory_uncovered    : elements.yaml - covered_refs (用例缺口)
  - noise_removed          : 剔除的文件名噪音 (含 '.')

若项目不存在 AT 用例 (找不到含 *.suite.yaml 的目录), 覆盖率记为 0。

用例数统计:
  用例数以 suite 内的 `- id` 条目计 (case_count), 一个 *.suite.yaml 可含
  多个 case (suites: 列表下每个带 id 的条目算 1 个用例); suite 文件数
  (suite_files) 仅作辅助展示, 不作为用例数。

Usage:
    # 1. 先运行 coverage_stats.py 得到 scan_total (扫描产物写入 <outdir>/coverage_scan/)
    python3 scripts/coverage_stats.py --src /path/to/repo --cpp-only -o coverage_report.json

    # 2. 接力计算 AT 用例覆盖率 (自动发现 <repo>/coverage_scan/ 或 ./coverage_scan/)
    python3 scripts/coverage_atcase.py --src /path/to/repo

    # 显式指定扫描产物目录 / 直接传 scan_total
    python3 scripts/coverage_atcase.py --src /path/to/repo --scan-dir /path/to/coverage_scan
    python3 scripts/coverage_atcase.py --src /path/to/repo --total <N>

    # 显式指定 AT 用例目录 (跳过自动发现)
    python3 scripts/coverage_atcase.py --src /path/to/repo --at-dir /path/to/tests/at/yaml_xxx
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# 瞬态菜单动作: 其 items 为瞬态菜单项 (键盘导航文本), 不计入覆盖
TRANSIENT_MENU_ACTIONS = frozenset({"dtk_main_menu", "dtk_context_menu"})
# 持久菜单动作: dtk_dropdown_menu 的 items 是 DDropdownMenu 项 objectName
# 后缀 (与 selector.accessible_id 同键空间, 持久占位节点), 计入覆盖
PERSISTENT_MENU_ACTIONS = frozenset({"dtk_dropdown_menu"})


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
    """递归遍历 suite 结构, 收集 selector 定位键 (持久) 与 items (瞬态菜单项)。

    selector 定位键 = name 与 accessible_id 并集:
      - name           : AT-SPI 可见名 (setAccessibleName / 控件文本)
      - accessible_id  : Qt6 bridge 编码的 objectName 点分路径后缀
                         (executor 后缀匹配定位, 见 df20e47)
    两类键都可能定位持久元素, 均计入覆盖。
    items 收集分两类:
      - 瞬态菜单动作 (dtk_main_menu / dtk_context_menu): items 是键盘导航
        文本, 关闭态无节点 → 不计入覆盖, 单独汇总。
      - 持久菜单动作 (dtk_dropdown_menu): items 是 DDropdownMenu 项
        objectName 后缀 (与 selector.accessible_id 同键空间, 关闭态树有
        占位节点) → 计入覆盖。
    """
    if isinstance(node, dict):
        sel = node.get("selector")
        if isinstance(sel, dict):
            for key in ("name", "accessible_id"):
                n = sel.get(key)
                if isinstance(n, str) and n.strip():
                    selectors.add(n.strip())
        action = node.get("action")
        if isinstance(action, str) and isinstance(node.get("items"), list):
            for it in node["items"]:
                if not isinstance(it, str) or not it.strip():
                    continue
                if action in TRANSIENT_MENU_ACTIONS:
                    items.add(it.strip())
                elif action in PERSISTENT_MENU_ACTIONS:
                    selectors.add(it.strip())
        for v in node.values():
            _iter_suite_refs(v, selectors, items)
    elif isinstance(node, list):
        for v in node:
            _iter_suite_refs(v, selectors, items)


def _iter_refs_by_type(node: Any, name_refs: set[str], aid_refs: set[str]) -> None:
    """递归遍历 suite 结构, 按定位键类型收集引用 (辅助统计用)。"""
    if isinstance(node, dict):
        sel = node.get("selector")
        if isinstance(sel, dict):
            n = sel.get("name")
            if isinstance(n, str) and n.strip():
                name_refs.add(n.strip())
            a = sel.get("accessible_id")
            if isinstance(a, str) and a.strip():
                aid_refs.add(a.strip())
        # dtk_dropdown_menu 的 items 是 objectName 后缀 → 归 aid_refs
        if node.get("action") in PERSISTENT_MENU_ACTIONS and isinstance(node.get("items"), list):
            for it in node["items"]:
                if isinstance(it, str) and it.strip():
                    aid_refs.add(it.strip())
        for v in node.values():
            _iter_refs_by_type(v, name_refs, aid_refs)
    elif isinstance(node, list):
        for v in node:
            _iter_refs_by_type(v, name_refs, aid_refs)


def _count_suite_cases(node: Any) -> int:
    """统计 suite 结构中的用例数: 每个 `suites:` 列表下的 `- id` 条目算 1 个 case。

    一个 *.suite.yaml 可含多个 case (suites 列表的每个 - id)。递归处理
    setup / teardown / 嵌套 suites, 只统计带 `id` 的用例条目。
    """
    count = 0
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "suites" and isinstance(v, list):
                for c in v:
                    if isinstance(c, dict) and isinstance(c.get("id"), str):
                        count += 1
                        count += _count_suite_cases(c)
            else:
                count += _count_suite_cases(v)
    elif isinstance(node, list):
        for v in node:
            count += _count_suite_cases(v)
    return count


def _collect_suite_refs(at_dir: Path) -> tuple[set[str], set[str], int, int]:
    """收集所有 *.suite.yaml 的 selector (持久) 与 items (瞬态) 去重集合。

    返回 (selectors, items, case_count, suite_files):
    - case_count  : 所有 suite 文件 `suites:` 列表下 `- id` 用例总数 (一个文件含多 case)
    - suite_files : *.suite.yaml 文件数
    """
    selectors: set[str] = set()
    items: set[str] = set()
    case_count = 0
    suite_files = 0
    for sf in sorted(at_dir.rglob("*.suite.yaml")):
        suite_files += 1
        data = _load_yaml(sf)
        if data is not None:
            case_count += _count_suite_cases(data)
            _iter_suite_refs(data, selectors, items)
    return selectors, items, case_count, suite_files


def _collect_elements_yaml(elements_yaml: Path) -> set[str]:
    """从 elements.yaml 的 `elements` map 收集定位键 (name + accessible_id) 去重集合。

    elements.yaml 的条目可含 name 与/或 accessible_id (生成链
    yaml_generator 已透传 accessible_id, 见 MappingSelector)。两类键都
    是持久定位键, 都用于清单内覆盖统计。
    """
    names: set[str] = set()
    data = _load_yaml(elements_yaml)
    if not isinstance(data, dict):
        return names
    elements = data.get("elements") or {}
    if not isinstance(elements, dict):
        return names
    for _, v in elements.items():
        if isinstance(v, dict):
            for key in ("name", "accessible_id"):
                n = v.get(key)
                if isinstance(n, str):
                    names.add(n.strip())
        elif isinstance(v, str):
            names.add(v.strip())
    return names


def _collect_scan_named(scan_dir: Path) -> set[str]:
    """从扫描产物收集已命名控件名 (existing_accessible_name / existing_object_name), 用于清单缺口报告。"""
    names: set[str] = set()
    for fname in ("pre_scan_ok.yaml", "pre_scan_gaps.yaml", "qml_ok.yaml", "qml_gaps.yaml"):
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
            # QML 产物用 accessible_name 字段
            n2 = w.get("accessible_name")
            if isinstance(n2, str) and n2:
                names.add(n2.strip())
    return names


def _is_noise(name: str) -> bool:
    """判断 name 是否为文件名噪音: 包含 '.' 分隔符 (如 normal.pdf)。

    SPI 元素名称不包含 '.', 只有文件名才包含, 因此直接按 '.' 识别。
    """
    return "." in name


def _denoise(names: set[str]) -> set[str]:
    return {n for n in names if n and not _is_noise(n)}


def _collect_unreachable_names(scan_dir: Path) -> set[str]:
    """收集 unreachable.yaml 中仍计入 at_locatable_total 的运行时豁免名。

    unreachable.yaml (tests/at/unreachable.yaml) 列出的元素是运行时 AT-SPI
    树中按名不可定位的豁免项。at_locatable_total 已剔除 QAction 家族与容器,
    因此这里只收集仍计数的 **widget 类型** 豁免 (如 PButton, 声明为
    DPushButton 但运行时从不构造)。通过扫描产物 (pre_scan_ok/gaps.yaml) 的
    type 判断: 非 widget 交互类型 (QAction/DAction/QShortcut) 已在分母外,
    不重复扣除。返回应再从分母扣除的 name 集合。
    """
    # 扫描产物 name -> type (用于判断是否 widget 类型)
    scan_types: dict[str, str] = {}
    for fname in ("pre_scan_ok.yaml", "pre_scan_gaps.yaml"):
        data = _load_yaml(scan_dir / fname)
        if not isinstance(data, dict):
            continue
        items = data.get("widgets") or data.get("gaps") or []
        for w in items:
            if not isinstance(w, dict):
                continue
            n = w.get("existing_accessible_name") or w.get("existing_object_name") or ""
            t = w.get("type", "")
            if n and t:
                scan_types.setdefault(n.strip(), t)
    # non-widget 交互类型 (仅在源码命名口径计入, at_locatable_total 已剔除)
    _NON_WIDGET = {"QAction", "DAction", "QShortcut"}
    names: set[str] = set()
    unreachable = scan_dir.parent / "tests" / "at" / "unreachable.yaml"
    # 也支持显式 at_dir 下的 unreachable
    for cand in (unreachable, scan_dir.parent / "unreachable.yaml"):
        data = _load_yaml(cand)
        if not isinstance(data, dict):
            continue
        entries = data.get("unreachable", [])
        for e in entries:
            if not isinstance(e, dict):
                continue
            nm = e.get("name", "")
            if not nm:
                continue
            # 若扫描产物能定位其类型且为 widget (非 QAction 家族) → 需扣除。
            # 若扫描产物中查不到该 name (说明已被 at_locatable_total 排除,
            # 如容器 ActionGroup/Group), 不重复扣。
            t = scan_types.get(nm, "")
            base = t.replace(" *", "").replace("*", "").split("<")[0].strip()
            if not t:
                continue  # 扫描产物中不存在 → 已在分母外, 不重复扣
            if base in _NON_WIDGET:
                continue  # 已在 at_locatable_total 之外, 不重复扣
            names.add(nm)
    return names


def _read_total_from(data: Any, keys: tuple[str, ...]) -> int | None:
    """从扫描产物 dict 读取 total 字段 (C++: total_widgets, QML: total_elements)。"""
    if not isinstance(data, dict):
        return None
    sm = data.get("summary") or {}
    for k in keys:
        v = sm.get(k)
        if isinstance(v, int) and v > 0:
            return v
    return None


def _load_scan_total(
    scan_dir: Path, key: str = "at_locatable_total"
) -> tuple[int | None, str]:
    """从 coverage_stats.py 扫描产物读取 total (应编写元素总数)。

    口径由 `key` 选择 (C++ 产物中同时存在):
      - at_locatable_total      : 按名可定位 (剔非 widget 交互 + 容器; 含
                                  仅 objectName 的 QAction 家族, Qt6 编码进
                                  accessible_id 后可定位)
      - at_locatable_by_aid_total: 按 accessible_id 可定位 (剔仅
                                  setAccessibleName 的 widget; 纯 objectName
                                  应用用此口径)
    回退 summary.total_widgets (源码命名口径)。C++ 与 QML 分别读取后求和
    (混合项目两者都有控件时 total = cpp + qml):
    - C++: pre_report.json, 回退 pre_scan_gaps.yaml
    - QML: qml_report.json, 回退 qml_gaps.yaml (summary.total_elements)
    返回 (total, source_label); 无任何产物时返回 (None, "")。
    """
    cpp_total: int | None = None
    cpp_src = ""
    pre_report = scan_dir / "pre_report.json"
    if pre_report.is_file():
        t = _read_total_from(_load_json(pre_report), (key, "at_locatable_total", "total_widgets"))
        if t is not None:
            cpp_total, cpp_src = t, "pre_report.json"
    if cpp_total is None:
        pre_gaps = scan_dir / "pre_scan_gaps.yaml"
        if pre_gaps.is_file():
            t = _read_total_from(_load_yaml(pre_gaps), (key, "at_locatable_total", "total_widgets"))
            if t is not None:
                cpp_total, cpp_src = t, "pre_scan_gaps.yaml"

    qml_total: int | None = None
    qml_src = ""
    qml_report = scan_dir / "qml_report.json"
    if qml_report.is_file():
        t = _read_total_from(_load_json(qml_report), ("total_elements",))
        if t is not None:
            qml_total, qml_src = t, "qml_report.json"
    if qml_total is None:
        qml_gaps = scan_dir / "qml_gaps.yaml"
        if qml_gaps.is_file():
            t = _read_total_from(_load_yaml(qml_gaps), ("total_elements",))
            if t is not None:
                qml_total, qml_src = t, "qml_gaps.yaml"

    if cpp_total is None and qml_total is None:
        return None, ""
    total = (cpp_total or 0) + (qml_total or 0)
    if cpp_total is not None and qml_total is not None:
        label = f"{cpp_src}+{qml_src}"
    else:
        label = cpp_src or qml_src
    return total, label


def _find_scan_dir(src: Path) -> Path | None:
    """自动发现扫描产物目录: <src>/coverage_scan, ./coverage_scan。

    接受 C++ 产物 (pre_report.json / pre_scan_gaps.yaml) 或纯 QML 产物
    (qml_report.json / qml_gaps.yaml)。
    """
    for cand in (src / "coverage_scan", Path("coverage_scan")):
        if (cand / "pre_report.json").is_file() or (cand / "pre_scan_gaps.yaml").is_file() \
                or (cand / "qml_report.json").is_file() or (cand / "qml_gaps.yaml").is_file():
            return cand
    return None


def _find_at_dir(src: Path, at_dir: Path | None) -> Path | None:
    """定位 AT 用例目录: 显式 --at-dir > 自动发现 <src>/tests/at/ 下含 *.suite.yaml 的子目录。

    <src>/tests/at/yaml 只是常见命名; 实际扫描的是任意含 *.suite.yaml 的子目录
    (tests/at/yaml, tests/at/yaml_xxx 等)。返回 None 表示项目无 AT 用例。
    """
    if at_dir is not None:
        return at_dir if any(at_dir.rglob("*.suite.yaml")) else None
    base = src / "tests" / "at"
    if base.is_dir():
        hits = [d for d in base.iterdir() if d.is_dir() and any(d.rglob("*.suite.yaml"))]
        if hits:
            return sorted(hits)[0]
    return None


def _pct(numer: int, denom: int) -> float:
    return round(numer / denom * 100, 1) if denom else 0.0


def main() -> int:
    ap = argparse.ArgumentParser(description="AT 用例覆盖率统计 (接力 coverage_stats.py)")
    ap.add_argument("--src", required=True, help="目标项目源码根目录 (repo root)")
    ap.add_argument("--at-dir", help="AT 用例目录 (默认自动发现 <src>/tests/at/ 下含 *.suite.yaml 的子目录)")
    ap.add_argument("--scan-dir", help="coverage_stats.py 扫描产物目录 (含 pre_report.json)")
    ap.add_argument("--total", type=int, help="直接指定元素总数 total (跳过扫描产物读取)")
    ap.add_argument("--aid-denominator", action="store_true",
                    help="分母用 at_locatable_by_aid_total (纯 objectName 应用; 默认 at_locatable_total)")
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
    at_dir = _find_at_dir(src, Path(args.at_dir) if args.at_dir else None)

    # ---- total: coverage_stats.py 扫描结果 (本脚本不计算) ----
    total: int | None = args.total
    total_source = f"--total {total}" if total is not None else ""
    scan_dir: Path | None = None
    if total is None:
        scan_dir = Path(args.scan_dir) if args.scan_dir else _find_scan_dir(src)
        if scan_dir is None:
            print("[FAIL] 未找到 coverage_stats.py 扫描产物 (coverage_scan/pre_report.json 或 qml_report.json)。", file=sys.stderr)
            print("       请先运行: python3 scripts/coverage_stats.py --src <repo> -o coverage_report.json", file=sys.stderr)
            print("       或直接传入: --total <元素总数> / --scan-dir <coverage_scan 目录>", file=sys.stderr)
            return 1
        total, total_src = _load_scan_total(
            scan_dir, key="at_locatable_by_aid_total" if args.aid_denominator else "at_locatable_total"
        )
        total_source = f"{scan_dir}/{total_src}" if total_src else f"{scan_dir}/pre_report.json"
        if total is None:
            print(f"[FAIL] 扫描产物 {scan_dir} 中未找到 total_widgets / total_elements 字段。", file=sys.stderr)
            return 1

    # 运行时豁免: unreachable.yaml 中仍计入 at_locatable_total 的 widget 类型
    # (如 PButton, 声明为 DPushButton 但运行时从不构造) 从分母扣除。
    runtime_exempt: set[str] = set()
    if total is not None and scan_dir is not None:
        runtime_exempt = _collect_unreachable_names(scan_dir)
        if runtime_exempt:
            total -= len(runtime_exempt)
            total_source += f" (豁免 {len(runtime_exempt)} 运行时不可定位)"

    # ---- suite 引用: selector (持久) + items (瞬态, 不计覆盖) ----
    if at_dir is not None:
        selectors_raw, items_raw, case_count, suite_files = _collect_suite_refs(at_dir)
    else:
        selectors_raw, items_raw, case_count, suite_files = set(), set(), 0, 0

    # ---- elements.yaml 权威清单 ----
    elements_yaml = at_dir / "elements.yaml" if at_dir is not None else None
    has_elements_yaml = elements_yaml is not None and elements_yaml.is_file()
    elements_yaml_path = elements_yaml if has_elements_yaml else None

    if has_elements_yaml:
        ui_raw = _collect_elements_yaml(elements_yaml_path)
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

    # 分子: 持久 selector 引用全集 —— 瞬态 items 不计入覆盖
    covered_refs = selectors
    # 清单内覆盖 (辅助): covered_refs ∩ elements.yaml
    covered_in_inventory = covered_refs & ui_clean if has_elements_yaml else covered_refs

    covered_n = len(covered_refs)
    # 封顶 100%: 分子可能与扫描口径不完全一致
    eff_covered = min(covered_n, total)
    cov = _pct(eff_covered, total)
    no_cases = case_count == 0
    # ---- 辅助报告 ----
    transient_items = sorted(items)  # 瞬态菜单项, 不参与覆盖计算
    inventory_uncovered = sorted(ui_clean - covered_refs) if has_elements_yaml else []
    scan_named_not_in_inventory: list[str] = []
    if has_elements_yaml and scan_dir is not None:
        scan_named = _denoise(_collect_scan_named(scan_dir))
        scan_named_not_in_inventory = sorted(scan_named - ui_clean)
    refs_not_in_inventory = sorted(covered_refs - ui_clean) if has_elements_yaml else []
    # 引用类型统计 (辅助): 分别计数 name / accessible_id 引用
    name_refs: set[str] = set()
    aid_refs: set[str] = set()
    if at_dir is not None:
        for sf in sorted(at_dir.rglob("*.suite.yaml")):
            data = _load_yaml(sf)
            if data is None:
                continue
            _iter_refs_by_type(data, name_refs, aid_refs)

    print("=" * 60)
    print("AT 用例覆盖率统计")
    print("=" * 60)
    print(f"  项目       : {src.resolve().name}")
    print(f"  AT 用例目录: {at_dir}")
    print(f"  total 来源 : {total_source}")
    print(f"  用例 (case) : {case_count} 个 (suite 文件 {suite_files} 个)")
    print(f"  elements 来源: {elements_source}")

    if no_cases:
        print("\n[WARN] 未找到 AT 用例 (tests/at/ 下无含 *.suite.yaml 的目录), 覆盖率记为 0。")
    else:
        print(f"  扫描交互控件 (total) : {total}")
        print(f"  用例覆盖引用 (covered): {covered_n} (selector 去重, 不含瞬态 items)")
        print(f"    其中 name 引用      : {len(name_refs)} 个 | accessible_id 引用: {len(aid_refs)} 个")
        print(f"  其中清单内           : {len(covered_in_inventory)} 个")
        print(f"  覆盖率               : {cov}%")
        if covered_n > total:
            print(f"  [INFO] covered({covered_n}) > total({total}), 覆盖率按 total 封顶。")
        if transient_items:
            print(f"  [INFO] 瞬态菜单项 (不计覆盖, {len(transient_items)} 个): "
                  f"{', '.join(transient_items[:20])}")
        if noise_removed:
            print(f"  [INFO] 已剔除文件名噪音: {', '.join(noise_removed)}")
        if refs_not_in_inventory:
            print(f"  [INFO] 用例引用的清单外元素 ({len(refs_not_in_inventory)} 个): "
                  f"{', '.join(refs_not_in_inventory[:20])}")
        if scan_named_not_in_inventory:
            print(f"  [INFO] 扫描已命名但清单缺失 ({len(scan_named_not_in_inventory)} 个): "
                  f"{', '.join(scan_named_not_in_inventory)}")
        if inventory_uncovered:
            print(f"  [INFO] 清单未覆盖 ({len(inventory_uncovered)} 个): "
                  f"{', '.join(inventory_uncovered[:20])}")
        if args.list_elements:
            print("\n--- 已覆盖引用明细 (持久 selector) ---")
            for n in sorted(covered_refs):
                print(f"    {n}")
            if transient_items:
                print("\n--- 瞬态菜单项 (不计覆盖) ---")
                for n in transient_items:
                    print(f"    {n}")
        print(f"       阈值: {args.threshold}%  -> {'PASS' if cov >= args.threshold else 'FAIL'}")

    report = {
        "project": src.name,
        "at_dir": str(at_dir) if at_dir is not None else None,
        "total_source": total_source,
        "case_count": case_count,
        "suite_files": suite_files,
        "elements_source": elements_source,
        "no_cases": no_cases,
        "total": total,
        "covered_in_inventory": len(covered_in_inventory),
        "name_refs": len(name_refs),
        "aid_refs": len(aid_refs),
        "covered_refs": covered_n,
        "transient_items": transient_items,
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
            f"- 用例数 (case): {case_count} 个 (suite 文件 {suite_files} 个)",
            "",
            "## 覆盖率",
            "",
            "| 指标 | 值 |",
            "|------|-----|",
            f"| 用例覆盖引用 (covered_refs, 持久 selector, 不含瞬态 items) | {covered_n} |",
            f"| 扫描交互控件 (total) | {total} |",
            f"| 阈值 | {args.threshold}% |",
            f"| 结果 | {'PASS' if report['passed'] else 'FAIL'} |",
            "",
        ]
        if transient_items:
            L += [f"- 瞬态菜单项 (不计覆盖): {', '.join(transient_items)}"]
        if noise_removed:
            L += [f"- 已剔除文件名噪音: {', '.join(noise_removed)}"]
        if refs_not_in_inventory:
            L += [f"- suite 引用的清单外元素: {', '.join(refs_not_in_inventory)}"]
        if scan_named_not_in_inventory:
            L += [f"- 扫描已命名但清单缺失: {', '.join(scan_named_not_in_inventory)}"]
        if no_cases:
            L += ["> 未找到 AT 用例, 覆盖率记为 0。"]
        md_path.write_text("\n".join(L), encoding="utf-8")
        print(f"MD 报告已写入: {md_path}")

    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
