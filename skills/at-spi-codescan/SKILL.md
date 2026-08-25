---
name: at-spi-codescan
description: >
  Assess AT-SPI element name coverage for Qt/DTK/QML desktop apps (static
  source scan vs codebase graph) and produce a coverage report.
  Triggers: AT-SPI覆盖率, 评估覆盖率, coverage report, 控件缺口.
version: "0.1.0"
license: MIT
author: Uniontech
---

## When to Use

- Asked to "check AT-SPI coverage" or "评估 AT-SPI 覆盖率" for a desktop app
- Need to compare static source scan vs codebase graph inference results
- Need a filed coverage report with gap details and root cause analysis
- Project has C++ (Qt/DTK) and/or QML source code

**Don't use when:**
- Need to **fix** missing AT-SPI names → use `at-spi-completion` skill
- Need to **derive** UI map from source → use `at-spi-ui-map` skill
- Quick one-off check → run `scan_cpp.py` directly

## Workflow

Run the scan scripts, then generate the report. See [assets/references/workflow.md](assets/references/workflow.md) for details.

```bash
OUT=<output_dir>

# Static scan — C++ (pure source, environment-independent)
python3 assets/scripts/scan_cpp.py --src <project_root> --output $OUT

# Static scan — QML (if the project has .qml files)
python3 assets/scripts/scan_qml.py --src <project_root> --output $OUT

# Coverage report (codebase-graph data optional: AI calls MCP tools to produce b_data.json)
python3 assets/scripts/generate_report.py \
  --project-name <name> --project-path <path> \
  --pipeline-a-dir $OUT \
  [--pipeline-b-data $OUT/b_data.json] \
  --output $OUT
```

Outputs: `pre_scan_ok/gaps.yaml` (C++), `qml_ok/gaps.yaml` (QML), `coverage-report.md` (summary).

## Coverage Sources

| Source | Implementation | Granularity | Output |
|--------|----------------|-------------|--------|
| Static scan | `scan_cpp.py` + `scan_qml.py` | instance-level (each `m_xxx` variable) | `pre_scan_ok/gaps.yaml` + `qml_ok/gaps.yaml` |
| Codebase graph | AI calls MCP tools directly | class-level (each widget class) | `b_data.json` |

**Static scan is the authoritative baseline** (pure source, environment-independent).
The codebase-graph source is optional: it requires an MCP service with the project
indexed. MCP services are dynamic (may be a different code graph), so **do not wrap
them in a script** — the AI calls the tools directly (probe with `list_tools` first,
do not assume fixed tool names). The two sources have different granularity
(instance vs class), so their coverage numbers are **not directly comparable**;
the graph source is only a class-level gap reference.

## Classification

All scripts share constants from `assets/scripts/classify.py` (C++ + QML), single source:

| Category | Counted as expected widget | Examples |
|----------|----------------------------|----------|
| Interactive | **Yes** — must have AT-SPI name | Button, LineEdit, Slider, Menu, List, Tree, Tab, ComboBox |
| Decorative | **No** — filtered out | Label, ProgressBar, Frame, GroupBox, Splitter, ToolBar |
| Layout | **No** — filtered out | QHBoxLayout, QVBoxLayout, QGridLayout |
| Non-widget interactive | **Yes** — objectName only | QAction, QShortcut, QActionGroup |

## Coverage Formula

```
Expected widgets = all interactive widgets (after filtering decorative/layout)
Named widgets    = expected widgets that have complete AT-SPI names
Coverage         = |Named| / |Expected| × 100%
```

**QWidget subclass**: needs BOTH `setObjectName()` + `setAccessibleName()` — missing either = gap.
**QAction/QShortcut**: only `setObjectName()` is possible — having it = ok.

## Commands

```bash
# C++ scan (pure source text, single mode, no environment dependency)
python3 assets/scripts/scan_cpp.py --src <project_root> --output <dir>

# QML scan
python3 assets/scripts/scan_qml.py --src <project_root> --output <dir>

# Generate coverage report (codebase-graph data optional)
python3 assets/scripts/generate_report.py \
  --project-name <name> --project-path <path> \
  --pipeline-a-dir <dir> \
  [--pipeline-b-data <dir>/b_data.json] \
  --output <project_root>/tests/at/coverage/
```

## Resources

- **Scan scripts**: See [assets/scripts/](assets/scripts/) for `scan_cpp.py`, `scan_qml.py`, `classify.py`
- **Report generator**: See [assets/scripts/generate_report.py](assets/scripts/generate_report.py)
- **Workflow**: See [assets/references/workflow.md](assets/references/workflow.md)