# coverage_stats.py — 源码扫描覆盖率

## Overview

Measures AT-SPI name coverage for a Qt/DTK C++ and/or QML project:

- **已编写 (ok)** — interactive widgets that already have `setObjectName()` + `setAccessibleName()` (C++) or `Accessible.name`/`Accessible.role` (QML)
- **应编写 (total)** — all interactive widgets found in source (ok + gap)
- **覆盖率 (coverage)** — `ok / total × 100%`

This skill owns the scanners (`scan_gaps.py` for C++ via libclang AST,
`scan_qml.py` for QML via tokenizer) and ships them self-contained, so the
skill is portable on its own.

The script (`scripts/coverage_stats.py`) improves on a raw `scan_source` call by:

1. **Per-file progress** — dispatches single-file tasks to a process pool so `imap_unordered` yields per file, instead of the skill's coarse 25-file batches that make large projects look hung.
2. **`compile_commands.json` auto-detection + `arguments` normalization** — finds `compile_commands.json` under any `build*/` dir and converts CMake's `arguments` (list) form to `command` (string) form, which the skill's `_load_compile_commands` reads.
3. **Standard output products** — writes `pre_scan_ok.yaml` / `pre_scan_gaps.yaml` compatible with the `--from-yaml` path, so you can re-view results without re-scanning.

## Usage

```bash
# Full scan (auto-detects compile_commands.json under build*/)
python3 scripts/coverage_stats.py --src /path/to/repo

# C++ only (skip QML search — for pure-C++ projects this silences the "no .qml" warning)
python3 scripts/coverage_stats.py --src /path/to/repo --cpp-only

# QML only (no libclang needed)
python3 scripts/coverage_stats.py --src /path/to/repo --qml-only

# Explicit build dir / compile_commands
python3 scripts/coverage_stats.py --src /path/to/repo --build /path/to/build
python3 scripts/coverage_stats.py --src /path/to/repo --compile-commands /path/to/compile_commands.json

# Breakdown by file and/or type
python3 scripts/coverage_stats.py --src /path/to/repo --by-file --by-type

# Custom threshold (default 80)
python3 scripts/coverage_stats.py --src /path/to/repo --threshold 90

# Re-view from existing scan products (fast, no re-scan)
python3 scripts/coverage_stats.py --from-yaml /path/to/coverage_scan/
```

## Output

Console:

```
[C++]
  已编写 (ok)   : 196
  缺失   (gap)  : 33
  应编写 (total): 229
  覆盖率        : 85.6%

[合计] 已编写: 196 / 应编写: 229 / 覆盖率: 85.6%
       阈值: 80.0%  -> PASS
```

With `--by-file` / `--by-type`, a breakdown like `src/dialog/scheduledlg.cpp  14/4/18` (ok/gap/total) and `DIconButton  6/11/17`.

Files written:
- `coverage_scan/pre_scan_ok.yaml`, `coverage_scan/pre_scan_gaps.yaml` — skill-compatible scan products (re-viewable via `--from-yaml`)
- `coverage_scan/pre_report.json` — skill's own summary
- `coverage_report.json` — this skill's summary (cpp/qml/combined counts + coverage + pass/fail)

Exit code: `0` if coverage ≥ threshold, `1` otherwise (CI-friendly).

## How Coverage Is Computed

Coverage formula:

- **C++**: `coverage = len(ok_widgets) / (len(ok_widgets) + len(gap_widgets))`
- **QML**: `coverage = len(ok_elements) / (len(ok_elements) + len(gap_elements))`

A widget is **ok** if it has both `setObjectName` and `setAccessibleName` (C++) or `Accessible.name` + `Accessible.role` (QML). A widget is a **gap** if the scanner classifies it as interactive (via `type_db.json` + hardcoded `_INTERACTIVE_CLASSES` + custom-type inheritance resolution) but lacks those calls.

## Interpreting "only N files have widgets"

For a large project you may scan 1000+ `.cpp` files but see only ~90 in the by-file breakdown. This is correct: only files that *instantiate interactive widget classes* (dialogs, widgets, views, main windows) contribute widgets. Model/data/business-logic/DBus files have none and are excluded from the breakdown.

## Built-in Environment Check

The script runs an environment check before any scanning and exits with code 1 + install hints if a required dependency is missing. You don't need to pre-verify — just run it; the check is automatic.

What it checks, by mode:

| Dependency | C++ scan | QML scan | `--from-yaml` |
|-----------|----------|----------|----------------|
| pyyaml | required | required | required (reads YAML) |
| python `clang` module | required | — | — |
| libclang `.so` | required | — | — |
| libclang binding init (scan_gaps) | required | — | — |

Example output when everything is present:

```
============================================================
环境检测
============================================================
  [✓] pyyaml                     已安装
  [✓] python clang 模块          已安装
  [✓] libclang 动态库            /usr/lib/x86_64-linux-gnu/libclang-17.so
  [✓] libclang 绑定可用          scan_gaps 可用
============================================================
[PASS] 环境检测通过
============================================================
```

When something is missing, each failing item prints its install command, plus a one-liner covering all C++ deps:

```
  [✗] python clang 模块          未安装
      sudo apt install python3-clang
============================================================
[FAIL] 环境检测未通过, 请按上述提示安装缺失依赖后重试。
       一键安装 (C++ 模式):  sudo apt install python3-clang libclang-18-dev && pip install pyyaml
============================================================
```
