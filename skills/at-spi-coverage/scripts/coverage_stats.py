#!/usr/bin/env python3
"""AT-SPI coverage statistics.

This skill owns the scanners (scan_gaps.py / scan_qml.py / type_db.json) and
counts, for a target project:
  - 已编写 (already named): interactive widgets with AT-SPI names
  - 应编写 (should be named): all interactive widgets (ok + gap)
  - 覆盖率 (coverage): ok / total

Coverage formula:
  C++ : ok_widgets / (ok_widgets + gap_widgets)
  QML : ok_elements / (ok_elements + gap_elements)

Usage:
    # Full scan (C++ needs build dir for libclang compile_commands.json)
    python3 coverage_stats.py --src /path/to/repo --build /path/to/build

    # QML only (no libclang needed)
    python3 coverage_stats.py --src /path/to/repo --qml-only

    # Parse existing scan outputs (skip re-scan, fast)
    python3 coverage_stats.py --from-yaml tests/at/spi/

    # Per-file / per-type breakdown
    python3 coverage_stats.py --src /path/to/repo --by-file --by-type
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent


def _add_scripts_to_path() -> None:
    """Make scan_gaps / scan_qml importable.

    This skill owns the scanners (scan_gaps.py / scan_qml.py / type_db.json)
    and ships them here (self-contained), so the skill is portable on its own.
    """
    # Bundled scanners (single owner)
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))


def _normalize_compile_commands(cc_path: str, out_dir: Path) -> str | None:
    """Convert compile_commands.json 'arguments' entries to 'command' string.

    scan_gaps._load_compile_commands only reads the 'command' field, but CMake
    newer versions emit 'arguments' (list form). Rewrite to a temp file with
    'command' so the skill scanner picks up per-file flags.
    """
    try:
        with open(cc_path, encoding="utf-8") as f:
            entries = json.load(f)
    except Exception as e:
        print(f"[WARN] 读取 compile_commands.json 失败: {e}", file=sys.stderr)
        return None
    has_args = any("arguments" in e and "command" not in e for e in entries)
    if not has_args:
        return cc_path  # already command-form or empty
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "compile_commands_normalized.json"
    for e in entries:
        if "command" not in e and "arguments" in e:
            e["command"] = " ".join(e["arguments"])
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(entries, f)
    print(f"[INFO] 已将 compile_commands 'arguments' 转为 'command' 格式: {out_path}",
          file=sys.stderr)
    return str(out_path)


_CPP_SKIP_DIRS = {
    "tests", "test", "autotests", "autotest",
    "examples", "example", "samples", "sample", "demo", "demos",
    "build", "Build", "builddir", "_build",
    "cmake-build", "CMakeFiles", ".cmake",
    "debian", ".git", "3rdparty", "thirdparty", "third_party",
}
_CPP_SKIP_PREFIXES = ("test_", "moc_", "mocs_", "ui_", "qrc_")
_CPP_EXTS = {".cpp", ".cxx", ".cc"}


def _scan_one_file_wrapper(task: tuple[str, str, list[str]]):
    """Module-level wrapper so Pool can pickle it; unpacks the 3-arg tuple
    for scan_gaps._scan_one_file (which imap_unordered won't auto-unpack)."""
    import scan_gaps as _sg  # type: ignore
    return _sg._scan_one_file(*task)


def _run_cpp_scan(src: str, build: str | None, compile_commands: str | None,
                  out_dir: Path) -> tuple[list, list]:
    """Self-scheduled C++ scan with per-file progress.

    Reuses scan_gaps internals (_scan_one_file, _load_compile_commands,
    resolve_custom_types, _write_outputs) but dispatches single-file tasks
    to a Pool so imap_unordered yields per-file → live progress, and avoids
    the skill's coarse batch grouping that makes large projects look hung.
    """
    _add_scripts_to_path()
    try:
        import scan_gaps as sg  # type: ignore
    except ImportError as e:
        print(f"[ERROR] 无法导入 scan_gaps.py: {e}", file=sys.stderr)
        print("        请先运行环境检测 (python3 coverage_stats.py --help 后扫描会自动检测)",
              file=sys.stderr)
        return [], []
    if not (sg._LIBCLANG_READY and sg._LIBCLANG_IMPORT_OK):
        print("[ERROR] libclang 不可用，环境检测应已拦截。", file=sys.stderr)
        print("        安装: sudo apt install python3-clang libclang-18-dev", file=sys.stderr)
        return [], []

    out_dir.mkdir(parents=True, exist_ok=True)
    root = Path(src)
    if not root.is_dir():
        print(f"[ERROR] 源码目录不存在: {src}", file=sys.stderr)
        return [], []

    # 1) Resolve + normalize compile_commands
    cc_path = compile_commands
    if not cc_path and build:
        cc_cand = Path(build) / "compile_commands.json"
        if cc_cand.is_file():
            cc_path = str(cc_cand)
    if not cc_path:
        for cand in root.rglob("compile_commands.json"):
            if "build" in cand.parts or ".qtc_clangd" in cand.parts:
                cc_path = str(cand)
                print(f"[INFO] 自动检测到 compile_commands.json: {cc_path}", file=sys.stderr)
                break
    if cc_path:
        cc_path = _normalize_compile_commands(cc_path, out_dir)

    file_flags = sg._load_compile_commands(cc_path) if cc_path else None
    print(f"[INFO] compile_commands: {len(file_flags) if file_flags else 0} 个文件编译参数",
          file=sys.stderr)

    # 2) Resolve custom types (registers project-defined widget classes)
    project_includes: list[str] = []
    if file_flags:
        src_str = str(root)
        seen: set[str] = set()
        for _f, flags in file_flags.items():
            for f in flags:
                if f.startswith("-I") and f not in seen:
                    seen.add(f)
                    inc = f[2:]
                    if inc and (inc.startswith(src_str) or src_str in inc):
                        project_includes.append(f)
    sg._TYPE_DB.resolve_custom_types(src, project_includes)

    # 3) Discover cpp files (same filter as scan_source)
    all_files = [p for p in root.rglob("*")
                 if p.suffix in _CPP_EXTS
                 and not any(part in _CPP_SKIP_DIRS for part in p.parts)
                 and not p.stem.startswith(_CPP_SKIP_PREFIXES)]
    all_files.sort()
    total = len(all_files)
    if total == 0:
        print(f"[WARN] 未在 {src} 发现 C++ 源文件", file=sys.stderr)
        return [], []

    # 4) Build per-file flag list
    extra_args = ["-x", "c++", "-std=c++17", "-fPIC"]
    extra_args.extend(sg._get_cxx_stdlib_flags())
    extra_args.extend(sg._get_qt_dtk_include_flags())
    # Extract include flags as complete pairs: '-isystem' takes its path as a
    # separate argv element, so a naive startswith filter would drop the paths
    # and leave dangling '-isystem' flags that break TU parsing.
    extra_includes: list[str] = []
    for i, f in enumerate(extra_args):
        if f == "-isystem" and i + 1 < len(extra_args):
            extra_includes.extend(["-isystem", extra_args[i + 1]])
        elif f.startswith("-I"):
            extra_includes.append(f)

    tasks: list[tuple[str, str, list[str]]] = []
    for p in all_files:
        abs_path = str(p.resolve())
        rel = str(p.relative_to(root))
        if file_flags and abs_path in file_flags:
            flags = list(file_flags[abs_path])
            for inc in extra_includes:
                if inc not in flags:
                    flags.append(inc)
        else:
            flags = extra_args
        tasks.append((abs_path, rel, flags))

    # 5) Dispatch single-file tasks to Pool → per-file progress
    import multiprocessing
    n_workers = min(multiprocessing.cpu_count() or 4, 8)
    print(f"[INFO] 开始 C++ AST 扫描: {total} 个文件, {n_workers} 进程...",
          file=sys.stderr)
    t0 = __import__("time").time()
    all_ok: list = []
    all_gaps: list = []
    global_named_calls: dict[str, set[str]] = {}
    parsed = failed = done = 0

    with multiprocessing.Pool(n_workers) as pool:
        for rel, ok_list, gap_list, named_vars, err in pool.imap_unordered(
                _scan_one_file_wrapper, tasks, chunksize=1):
            done += 1
            if err:
                failed += 1
            else:
                parsed += 1
            all_ok.extend(ok_list)
            all_gaps.extend(gap_list)
            for _v, _calls in named_vars.items():
                global_named_calls.setdefault(_v, set()).update(_calls)
            if done % 20 == 0 or done == total:
                elapsed = __import__("time").time() - t0
                print(f"  [{done}/{total}] {elapsed:.0f}s 已解析, "
                      f"ok={len(all_ok)} gap={len(all_gaps)} (失败 {failed})",
                      file=sys.stderr)

    # 5.5) Gap filters (kept in parity with scan_gaps.scan_source so the
    #   - text_named_calls: name calls caught by text regex (libclang may miss
    #     pointer-member calls on unresolved types); maps var -> call types.
    #   - newed_members: members actually instantiated via `new` somewhere.
    #     Drops dead header-only members and externally-owned references
    #     (m_var = ctorParam) that this class does not create.
    _NEW_ASSIGN_RE = re.compile(r'(\w+)\s*=\s*new\s+')
    _NEW_INIT_RE = re.compile(r'(\w+)\s*\(\s*new\s+')
    _NAME_CALL_PATTERNS = [
        (re.compile(r'(\w+)\s*->\s*setObjectName\s*\('), "setObjectName"),
        (re.compile(r'(\w+)\s*->\s*setAccessibleName\s*\('), "setAccessibleName"),
        (re.compile(r'(\w+)\s*\.\s*setObjectName\s*\('), "setObjectName"),
        (re.compile(r'(\w+)\s*\.\s*setAccessibleName\s*\('), "setAccessibleName"),
    ]
    # newed_members: (file_stem, variable) members instantiated via `new`,
    # scoped per file so a same-named member new-ed in a different file does
    # not mark one here (TextEdit::m_actEditView must not instantiate
    # BottomBar::m_actEditView). Drops dead header-only members and
    # externally-owned references (m_var = ctorParam).
    newed_members: set[tuple[str, str]] = set()
    # text_named_calls: (file_stem, variable) -> call types, scoped per file.
    text_named_calls: dict[tuple[str, str], set[str]] = {}
    for f in all_files:
        try:
            content = f.read_text(errors="replace")
            # all_files come from root.rglob, so relative_to always works.
            # (A startswith(str(root)) guard breaks for root="." where
            # str(f) is "reader/..." and never starts with ".", silently
            # keying newed_members/text_named_calls by bare filename and
            # dropping every gap in the cross-file merge.)
            rel = str(f.relative_to(root))
            fkey = sg._file_key(rel)
            for m in _NEW_ASSIGN_RE.finditer(content):
                newed_members.add((fkey, m.group(1)))
            for m in _NEW_INIT_RE.finditer(content):
                newed_members.add((fkey, m.group(1)))
            for rx, call_type in _NAME_CALL_PATTERNS:
                for m in rx.finditer(content):
                    text_named_calls.setdefault((fkey, m.group(1)), set()).add(call_type)
        except Exception:
            continue
    # 6) Dead-member / external-assignment filter FIRST (parity with
    # scan_gaps.scan_source): only consider a gap if the member is actually
    # instantiated via `new` in its own file. Drops dead header-only members
    # and externally-owned references (m_var = ctorParam, never new-ed).
    # Scoped by (file_stem, variable) so a same-named member new-ed in a
    # different file does not count here. Running before the cross-file
    # rescue means non-new members can never be rescued into "named".
    live_gaps = []
    for g in all_gaps:
        if (sg._file_key(g.source_file), g.variable) in newed_members:
            live_gaps.append(g)
    all_gaps = live_gaps

    # 7) Cross-file merge: a gap may be named in another file. A gap is only
    # rescued if actually fully named — interactive QWidgets need BOTH
    # setObjectName AND setAccessibleName. Uses the shared helper from
    # scan_gaps so baseline and quality-gate scans agree exactly.
    still_gaps = []
    for g in all_gaps:
        if sg._gap_fully_named(g, global_named_calls, text_named_calls):
            all_ok.append(g)
            continue
        still_gaps.append(g)
    all_gaps = still_gaps
    all_ok.sort(key=lambda w: (w.source_file, w.line, w.variable))
    all_gaps.sort(key=lambda w: (w.source_file, w.line, w.variable))

    # 7) Write standard skill outputs (pre_scan_ok.yaml / pre_scan_gaps.yaml)
    result = sg.ScanResult(
        source_dir=src, total_files=total, parsed_files=parsed,
        failed_files=failed, widgets=all_ok + all_gaps,
        ok_widgets=all_ok, gap_widgets=all_gaps,
    )
    try:
        sg._write_outputs(result, str(out_dir))
    except Exception as e:
        print(f"[WARN] 写出扫描产物失败: {e}", file=sys.stderr)

    elapsed = __import__("time").time() - t0
    print(f"[INFO] C++ 扫描完成: {elapsed:.0f}s, 解析 {parsed}, 失败 {failed}, "
          f"ok={len(all_ok)} gap={len(all_gaps)}", file=sys.stderr)
    return all_ok, all_gaps


def _run_qml_scan(src: str, out_dir: Path) -> tuple[list, list]:
    """Run scan_qml.scan_qml_source, return (ok_elements, gap_elements)."""
    _add_scripts_to_path()
    try:
        from scan_qml import scan_qml_source  # type: ignore
    except ImportError as e:
        print(f"[WARN] 无法导入 scan_qml.py: {e}", file=sys.stderr)
        return [], []
    out_dir.mkdir(parents=True, exist_ok=True)
    result = scan_qml_source(src_dir=src, output_dir=str(out_dir))
    return result.ok_elements, result.gap_elements


def _load_yaml(path: Path) -> Any:
    if not path.is_file():
        return None
    try:
        import yaml
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    except ImportError:
        pass
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _parse_cpp_yaml(dir_: Path) -> tuple[list, list]:
    """Parse existing pre_scan_ok.yaml + pre_scan_gaps.yaml."""
    ok_data = _load_yaml(dir_ / "pre_scan_ok.yaml") or {}
    gap_data = _load_yaml(dir_ / "pre_scan_gaps.yaml") or {}
    ok = ok_data.get("widgets", []) if isinstance(ok_data, dict) else []
    gap = gap_data.get("gaps", gap_data.get("widgets", [])) if isinstance(gap_data, dict) else []
    return ok, gap


def _parse_qml_yaml(dir_: Path) -> tuple[list, list]:
    """Parse existing qml_ok.yaml + qml_gaps.yaml."""
    ok_data = _load_yaml(dir_ / "qml_ok.yaml") or {}
    gap_data = _load_yaml(dir_ / "qml_gaps.yaml") or {}
    ok = ok_data.get("elements", ok_data.get("widgets", [])) if isinstance(ok_data, dict) else []
    gap = gap_data.get("gaps", gap_data.get("elements", [])) if isinstance(gap_data, dict) else []
    return ok, gap


def _pct(numer: int, denom: int) -> float:
    return round(numer / denom * 100, 1) if denom else 0.0


def _cpp_key(w: dict) -> str:
    return f"{w.get('source_file', '?')}:{w.get('line', 0)}:{w.get('variable', '')}"


def _qml_key(e: dict) -> str:
    return f"{e.get('source_file', '?')}:{e.get('line', 0)}:{e.get('element_type', '')}"


def _print_block(title: str, ok: int, gap: int) -> None:
    total = ok + gap
    print(f"\n[{title}]")
    print(f"  已编写 (ok)   : {ok}")
    print(f"  缺失   (gap)  : {gap}")
    print(f"  应编写 (total): {total}")
    print(f"  覆盖率        : {_pct(ok, total)}%")


_ENV_LOG: list[str] = []


def _check_env(need_cpp: bool, need_qml: bool, from_yaml: bool) -> bool:
    """Check runtime deps. Returns True if all present, prints install hints + returns False otherwise.

    - pyyaml: always required (write/read YAML products)
    - clang python module + libclang .so: required for C++ scan (not --qml-only/--from-yaml)
    - QML scan: stdlib only, no extra deps

    Also captures all output lines into module-level _ENV_LOG for the MD report.
    """
    _ENV_LOG.clear()
    def _say(s: str = "") -> None:
        print(s)
        _ENV_LOG.append(s)
    _say("=" * 60)
    _say("环境检测")
    _say("=" * 60)
    all_ok = True

    # 1) pyyaml
    try:
        import yaml  # noqa: F401
        _say("  [✓] pyyaml                     已安装")
    except ImportError:
        _say("  [✗] pyyaml                     未安装")
        _say("      pip install pyyaml")
        all_ok = False

    # 2) C++ deps — only when actually scanning C++ (not --from-yaml, not --qml-only)
    if need_cpp and not from_yaml:
        # Bootstrap resolves .so + Python binding together, self-healing via
        # pip when either is missing (sudo-free, PEP 668-aware). No manual
        # binding check first — let ensure_libclang() do the whole job.
        _add_scripts_to_path()
        from libclang_bootstrap import ensure_libclang
        _lc = ensure_libclang()
        if _lc.found:
            _say(f"  [✓] libclang 绑定+动态库         {_lc.display()}  ({_lc.source})")
        else:
            if _lc.source in ("LIBCLANG_LIBRARY_FILE", "LIBCLANG_LIBRARY_PATH"):
                _say(f"  [✗] libclang {_lc.source} 指向的路径无效")
                _say("      检查环境变量路径是否正确")
            else:
                _say("  [✗] libclang 绑定+动态库       未找到")
                _say("      设置 $LIBCLANG_LIBRARY_FILE=<path> 或确保可 pip install libclang")
            all_ok = False

        # libclang import actually works end-to-end
        _add_scripts_to_path()
        try:
            import scan_gaps as sg  # type: ignore
            if not (sg._LIBCLANG_READY and sg._LIBCLANG_IMPORT_OK):
                _say("  [✗] libclang 绑定初始化失败     scan_gaps._LIBCLANG_READY=False")
                _say("      检查 libclang 版本与 python3-clang 是否一致")
                all_ok = False
            else:
                _say("  [✓] libclang 绑定可用          scan_gaps 可用")
        except Exception as e:
            _say(f"  [✗] scan_gaps 导入异常          {e}")
            all_ok = False
    else:
        _say("  [—] C++ 扫描依赖                跳过 (非 C++ 扫描模式)")

    # 3) QML — stdlib only
    if need_qml and not from_yaml:
        _say("  [✓] QML 扫描依赖                纯标准库, 无需额外安装")

    _say("=" * 60)
    if not all_ok:
        _say("[FAIL] 环境检测未通过, 请按上述提示安装缺失依赖后重试。")
        _say("       脚本会自动 pip install libclang 兜底(免 sudo); 仍失败则设 $LIBCLANG_LIBRARY_FILE=<path>")
        _say("       一键安装 (C++ 模式):  sudo apt install python3-clang libclang-18-dev && pip install pyyaml")
    else:
        _say("[PASS] 环境检测通过")
    _say("=" * 60)
    return all_ok


def _tag(items: list, status: str) -> list[dict]:
    """Tag each item with an explicit _status field (ok/gap).

    Accepts either dicts (--from-yaml path) or dataclass objects (--src path).
    Dispatches to the correct converter based on element shape:
      - C++ WidgetInstance  -> scan_gaps._widget_to_dict
      - QML QmlElement      -> scan_qml._element_to_dict
    """
    _add_scripts_to_path()
    try:
        from scan_gaps import _widget_to_dict  # type: ignore
    except ImportError:
        _widget_to_dict = None
    try:
        from scan_qml import _element_to_dict  # type: ignore
    except ImportError:
        _element_to_dict = None
    out: list[dict] = []
    for it in items:
        if isinstance(it, dict):
            d = dict(it)
        elif hasattr(it, "element_type") and _element_to_dict:
            # QML QmlElement — has element_type, no `variable`/`type_name`.
            d = _element_to_dict(it)
        elif _widget_to_dict:
            # C++ WidgetInstance — has `variable`/`type_name`.
            d = _widget_to_dict(it)
        else:
            d = {"source_file": getattr(it, "source_file", "?"),
                 "type_name": getattr(it, "type_name", ""),
                 "element_type": getattr(it, "element_type", ""),
                 "line": getattr(it, "line", 0)}
        d["_status"] = status
        out.append(d)
    return out


def _breakdown(items: list[dict], key_fn, label: str) -> None:
    by: dict[str, dict[str, int]] = defaultdict(lambda: {"ok": 0, "gap": 0})
    for it in items:
        k = key_fn(it)
        by[k][it.get("_status", "gap")] += 1
    print(f"\n  按{label}分布 (ok/gap/total):")
    for k in sorted(by):
        o, g = by[k]["ok"], by[k]["gap"]
        print(f"    {k:<60} {o}/{g}/{o+g}")


def _breakdown_data(items: list[dict], key_fn) -> list[tuple[str, int, int, int]]:
    """Return [(key, ok, gap, total), ...] sorted by total desc then key."""
    by: dict[str, dict[str, int]] = defaultdict(lambda: {"ok": 0, "gap": 0})
    for it in items:
        by[key_fn(it)][it.get("_status", "gap")] += 1
    rows = [(k, v["ok"], v["gap"], v["ok"] + v["gap"]) for k, v in by.items()]
    rows.sort(key=lambda r: (-r[3], r[0]))
    return rows


def _gap_detail_rows(items: list[dict]) -> list[dict]:
    """Return gap items as dicts with file/line/type/var fields, sorted."""
    gaps = [it for it in items if it.get("_status") == "gap"]
    def _key(it):
        return (it.get("source_file", "?"), it.get("line", 0),
                it.get("type_name") or it.get("element_type") or "", it.get("variable", ""))
    return sorted(gaps, key=_key)


def _write_md_report(path: Path, ctx: dict) -> None:
    """Write a complete Markdown coverage report.

    ctx keys: project, generated_at, env_lines, env_pass, scan_mode,
              cpp{ok,gap,total,coverage}, qml{...}, combined{...},
              threshold, passed, by_file_rows, by_type_rows,
              qml_by_file_rows, qml_by_type_rows, gap_rows, qml_gap_rows,
              files_scanned, files_parsed, files_failed, products, command
    """
    L = []
    p = ctx["project"]
    L.append(f"# AT-SPI 覆盖率报告 — {p['name']}")
    L.append("")
    L.append(f"- 生成时间: {ctx['generated_at']}")
    L.append(f"- 源码路径: `{p['src']}`")
    if p.get("build"):
        L.append(f"- 构建目录: `{p['build']}`")
    if p.get("compile_commands"):
        L.append(f"- compile_commands: `{p['compile_commands']}`")
    L.append(f"- 扫描模式: {ctx['scan_mode']}")
    if ctx.get("files_scanned") is not None:
        L.append(f"- 扫描文件数: {ctx['files_scanned']} (解析 {ctx['files_parsed']}, 失败 {ctx['files_failed']})")
    L.append(f"- 阈值: {ctx['threshold']}%")
    L.append("")

    # Executive summary
    c = ctx["combined"]
    verdict = "PASS ✅" if ctx["passed"] else "FAIL ❌"
    L.append("## 执行摘要")
    L.append("")
    L.append(f"| 指标 | 值 |")
    L.append(f"|------|----|")
    L.append(f"| 已编写 (ok) | {c['ok']} |")
    L.append(f"| 应编写 (total) | {c['total']} |")
    L.append(f"| 覆盖率 | **{c['coverage']}%** |")
    L.append(f"| 阈值判定 | {verdict} (≥ {ctx['threshold']}%) |")
    L.append("")

    # Coverage summary by language
    L.append("## 覆盖率汇总")
    L.append("")
    L.append("| 语言 | 已编写 (ok) | 缺失 (gap) | 应编写 (total) | 覆盖率 |")
    L.append("|------|-----------|-----------|---------------|--------|")
    for label, key in [("C++", "cpp"), ("QML", "qml"), ("合计", "combined")]:
        d = ctx[key]
        L.append(f"| {label} | {d['ok']} | {d['gap']} | {d['total']} | {d['coverage']}% |")
    L.append("")

    # Environment check
    L.append("## 环境检测")
    L.append("")
    L.append(f"结果: {'PASS ✅' if ctx['env_pass'] else 'FAIL ❌'}")
    L.append("")
    L.append("```")
    L.extend(ctx.get("env_lines", []))
    L.append("```")
    L.append("")

    # By type breakdown (C++)
    if ctx.get("by_type_rows"):
        L.append("## C++ 按控件类型分布")
        L.append("")
        L.append("| 类型 | ok | gap | total | 覆盖率 |")
        L.append("|------|----|----|-------|--------|")
        for k, o, g, t in ctx["by_type_rows"]:
            cov = f"{_pct(o, t)}%"
            L.append(f"| {k} | {o} | {g} | {t} | {cov} |")
        L.append("")

    # By file breakdown (C++)
    if ctx.get("by_file_rows"):
        L.append("## C++ 按文件分布")
        L.append("")
        L.append("| 文件 | ok | gap | total | 覆盖率 |")
        L.append("|------|----|----|-------|--------|")
        for k, o, g, t in ctx["by_file_rows"]:
            cov = f"{_pct(o, t)}%"
            L.append(f"| `{k}` | {o} | {g} | {t} | {cov} |")
        L.append("")

    # QML breakdowns
    if ctx.get("qml_by_type_rows"):
        L.append("## QML 按控件类型分布")
        L.append("")
        L.append("| 类型 | ok | gap | total | 覆盖率 |")
        L.append("|------|----|----|-------|--------|")
        for k, o, g, t in ctx["qml_by_type_rows"]:
            L.append(f"| {k} | {o} | {g} | {t} | {_pct(o, t)}% |")
        L.append("")

    if ctx.get("qml_by_file_rows"):
        L.append("## QML 按文件分布")
        L.append("")
        L.append("| 文件 | ok | gap | total | 覆盖率 |")
        L.append("|------|----|----|-------|--------|")
        for k, o, g, t in ctx["qml_by_file_rows"]:
            L.append(f"| `{k}` | {o} | {g} | {t} | {_pct(o, t)}% |")
        L.append("")

    # Gap detail (C++)
    if ctx.get("gap_rows"):
        L.append("## C++ 缺口明细 (AT-SPI 名称缺失)")
        L.append("")
        L.append("| 文件 | 行 | 类型 | 变量/对象 | 建议名称 |")
        L.append("|------|----|------|----------|---------|")
        for g in ctx["gap_rows"]:
            L.append(f"| `{g['source_file']}` | {g['line']} | {g['type']} | {g['variable']} | {g['suggested']} |")
        L.append("")

    # Gap detail (QML)
    if ctx.get("qml_gap_rows"):
        L.append("## QML 缺口明细 (AT-SPI 名称缺失)")
        L.append("")
        L.append("| 文件 | 行 | 类型 | 建议名称 |")
        L.append("|------|----|------|---------|")
        for g in ctx["qml_gap_rows"]:
            L.append(f"| `{g['source_file']}` | {g['line']} | {g['type']} | {g['suggested']} |")
        L.append("")

    # Products
    L.append("## 产物文件")
    L.append("")
    for f in ctx.get("products", []):
        L.append(f"- `{f}`")
    L.append("")

    # Reproduction
    L.append("## 复现命令")
    L.append("```bash")
    L.append(ctx["command"])
    L.append("```")
    L.append("")
    L.append("---")
    L.append(f"*报告由 at-spi-coverage skill 自动生成*")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))



def main() -> int:
    ap = argparse.ArgumentParser(description="AT-SPI 覆盖率统计")
    ap.add_argument("--src", help="目标项目源码根目录 (repo root)")
    ap.add_argument("--build", help="C++ 构建目录 (含 compile_commands.json)")
    ap.add_argument("--compile-commands", help="直接指定 compile_commands.json 路径")
    ap.add_argument("--from-yaml", help="从已有扫描产物目录读取 (跳过重新扫描)")
    ap.add_argument("--output", "-o", default="coverage_report.json", help="JSON 报告输出路径")
    ap.add_argument("--qml-only", action="store_true", help="只统计 QML (跳过 C++ libclang 扫描)")
    ap.add_argument("--cpp-only", action="store_true", help="只统计 C++")
    ap.add_argument("--by-file", action="store_true", help="按文件分组输出")
    ap.add_argument("--by-type", action="store_true", help="按控件类型分组输出")
    ap.add_argument("--threshold", type=float, default=80.0, help="覆盖率阈值 (默认 80)")
    ap.add_argument("--md-report", default="coverage_report.md",
                    help="Markdown 报告输出路径 (默认 coverage_report.md; 置空则不生成)")
    args = ap.parse_args()

    # Environment check before any scanning
    need_cpp = not args.qml_only
    need_qml = not args.cpp_only
    if not _check_env(need_cpp, need_qml, bool(args.from_yaml)):
        return 1

    cpp_ok: list = []
    cpp_gap: list = []
    qml_ok: list = []
    qml_gap: list = []

    if args.from_yaml:
        ydir = Path(args.from_yaml)
        if not args.qml_only:
            cpp_ok, cpp_gap = _parse_cpp_yaml(ydir)
        if not args.cpp_only:
            qml_ok, qml_gap = _parse_qml_yaml(ydir)
    else:
        if not args.src:
            ap.error("--src 或 --from-yaml 必须指定一个")
        out_dir = Path(args.output).parent / "coverage_scan"
        if not args.qml_only:
            cpp_ok, cpp_gap = _run_cpp_scan(args.src, args.build, args.compile_commands, out_dir)
        if not args.cpp_only:
            qml_ok, qml_gap = _run_qml_scan(args.src, out_dir)

    # C++
    cpp_ok_n = len(cpp_ok)
    cpp_gap_n = len(cpp_gap)
    cpp_total = cpp_ok_n + cpp_gap_n
    cpp_cov = _pct(cpp_ok_n, cpp_total)

    # QML
    qml_ok_n = len(qml_ok)
    qml_gap_n = len(qml_gap)
    qml_total = qml_ok_n + qml_gap_n
    qml_cov = _pct(qml_ok_n, qml_total)

    # Combined
    all_ok = cpp_ok_n + qml_ok_n
    all_total = cpp_total + qml_total
    all_cov = _pct(all_ok, all_total)

    print("=" * 60)
    print("AT-SPI 覆盖率统计")
    print("=" * 60)

    if cpp_total > 0 or args.qml_only is False and not args.qml_only:
        _print_block("C++", cpp_ok_n, cpp_gap_n)
    if qml_total > 0 or args.qml_only:
        _print_block("QML", qml_ok_n, qml_gap_n)
    if cpp_total == 0 and qml_total == 0:
        print("\n[WARN] 未扫描到任何交互控件。检查 --src 路径或扫描依赖。")
        print("       C++ 需要: python3-clang-18 libclang-18-dev + compile_commands.json")
        return 1

    print("\n" + "=" * 60)
    print(f"[合计] 已编写: {all_ok} / 应编写: {all_total} / 覆盖率: {all_cov}%")
    print(f"       阈值: {args.threshold}%  -> {'PASS' if all_cov >= args.threshold else 'FAIL'}")
    print("=" * 60)

    if args.by_file or args.by_type:
        print("\n--- C++ 明细 ---" if cpp_total else "\n--- (无 C++ 控件) ---")
        if cpp_total:
            items = _tag(list(cpp_ok), "ok") + _tag(list(cpp_gap), "gap")
            if args.by_file:
                _breakdown(items, lambda w: w.get("source_file", "?"), "文件")
            if args.by_type:
                _breakdown(items, lambda w: w.get("type_name") or w.get("type", "?"), "类型")

        print("\n--- QML 明细 ---" if qml_total else "\n--- (无 QML 控件) ---")
        if qml_total:
            items = _tag(list(qml_ok), "ok") + _tag(list(qml_gap), "gap")
            if args.by_file:
                _breakdown(items, lambda e: e.get("source_file", "?"), "文件")
            if args.by_type:
                _breakdown(items, lambda e: e.get("element_type", "?"), "类型")

    report = {
        "cpp": {"ok": cpp_ok_n, "gap": cpp_gap_n, "total": cpp_total, "coverage": cpp_cov},
        "qml": {"ok": qml_ok_n, "gap": qml_gap_n, "total": qml_total, "coverage": qml_cov},
        "combined": {"ok": all_ok, "total": all_total, "coverage": all_cov},
        "threshold": args.threshold,
        "passed": all_cov >= args.threshold,
    }
    rpath = Path(args.output)
    with open(rpath, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\nJSON 报告已写入: {rpath}")

    # Markdown report (always generated unless --md-report is empty)
    if args.md_report:
        md_path = Path(args.md_report)
        # Build breakdown data for MD (always compute; cheap)
        cpp_items = _tag(list(cpp_ok), "ok") + _tag(list(cpp_gap), "gap") if cpp_total else []
        qml_items = _tag(list(qml_ok), "ok") + _tag(list(qml_gap), "gap") if qml_total else []
        cpp_by_file = _breakdown_data(cpp_items, lambda w: w.get("source_file", "?")) if cpp_items else []
        cpp_by_type = _breakdown_data(cpp_items, lambda w: w.get("type_name") or w.get("type", "?")) if cpp_items else []
        qml_by_file = _breakdown_data(qml_items, lambda e: e.get("source_file", "?")) if qml_items else []
        qml_by_type = _breakdown_data(qml_items, lambda e: e.get("element_type", "?")) if qml_items else []
        gap_rows = [{
            "source_file": g.get("source_file", "?"), "line": g.get("line", 0),
            "type": g.get("type_name") or g.get("type", "?"),
            "variable": g.get("variable", g.get("object_name", "")),
            "suggested": g.get("suggested_name", g.get("suggested", "")),
        } for g in _gap_detail_rows(cpp_items)]
        qml_gap_rows = [{
            "source_file": g.get("source_file", "?"), "line": g.get("line", 0),
            "type": g.get("element_type", g.get("type", "?")),
            "suggested": g.get("suggested_name", g.get("suggested", "")),
        } for g in _gap_detail_rows(qml_items)]

        scan_mode = "C++ only" if args.cpp_only else "QML only" if args.qml_only else "C++ + QML"
        if args.from_yaml:
            scan_mode += " (from existing YAML products)"
        from datetime import datetime
        project_name = Path(args.src).name if args.src else Path(args.from_yaml).resolve().parent.name

        # Read scan stats from pre_report.json if present (written by _run_cpp_scan)
        files_scanned = files_parsed = files_failed = None
        pre_report_path = Path(args.output).parent / "coverage_scan" / "pre_report.json"
        if pre_report_path.is_file():
            try:
                with open(pre_report_path, encoding="utf-8") as f:
                    pr = json.load(f)
                st = pr.get("stats", {})
                files_scanned = st.get("total_files")
                files_parsed = st.get("parsed_files")
                files_failed = st.get("failed_files")
            except Exception:
                pass

        ctx = {
            "project": {"name": project_name, "src": args.src or args.from_yaml,
                        "build": args.build, "compile_commands": args.compile_commands},
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "env_lines": list(_ENV_LOG),
            "env_pass": True,  # env check failure returns early before reaching here
            "scan_mode": scan_mode,
            "cpp": {"ok": cpp_ok_n, "gap": cpp_gap_n, "total": cpp_total, "coverage": cpp_cov},
            "qml": {"ok": qml_ok_n, "gap": qml_gap_n, "total": qml_total, "coverage": qml_cov},
            "combined": {"ok": all_ok, "gap": cpp_gap_n + qml_gap_n, "total": all_total, "coverage": all_cov},
            "threshold": args.threshold,
            "passed": report["passed"],
            "by_file_rows": cpp_by_file, "by_type_rows": cpp_by_type,
            "qml_by_file_rows": qml_by_file, "qml_by_type_rows": qml_by_type,
            "gap_rows": gap_rows, "qml_gap_rows": qml_gap_rows,
            "files_scanned": files_scanned, "files_parsed": files_parsed,
            "files_failed": files_failed,
            "products": [str(rpath), str(md_path)],
            "command": "python3 " + " ".join(sys.argv),
        }
        try:
            _write_md_report(md_path, ctx)
            print(f"MD 报告已写入: {md_path}")
        except Exception as e:
            print(f"[WARN] MD 报告生成失败: {e}", file=sys.stderr)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
