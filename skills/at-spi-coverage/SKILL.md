---
name: at-spi-coverage
description: Use when you need to measure AT-SPI name coverage of a Qt/DTK C++ or QML project — count already-named interactive widgets vs. widgets that still need names, compute coverage %, and list gaps by file/type. Reuses the at-spi-completion scanners (scan_gaps.py / scan_qml.py) with per-file progress and compile_commands.json auto-detection. Use to verify coverage before/after an AT-SPI completion pass, or to triage which files/types most need work.
version: "0.2.0"
license: MIT
author: Uniontech
---

# AT-SPI Coverage Statistics

## Overview

Measures AT-SPI name coverage for a Qt/DTK C++ and/or QML project:

- **已编写 (ok)** — interactive widgets that already have `setObjectName()` + `setAccessibleName()` (C++) or `Accessible.name`/`Accessible.role` (QML)
- **应编写 (total)** — all interactive widgets found in source (ok + gap)
- **覆盖率 (coverage)** — `ok / total × 100%`

Reuses the at-spi-completion skill's scanners (`scan_gaps.py` for C++ via libclang AST, `scan_qml.py` for QML via tokenizer) so the numbers are consistent with the completion workflow's own `quality_gate.py`.

The script (`scripts/coverage_stats.py`) improves on a raw `scan_source` call by:

1. **Per-file progress** — dispatches single-file tasks to a process pool so `imap_unordered` yields per file, instead of the skill's coarse 25-file batches that make large projects look hung.
2. **`compile_commands.json` auto-detection + `arguments` normalization** — finds `compile_commands.json` under any `build*/` dir and converts CMake's `arguments` (list) form to `command` (string) form, which the skill's `_load_compile_commands` reads.
3. **Standard output products** — writes `pre_scan_ok.yaml` / `pre_scan_gaps.yaml` compatible with the `--from-yaml` path, so you can re-view results without re-scanning.

## When to Use

- Verify AT-SPI coverage before a completion pass (baseline)
- Verify coverage after a completion pass (did it go up? did ok count rise?)
- Triage which files / widget types most need AT-SPI names
- CI gate: fail when coverage < threshold (default 80%)

## When NOT to Use

- You want to *fix* missing AT-SPI names — use the `at-spi-completion` skill instead. This skill only *measures*.
- Decorative-only review (labels, frames, progress bars) — the scanner already excludes non-interactive types.

## Prerequisites

```bash
# C++ scanning needs libclang Python bindings + the .so
sudo apt install python3-clang libclang-18-dev   # match your system's libclang version (e.g. libclang-17-dev)
pip install pyyaml

# QML scanning needs only Python stdlib (tokenizer-based)
```

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

Identical to `at-spi-completion/scripts/quality_gate.py`:

- **C++**: `coverage = len(ok_widgets) / (len(ok_widgets) + len(gap_widgets))`
- **QML**: `coverage = len(ok_elements) / (len(ok_elements) + len(gap_elements))`

A widget is **ok** if it has both `setObjectName` and `setAccessibleName` (C++) or `Accessible.name` + `Accessible.role` (QML). A widget is a **gap** if the scanner classifies it as interactive (via `type_db.json` + hardcoded `_INTERACTIVE_CLASSES` + custom-type inheritance resolution) but lacks those calls.

## Interpreting "only N files have widgets"

For a large project you may scan 1000+ `.cpp` files but see only ~90 in the by-file breakdown. This is correct: only files that *instantiate interactive widget classes* (dialogs, widgets, views, main windows) contribute widgets. Model/data/business-logic/DBus files have none and are excluded from the breakdown.

## Caveats

- **`compile_commands.json` improves accuracy** for projects with deep custom widget hierarchies. Without it, the scanner falls back to system Qt/DTK include paths + `resolve_custom_types` (text grep of all `.h` files). The fallback is usually fine — verify by checking `parsed/failed` counts in the scan summary; `0 failed` means libclang didn't choke on missing includes.
- **`examples/` and `tests/` are excluded by default** via `_SKIP_DIRS`. If you ship example code to users and want it covered, that's a policy call — the script excludes them to match the completion skill's behavior.
- **Cross-file naming** is handled: if a widget is declared in `foo.h` and named in `foo.cpp`, the merge step promotes it from gap to ok.

## Troubleshooting

| Symptom | Cause / Fix |
|---------|-------------|
| `libclang not available` | `sudo apt install python3-clang libclang-18-dev` (match your system's libclang version) |
| `compile_commands: 0 个文件` | No `compile_commands.json` under `build*/`. Pass `--compile-commands <path>` explicitly, or accept the fallback (check `0 failed` in summary). |
| Scan seems hung | Large projects take 2-5 min. The script prints progress every 20 files; if you see no progress lines for >1 min, check that libclang imported cleanly. |
| Coverage looks too low | Run `--by-type` and inspect whether a custom widget type is being misclassified as non-interactive. Custom types are registered by `resolve_custom_types` scanning `.h` files for `class X : public DPushButton` patterns. |
