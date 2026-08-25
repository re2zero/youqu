---
name: at-spi-coverage
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

## Critical Patterns

### 1. Two Isolated Pipelines

Spawn two independent sub-agents via `task` — they MUST NOT share intermediate state. Communication only through `local://` URIs.

| Pipeline | Method | Granularity |
|----------|--------|-------------|
| A (Static Scan) | `scan_cpp.py` + `scan_qml.py` | Instance-level (each `m_xxx` variable) |
| B (Codebase Graph) | codebase MCP `query_graph` + `search_code` | Class-level (each widget class) |

### 2. Unified Classification

Both pipelines MUST use the same classification from `assets/scripts/classify.py`:

| Category | Included in Element A | Examples |
|----------|----------------------|----------|
| Interactive | **Yes** — must have AT-SPI name | Button, LineEdit, Slider, Menu, List, Tree, Tab, ComboBox |
| Decorative | **No** — filtered out | Label, ProgressBar, Frame, GroupBox, Splitter, ToolBar |
| Layout | **No** — filtered out | QHBoxLayout, QVBoxLayout, QGridLayout |
| Non-widget interactive | **Yes** — objectName only | QAction, QShortcut, QActionGroup |

### 3. Coverage Formula

```
Element A = all interactive widgets (after filtering decorative/layout)
Element B = Element A widgets that have complete AT-SPI names
Coverage = |B| / |A| × 100%
```

**QWidget subclass**: needs BOTH `setObjectName()` + `setAccessibleName()` — missing either = gap.
**QAction/QShortcut**: only `setObjectName()` is possible — having it = ok.

### 4. Pipeline A: Scan Mode Auto-Fallback

`scan_cpp.py` supports three modes via `--mode`:

| Mode | Behavior | When to use |
|------|----------|-------------|
| `auto` (default) | Try libclang; if ABI incompatible → fallback to text grep | General use |
| `libclang` | Only libclang AST scan; fail if unavailable | Debug/verify AST results |
| `grep` | Text grep only, no libclang needed | Headless/CI without libclang |

The grep fallback scans `.h` files for widget member declarations via regex and `.cpp` files for `setObjectName`/`setAccessibleName` calls. Less precise than libclang (no template/typedef resolution) but works without any C++ parser.

### 5. Pipeline B: MCP Endpoint Fallback

codebase MCP 服务提供固定 HTTP 端点（`/projects`、`/index`、`/mcp`），不支持 OAuth 动态客户端注册。

| 步骤 | 动作 | 失败处理 |
|------|------|---------|
| 1 | 尝试 OAuth 注册（`/register`） | 404 → 跳过，直接调固定端点 |
| 2 | 调 `list_projects`（`/projects`） | 失败 → 报错退出 |
| 3 | 调 `index_status`（`/index`） | 失败 → 报错退出 |
| 4 | 调 `get_architecture`（`/mcp`） | 失败 → 报错退出 |


**关键规则：** 认证方式失败（404）不降级到 grep。直接调固定端点。端点调用失败才报错退出。

## Code Examples

### Spawn two isolated pipelines

```python
# Main agent dispatches both pipelines in parallel
context = """
# Goal
Assess AT-SPI coverage for {project_path}

# Constraints
- Element A = interactive widgets only (filter decorative/layout)
- Element B = widgets with complete AT-SPI names
- Coverage = |B| / |A| * 100
- Each pipeline works independently
"""

tasks = [
    {
        "name": "PipelineA_StaticScan",
        "task": """
# Target
{project_path}
Run assets/scripts/scan_cpp.py for C++, assets/scripts/scan_qml.py for QML.

# Change
1. Run scan_cpp.py --mode auto --src {project_path} --build <build_dir> --output <out>
   (--mode auto: try libclang, fallback to grep if ABI incompatible)
2. Run scan_qml.py --src {project_path} --output <out>
3. Calculate coverage from output files
4. Write report to local://a_report.md

# Acceptance
local://a_report.md contains total, ok, coverage%, module breakdown, gap list
"""
    },
    {
        "name": "PipelineB_CodebaseMCP",
        "task": """
# Target
{project_name} in codebase MCP.
Use query_graph + search_code to derive coverage.

# Change
1. Try OAuth register → 404? Skip, call fixed endpoints directly
2. list_projects → confirm indexed
3. index_status → confirm head_sha current
4. get_architecture → find gui/ directories
5. query_graph → find QWidget/DWidget subclasses
6. search_code → find setAccessibleName/setObjectName calls
7. Classify, calculate coverage, write local://b_report.md

# Acceptance
local://b_report.md contains total, ok, coverage%, module breakdown, gap list
"""
    }
]
```

### Generate final report

```bash
python3 assets/scripts/generate_report.py \
  --project-name <name> \
  --project-path <path> \
  --pipeline-a-dir <output_dir> \
  --pipeline-b-data <b_data.json> \
  --output <project_root>/tests/at/coverage/
```

## Commands

```bash
# Initialize workflow state
python3 assets/scripts/workflow_state.py init <project_path> <project_name>

# C++ scan (auto mode: try libclang, fallback to grep)
python3 assets/scripts/scan_cpp.py --mode auto --src <project_root> --build <build_dir> --output <dir>

# C++ scan (grep only, no libclang needed)
python3 assets/scripts/scan_cpp.py --mode grep --src <project_root> --output <dir>

# QML scan (standalone)
python3 assets/scripts/scan_qml.py --src <project_root> --output <dir>

# Generate coverage report
python3 assets/scripts/generate_report.py \
  --project-name <name> --project-path <path> \
  --pipeline-a-dir <dir> --pipeline-b-data <json> \
  --output <project_root>/tests/at/coverage/

# Check workflow state
python3 assets/scripts/workflow_state.py status
```
## Resources

- **Scan scripts**: See [assets/scripts/](assets/scripts/) for `scan_cpp.py`, `scan_qml.py`, `classify.py`
- **Report generator**: See [assets/scripts/generate_report.py](assets/scripts/generate_report.py)
- **Workflow references**: See [assets/references/](assets/references/) for per-stage instructions
- **Report templates**: See [assets/templates/](assets/templates/) for pipeline report templates