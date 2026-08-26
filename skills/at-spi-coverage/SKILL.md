---
name: at-spi-coverage
description: >
  Measure AT-SPI coverage of a Qt/DTK C++/QML project in two modes:
  (a) source-scan coverage — interactive widgets named vs. still needing names,
  gaps by file/type; (b) AT 用例覆盖率 (atcase) =
  min(covered_refs, scan_total)/scan_total, where covered_refs = suite refs
  (selector ∪ menu items), scan_total = interactive widgets from the source scan
  (coverage_stats.py), capped at 100%.
  Triggers: AT-SPI覆盖率, 覆盖率, coverage, AT 用例覆盖率, atcase, 控件缺口, gap 分析.
version: "0.5.0"
license: MIT
author: Uniontech
---

# AT-SPI Coverage Statistics

Two measurement modes, both via bundled scripts (self-contained, no repo-external deps):

> **独立可迁移技能。** 本技能自带全部扫描器（`scan_gaps.py` / `scan_qml.py` /
> `type_db.json`）与统计脚本，可独立复制到任意环境运行，不依赖其他技能。
> 扫描产物（`pre_scan_gaps.yaml` / `pre_scan_ok.yaml` / `qml_gaps.yaml` /
> `qml_ok.yaml`）是标准格式，可被任何下游消费。

## Default path: source-scan coverage

```bash
# Full scan (auto-detects compile_commands.json under build*/)
python3 scripts/coverage_stats.py --src /path/to/repo

# C++ only (pure-C++ projects: silences "no .qml" warning)
python3 scripts/coverage_stats.py --src /path/to/repo --cpp-only

# QML only (no libclang needed)
python3 scripts/coverage_stats.py --src /path/to/repo --qml-only

# Re-view from existing scan products (fast, no re-scan)
python3 scripts/coverage_stats.py --from-yaml /path/to/coverage_scan/
```

Output: `ok / total × 100%` where `total = ok + gap`. Exit `0` if coverage ≥ threshold (default 80), else `1` (CI-friendly). Full usage, breakdowns, and output products: read `references/coverage-stats.md`.

## AT 用例覆盖率 (atcase)

接力 `coverage_stats.py`, 分母 = 源码扫描的交互控件总数。公式:

```
coverage = min(covered_refs, scan_total) / scan_total × 100%   (封顶 100%)
covered_refs = selector.name ∪ items: 菜单项 (去重去噪)   # 分子, 用例引用全集
scan_total   = coverage_stats.py 扫描的交互控件数          # 分母, 源码扫描产物
```

瞬态菜单项 (主/右键菜单) 也算覆盖; `elements.yaml` 仅用于辅助报告 (清单内覆盖/清单缺口), 不决定分子分母。

```bash
# 1. 先扫描得到 total (产物写入 coverage_scan/)
python3 scripts/coverage_stats.py --src /path/to/repo --cpp-only -o coverage_report.json

# 2. 接力计算 AT 用例覆盖率 (自动发现 <repo>/coverage_scan/ 或 ./coverage_scan/)
python3 scripts/coverage_atcase.py --src /path/to/repo
```

Semantics, total-source precedence, noise filter, and output: read `references/atcase-coverage.md`.

## When to Use

- Verify AT-SPI coverage of a project (baseline)
- Triage which files / widget types most need AT-SPI names
- Measure how much of the UI element set the AT test cases exercise
- CI gate: fail when coverage < threshold

## When NOT to Use

- You want to *fix* missing AT-SPI names — this skill only *measures*.
- Decorative-only review (labels, frames, progress bars) — the scanner already excludes non-interactive types.

## Prerequisites

```bash
# C++ scanning needs libclang Python bindings + the .so
sudo apt install python3-clang libclang-18-dev   # match your system's libclang version (e.g. libclang-17-dev)
pip install pyyaml

# QML scanning and AT 用例覆盖率 need only Python stdlib (+ pyyaml)
```

The scripts run an automatic environment check before scanning and print install hints on failure — no manual pre-verification needed.

## Gotchas

- **`elements.yaml` ≠ source scan.** `elements.yaml` is a manually-maintained UI element list (includes `Form_*` containers, `Label_*` labels, menu items); `coverage_stats.py` counts only interactive widgets instantiated in source. Different dimensions — do not expect them to match. The atcase formula counts **all** suite refs (incl. transient menu items) against the scan total, so coverage can hit 100% even when the inventory is incomplete. See "Interpreting results" in `references/atcase-coverage.md`.
- **Dynamic names are invisible to static scan.** `setAccessibleName("Button_" + objName)` (string concatenation) cannot be resolved by libclang — those widgets appear as gaps even though they get names at runtime. Verify with a live AT-SPI dump, not the static scan alone.

## Verification

- Source scan: check `parsed/failed` counts in the scan summary; `0 failed` means libclang didn't choke on missing includes.
- AT case coverage: confirm `elements_source` in the JSON report is `elements.yaml` (or `*.suite.yaml` fallback) and that `noise_removed` lists only filename-like names.
- Cross-check: run `--by-type` to verify custom widget types aren't misclassified as non-interactive.

## Troubleshooting

| Symptom | Cause / Fix |
|---------|-------------|
| `libclang not available` | `sudo apt install python3-clang libclang-18-dev` (match your system's libclang version) |
| `compile_commands: 0 个文件` | No `compile_commands.json` under `build*/`. Pass `--compile-commands <path>` explicitly, or accept the fallback (check `0 failed` in summary). |
| Scan seems hung | Large projects take 2-5 min. The script prints progress every 20 files; if no progress lines for >1 min, check libclang imported cleanly. |
| Coverage looks too low | Run `--by-type` and inspect whether a custom widget type is misclassified as non-interactive. Custom types are registered by `resolve_custom_types` scanning `.h` files for `class X : public DPushButton` patterns. |
| atcase: "未找到扫描产物" | Run `coverage_stats.py` first (or pass `--total <N>` / `--scan-dir <dir>`). |
