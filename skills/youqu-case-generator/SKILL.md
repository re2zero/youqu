---
name: youqu-case-generator
version: "0.5.0"
description: >
  Generate YouQu test cases in YAML (primary) or Python (fallback) from xlsx/csv,
  feature descriptions, or git diff analysis. Use whenever: YAML用例生成,
  xlsx转py用例, csv转py用例, 生成YouQu用例, generate YouQu tests, 批量生成测试用例,
  youqu make, 创建autotest, AT-SPI用例生成, diff生成用例, 代码变更生成用例.
---

# YouQu Case Generator

Generate complete, executable YouQu test cases in YAML (primary) or Python (fallback)
from xlsx/csv test case documents, feature descriptions, or git diff analysis.
Core principle: LLM understands test intent + youqu-mcp provides the real AT-SPI
element tree → produces genuine operations, not trivial stubs.

## Three Operating Modes

- **xlsx/csv-driven**: Full regression suite from structured spreadsheet (id, title,
  module, precondition, steps, expected, priority).
- **feature-driven**: New feature cases from PR description, issue, requirement doc.
  Extract testable scenarios manually, then generate.
- **git-diff-driven**: Cases from `youqu-change-test` skill. Receives structured
  change analysis (module, change_type, affected_features, diff summary), generates
  cases for uncovered features. Called by `youqu-change-test` Step 4 — do NOT use
  standalone unless you have the structured analysis output.

## YAML First, Python Second

The framework now supports YAML test cases as the **primary** format for AI automation.
YAML is simpler for LLMs to generate, has built-in app lifecycle (setup/teardown),
wait_for conditions, and declarative assertions.

**When to use YAML**: Linear workflows, data-driven tests, regression suites,
AI-generated cases from xlsx/PR/issue.

**When to use Python**: Complex branching logic, custom assertions, unusual app interactions
that don't fit the declarative model.

YAML and Python cases coexist — `youqu run` collects both formats automatically.

## Non-Automatable Case Handling

Every source case produces a test method inside a batch Python file. Cases from
the same module are grouped into batches of ≤10 cases, each batch becomes one
Python test file. Non-automatable cases get `@pytest.mark.skip` — never omitted
silently.

**Automatic classification** (see `@references/skip-classification.md` for full rules):

| Category | Detection Pattern | Skip Reason |
|----------|------------------|-------------|
| Touch/gesture | 触摸, touch, 手势, pinch, swipe | skip-触摸操作无法自动化 |
| Performance | 性能, performance, 压测, 压力, 并发 | skip-性能压测类不支持自动化 |
| Hardware dependency | 需要特定硬件, 需要外设, 需要U盘, 需要打印机 | skip-依赖特定硬件环境 |
| Linglong | 玲珑, linglong | skip-玲珑环境不支持自动化 |
| System reboot | 重启, reboot, 重启后, 重启系统 | skip-重启类场景需要letmego支持 |
| External app | 调用外部应用, 打开第三方 | skip-外部应用交互无法验证 |
| Manual verification | 人工确认, 肉眼观察, 主观判断, 听感 | skip-需要人工主观判断 |

**Flag for manual review**: 多机/协同/投屏, 网络/在线, 渲染/GPU/显卡.

---

## Execution Steps

### Step 1: Parse Source Data

**xlsx/csv mode**: Use the export script to produce JSON batches:

```bash
# Parse xlsx/csv into JSON batches for agent consumption (throwaway intermediate)
python3 @scripts/export_xlsx.py <xlsx_or_csv_path> <output_dir> [--batch-size 10]
```

Each batch is a JSON file containing ≤10 cases with fields: id, title, module,
precondition, steps, expected, priority, case_type. The output directory is a
**throwaway temp directory** — the JSON is consumed by the agent during case
generation and does not need to be persisted. The original xlsx/csv in
`autotest/casefiles/` is the permanent source of truth.

**feature mode**: Gather context manually from PR descriptions, git diffs, etc.

**git-diff mode** (called by `youqu-change-test` skill): Input is a structured
analysis result from LLM reading git diff, not raw diff text. The analysis already
identifies modules, features, and change type. Agent derives test scenarios from
the analysis + original diff content.

Input format:
```yaml
source_type: git_diff
app_name: "deepin-music"
module: "播放"
change_type: "new_feature"         # bug_fix / new_feature / refactor / config
change_description: |
  新增了歌词逐字高亮功能，在播放页面底部显示歌词，
  当前播放行高亮，支持逐字 Karaoke 效果。
affected_features:
  - "歌词显示"
  - "逐字高亮"
diff_summary: |
  src/player/lyrics.cpp  | 120 +++++++++++++
  src/player/lyrics.h    |  30 +++
  src/ui/lyrics_panel.cpp | 85 ++++++---
```

In git-diff mode, skip Step 1 (no xlsx/csv parsing). Go directly to Step 2
(project skeleton check) → Step 3 (AT-SPI tree) → Step 8 (YAML generation).
Case metadata: `vars.source_type: "git_diff"`, `vars.change_type`, and trace
the affected_features in the `feature` field.

**Output format decision**: By default, generate YAML cases. Generate Python only when:
- Case requires loops, conditionals, or complex state management
- Custom assertions not covered by YAML assert types
- User explicitly requests Python format

### Step 2: Create YouQu Project Skeleton

Generate a standalone `autotest/` skeleton with the new CLI:

```bash
youqu make <name>                  # YAML only (default)
youqu make <name> --format py      # Python only (widget/case/ui.ini)
youqu make <name> --format all     # Both YAML + Python
```

**Default (yaml)** — YAML is the primary format. `yaml/` directory with shared `elements.yaml`:
```
autotest/
├── yaml/                         # YAML test cases (primary format)
│   ├── elements.yaml           # MANDATORY shared element registry (upward lookup supported)
│   ├── test_<name>_001.yaml    # sample flat-layout case
│   └── <module>/               # optional module subdirectory (Allure auto-groups by dir)
│       └── test_<name>_002.yaml
├── casefiles/                   # source xlsx/csv case design docs (permanent input)
├── conftest.py
├── pytest.ini
├── config.ini
└── report/
```

Subdirectory YAML files automatically find the shared `elements.yaml` at `yaml/` root
via upward lookup (up to 4 levels). No per-directory copy needed.

**py mode** — Python with Page Object:
```
autotest/
├── widget/
│   ├── __init__.py          # exports <Name>Widget
│   ├── base_widget.py       # extends Src
│   ├── <name>_widget.py     # main widget class
│   ├── ui.ini               # ButtonCenter coordinates
│   └── pic_res/             # image templates
├── case/
│   ├── __init__.py          # exports BaseCase
│   ├── base_case.py         # extends AssertCommon
│   └── test_<name>_001.py   # sample test
├── conftest.py
├── pytest.ini
├── config.ini
├── ui.ini
└── report/
```

**all mode** — combined (both yaml/ and widget/case/ directories).

**Naming**: `youqu make terminal` creates `autotest/` with:
- `BaseCase.APP_NAME = "terminal"` (py mode only)
- `BaseWidget.APP_NAME = "terminal"` (py mode only)
- `BaseWidget.DESC = "/usr/bin/terminal"` (py mode only)
- Widget class: `TerminalWidget` (py mode only)
- Sample test: `TestTerminal.test_terminal_001` (py mode only)

### Step 3: Acquire Live AT-SPI Tree → Populate elements.yaml

Launch the target app and capture its accessibility tree. The critical output is
`autotest/yaml/elements.yaml` — the mandatory element registry that all YAML
test cases reference via `ref`.

**Full procedure**: See `@references/atspi-tree-acquisition.md`.

**Key points:**
- Set environment: `DISPLAY`, `AT_SPI_BUS_ADDRESS`, `QT_ACCESSIBILITY`
- Verify via `window_focus` and `window_get_info`
- Primary: `atspi_find_element` / `atspi_get_children_text` / `screenshot_save`
- Interactive: `atspi_find_and_click` / `atspi_find_and_right_click` (trigger menus, dialogs)
- Status: `window_get_count` / `system_get_process_status`
- Fallback: pyatspi script (see reference doc) for DTK apps with internal class names
- Capture each UI state separately (main window, menu, dialogs, search, etc.)
- **Populate `autotest/yaml/elements.yaml`** with the captured elements (see format below)

### Step 4: Classify and Batch

1. Run automatic skip classification rules on each case
2. Flag ambiguous cases for manual review
3. Group automatable cases into batches of ≤10

### Step 5: Generate Widget Methods (Per Module) — Python Mode Only

For py mode, generate Widget files. For each module with automatable cases:

```python
from autotest.widget.base_widget import BaseWidget
from src import log

@log
class <Module>Widget(BaseWidget):

    def click_xxx_by_attr(self):
        self.dog.find_element_by_attr("Btn_xxx").click()

    def get_xxx_text(self):
        return self.dog.find_element_by_attr("Label_xxx").text
```

**Positioning strategy priority:**
1. **AT-SPI attribute** — preferred, when `atspi_find_element` succeeds
2. **OCR** — fallback for elements without AT-SPI attributes
3. **ButtonCenter (ui.ini)** — for fixed-layout elements
4. **Image recognition** — last resort, maintenance-heavy
5. **VLM (vlm_click)** — AI vision fallback when all above fail (requires VLM API)

**Method naming**: `click_<target>_by_<strategy>()`, `get_<target>_<prop>()`,
`input_<target>()`, `switch_<target>()`, `select_<target>()`, `wait_<target>()`.

See `@references/youqu-po-pattern.md` for full naming conventions and available
Src/AssertCommon methods.

### Step 6: Generate Test Case Files

For automatable cases:

```python
from autotest.case.base_case import BaseCase
from autotest.widget.<module>_widget import <Module>Widget

class Test<CaseName>(BaseCase):

    def test_<case_name>_<nnn>(self):
        """<case title>"""
        widget = <Module>Widget()
        # Step 1: <description>
        widget.<method>()
        # Assert: <expected>
        self.assert_true(...)
```

For non-automatable cases:

```python
import pytest
from autotest.case.base_case import BaseCase

class Test<CaseName>(BaseCase):

    @pytest.mark.skip(reason="<skip reason>")
    def test_<case_name>_<nnn>(self):
        """<case title> — NON-AUTOMATABLE: <reason>"""
        pass
```

**Critical naming rules** (framework enforces at collection, `conftest.py:287-304`):
- File: `test_<name>_<nnn>.py` — `<nnn>` = 3-digit padded ID
- Method: `test_<name>_<nnn>` — **must match file name exactly**
- Consequences of mismatch:
  - File/method ID differ → **skipped** (error logged)
  - File/method name part differ → **removed from collection** (silent)
  - No ID match (`test_something` without `_\d+`) → **skipped** (error logged)

### Step 7: Verify

```bash
cd autotest && youqu run --collect-only
```

Check:
- Python method count == source case count (1:1 content fidelity)
- File name ID == method name ID for every case
- All imports resolve
- Widget extends BaseWidget, TestCase extends BaseCase
- Non-automatable cases have `@pytest.mark.skip`

### Step 8: Generate YAML Test Cases (Preferred)

For automatable cases, generate YAML files in `autotest/yaml/`. Organize files
into module subdirectories when the case count warrants it (e.g. 10+ cases per module):

```
autotest/yaml/
├── elements.yaml            # shared registry (found via upward lookup)
├── keyboard/
│   ├── test_kb_menu_019.yaml
│   └── test_kb_shortcut_028.yaml
├── remote/
│   ├── test_remote_add_057.yaml
│   └── test_remote_edit_058.yaml
```

Subdirectory organization gives automatic Allure report grouping (pytest-allure
uses directory paths for `parentSuite` labels). No explicit Allure tag injection needed.

**Prerequisite**: `autotest/yaml/elements.yaml` must contain element aliases for all
UI elements referenced by test cases. This file is mandatory — test cases use `ref` to
reference elements, never inline selectors or coordinates.

#### elements.yaml Format (MANDATORY)

```yaml
# Element aliases for <app-name>
# All UI elements referenced by test cases must be registered here.
# Supports: AT-SPI attributes (name/role), coordinates (x/y), and menu paths.
app: <app-name>

elements:
  # AT-SPI elements
  ok_button:
    name: "确定"
  dialog:
    role: "dialog"
  file_menu:
    name: "文件"
    role: "menu"
  settings_tab:
    name: "设置"
    role: "page tab"

  # Coordinate-based elements (right-click targets, fixed positions)
  app_center:
    x: 500
    y: 300

  # Menu navigation paths (keyboard arrow-key based)
  open_file:
    menu: ["文件", "打开"]

  # Context menu paths (right-click + keyboard)
  context_copy:
    x: 100
    y: 200
    menu: ["复制"]
```

**Element type rules**:
- `name`/`role` → AT-SPI element lookup (element_action, element_set_value, asserts)
- `x`/`y` → coordinate-based actions (mouse_click, mouse_right_click, mouse_drag)
- `menu` → keyboard menu navigation (main_menu_comb)
- `x`/`y` + `menu` → context menu navigation (context_menu_comb)
- `name`/`role` + `menu` → element_action click + keyboard menu (main_menu_comb from element)

#### YAML Test Case Format

Every YAML test case MUST include a complete metadata header that preserves ALL
original xlsx/csv case information. This is the **single source of traceability**
back to the original case design — never omit any field.

**xlsx → YAML field mapping:**

| xlsx field | YAML location | Required |
|---|---|---|
| 用例编号 (ID) | `vars.xlsx_id` | ✅ always |
| 用例标题 (title) | `name` | ✅ always |
| 所属模块 (module) | `module` | ✅ always |
| 前置条件 (precondition) | `description` (prepended) | ✅ if non-empty |
| 步骤 (steps) | `description` (main body) | ✅ always |
| 预期 (expected) | `description` (appended) | ✅ always |
| 用例级别 (priority) | `tags` (mapped) | ✅ always |
| 用例类型 (case_type) | `vars.case_type` | ✅ always |

```yaml
name: "用例标题（原始 xlsx 标题）"
app: "app-name"
screenshot: false
description: |
  前置条件:
  <original precondition from xlsx — omit section if empty>

  测试步骤:
  1. <step>
  2. <step>

  预期结果:
  1. <expected>
  2. <expected>
module: "主菜单"           # ← xlsx "所属模块", never empty string
feature: "关于"           # ← inferred subcategory from case content
tags:
  - L1                   # ← xlsx "用例级别" mapped to tag
vars:
  xlsx_id: "1652139"     # ← xlsx "用例编号", traceability to original
  case_type: "功能测试"   # ← xlsx "用例类型"

setup:
  - action: session_start
    command: "app-name"
    wait: 1.0

steps:
  - name: "单击确定按钮"
    action: element_action
    ref: ok_button
    do: "click"
    wait_after: 300
    wait_for:
      selector:
        role: "dialog"
      timeout: 3000
    assert:
      - type: element_visible
        selector:
          name: "成功"

  - name: "右键点击打开菜单"
    action: context_menu_comb
    ref: context_copy
    wait: 0.3

  - name: "打开文件菜单"
    action: main_menu_comb
    ref: open_file
    wait: 0.3

  - name: "点击中心区域"
    action: mouse_click
    ref: app_center
    wait: 0.3

  - name: "DBus 属性验证"
    action: dbus_get_property
    value:
      bus_type: "session"
      dbus_name: "com.example.Interface"
      object_path: "/com/example/Object"
      interface: "com.example.Interface"
      property: "SomeProperty"
    wait: 0.3
    assert:
      - type: dbus_property
        value:
          expected: "expected_value"

  # Final step: wait for last operation to take effect, then assert result
  - name: "等待操作生效并验证"
    action: wait
    wait: 0.3
    assert:
      - type: process_running
        app: "app-name"

teardown:
  - action: session_stop
```

**Critical**: All YAML test cases use `ref` to reference elements.yaml entries.
Inline `selector`, `x`, `y`, `items` are NOT allowed — they cause ambiguity and
scatter element definitions across files.

**Metadata fields** (`description`/`module`/`feature`/`tags`):
- `description`: From xlsx "测试步骤" + "预期结果" columns (multi-line, human-readable reference)
- `module`/`feature`: From xlsx module/feature columns, or inferred from case grouping
- `tags`: Priority-based (L1/L2/L3) from xlsx priority column
- After generating cases, run `youqu index --rebuild` to update `yaml/index.yaml`

#### YAML Action Reference

| Action | Key Parameters | Description |
|--------|---------------|-------------|
| `session_start` | `command`, `wait` | Launch app process |
| `session_stop` | — | Terminate app process (proc.terminate + proc.kill fallback) |
| `keyboard_press` | `keys` | Single key or combo (e.g. "Return", "ctrl+a") |
| `keyboard_hot_key` | `keys` | Key combination (e.g. "ctrl,c") |
| `keyboard_type` | `text` | Type text string |
| `mouse_click` | `ref` | Left click — AT-SPI name/role → dynamic center if available, else x/y fallback |
| `mouse_right_click` | `ref` | Right click — same dynamic center resolution |
| `mouse_double_click` | `ref` | Double click — same dynamic center resolution |
| `mouse_scroll` | `amount` | Scroll (positive=up) |
| `mouse_drag` | `ref` | Drag to coordinates |
| `element_action` | `ref`, `do` | AT-SPI element operation (resolved from elements.yaml. do: click/right_click/double_click) |
| `element_set_value` | `ref`, `text` | Set text value on element |
| `main_menu_comb` | `ref` | Keyboard-navigate menu (resolved from elements.yaml) |
| `context_menu_comb` | `ref` | Right-click + keyboard-navigate context menu |
| `dbus_call` | `value` | Call D-Bus method |
| `dbus_get_property` | `value` | Read D-Bus property |
| `wait` | `wait` | Smart wait — polls AT-SPI tree for next step's target; falls back to sleep if no target |
| `screenshot` | — | Capture screen |

**Assert types for inline use** (still use inline `selector` for asserts within step):

#### YAML Assert Reference

| Assert Type | Key Parameters | Description |
|-------------|---------------|-------------|
| `element_visible` | `selector` | Element exists in AT-SPI tree |
| `element_not_visible` | `selector` | Element does NOT exist |
| `element_numbers` | `selector`, `number` | Exact count of matching elements |
| `element_text` | `selector`, `expected` | Element text matches expected |
| `process_running` | `app` | Process is running |
| `process_not_running` | `app` | Process is NOT running |
| `file_exists` | `path` | File exists on disk |
| `file_not_exists` | `path` | File does NOT exist |
| `image_exist` | `path` | Template image matches screen |
| `image_not_exist` | `path` | Template image NOT on screen |
| `ocr_exist` | `text` | OCR text exists on screen |
| `ocr_not_exist` | `text` | OCR text NOT on screen |
| `window_size` | `expected`, `actual` | Window dimensions match |
| `dbus_property` | `value` | D-Bus property equals expected |

**Variable substitution**: Use `${VAR_NAME}` in any string field. Variables are resolved at parse
time with this priority (highest → lowest):

1. **Env var** (e.g. `YOUQU_BUILD_DIR=/custom/path`)
2. **test_*.yaml `vars:`** — case-specific values
3. **elements.yaml `vars:`** — project-level defaults (define once, reuse everywhere)
4. **Built-in defaults** (see table below)

**Define project-wide paths in `elements.yaml`** so all test cases share them. Individual test
YAMLs only need `vars:` for case-specific values — they should NOT redefine common paths.

| Built-in Variable | Default Value | Env Override |
|---|---|---|
| `${YAML_DIR}` | Directory containing the test YAML file | — |
| `${PROJECT_ROOT}` | autotest directory's parent (workspace root) | — |
| `${TEST_FILES_DIR}` | `${PROJECT_ROOT}/test_files` | `YOUQU_TEST_FILES_DIR` |
| `${BUILD_DIR}` | `${PROJECT_ROOT}/build` | `YOUQU_BUILD_DIR` |
| `${APP_PATH}` | `app` field basename (for AT-SPI registration name) | — |

**Example** — define in elements.yaml once:
```yaml
# elements.yaml
app: deepin-music
vars:
  BUILD_DIR: "${PROJECT_ROOT}/build"
  TEST_FILES_DIR: "${PROJECT_ROOT}/tests/files"
elements:
  play_button:
    name: 播放
```

Then reference in any test_*.yaml without redefining:
```yaml
# test_play_001.yaml
name: 播放音乐
steps:
  - action: session_start
    command: "${BUILD_DIR}/deepin-music"
  - action: keyboard_type
    text: "${TEST_FILES_DIR}/sample.mp3"
```

Always use `${BUILD_DIR}` and `${TEST_FILES_DIR}` — never hardcode absolute paths.

**Wait conditions**: Steps can have `wait_for` to poll until an element appears. Uses inline
selectors (not ref) since wait_for target is transient UI state, not a registered element:

```yaml
- action: element_action
  ref: ok_button
  wait_for:
    selector: {role: "dialog"}
    timeout: 3000
    interval: 200
```

**Naming**: YAML files follow `test_<name>_<nnn>.yaml`. The name field must match.

**Non-automatable cases**: Documented with comment header, minimal stub body.

### Step 9: Verify

```bash
cd autotest && youqu run --collect-only
```

Check:
- Python: method count == source case count (1:1 content fidelity)
- YAML: file count == automatable case count
- Both YAML and Python cases appear in collection output
- YAML files parse without YAML errors
- **Every YAML file contains complete metadata header: name, description, module, feature, tags, vars.xlsx_id, vars.case_type — missing any is a defect**
- elements.yaml contains all refs used by test cases
- Non-automatable YAML cases are documented with reason comments
- File name ID == method name ID for every Python case
- All imports resolve
- Widget extends BaseWidget, TestCase extends BaseCase
- Non-automatable Python cases have `@pytest.mark.skip`

---

## Delegation Pattern

For multi-module generation, dispatch one sub-agent per batch in parallel.

**Sub-agent prompt template:**

```
1. TASK: Generate YAML test cases (preferred) or Python test files for module "<module>" (<count> cases).
   Read JSON batch at <batch_json_path>.
   Target app: <app_name>. Working dir: <project_root>.

2. EXPECTED OUTCOME:
   - YAML files in autotest/yaml/ or autotest/yaml/<module>/ (subdirectory for multi-module projects)
   - elements.yaml populated with all UI elements from AT-SPI tree (at yaml/ root)
   - Python files in autotest/case/ (fallback, for complex cases)
   - <count> YAML or Python files total
   - 1 Widget file in autotest/widget/<module>_widget.py (py mode only)
   - YAML naming: test_<name>_<nnn>.yaml (<nnn>=3-digit padded batch position)
   - Python naming: test_<name>_<nnn>.py
   - Non-automatable: YAML stub with reason comment or @pytest.mark.skip + pass body
   - YAML steps use ref (never inline selector/x/y) referencing elements.yaml

3. REQUIRED TOOLS: read, write, edit

4. MUST DO:
   - Generate YAML by default; use Python only for complex branching/loops
   - YAML must follow schema: name, description, module, feature, tags, app, setup, steps, teardown
   - **Every YAML MUST include a complete metadata header — never omit any field**
   - `name`: xlsx "用例标题" (exact copy)
   - `description`: xlsx "前置条件" + "步骤" + "预期" (multi-line block scalar, all three sections)
   - `module`: xlsx "所属模块" (exact copy, never empty string)
   - `feature`: Feature subcategory inferred from case content (e.g. "关于", "打开图片")
   - `tags`: xlsx "用例级别" mapped to tags (e.g. ["L1"], ["L2", "smoke"])
   - `vars.xlsx_id`: xlsx "用例编号" (traceability to original case, REQUIRED)
   - `vars.case_type`: xlsx "用例类型" (e.g. "功能测试", "兼容性测试")
   - Each YAML step must use ref (never inline selector/x/y/items)
   - Populate elements.yaml with all UI elements from AT-SPI tree capture
   - Read the JSON batch file for case data
   - Read existing base_widget.py and base_case.py for inheritance reference
   - Read autotest/docs/at-spi-tree.md for real element names
   - Use MCP tools for AT-SPI tree acquisition and verification (see tool list below)
   - If atspi_find_element fails, use pyatspi fallback (see @references/atspi-tree-acquisition.md)
   - Map operations to concrete Widget methods using real AT-SPI element names
   - Follow naming: file ID == method ID
   - Non-automatable → YAML stub with comment or @pytest.mark.skip(reason="..."), never omit
   - **Generated Python code MUST use YouQu framework API (Src/DogtailUtils/ButtonCenter),
     NOT MCP tool calls.** MCP tools are for the agent's exploration workflow only.

5. MUST NOT DO:
   - Modify framework source (src/, setting/, conftest.py)
   - Modify files outside autotest/
   - Invent element names without MCP verification
   - Generate "pass" stubs for automatable cases
   - Hardcode absolute paths

 6. CONTEXT:
   - PO inheritance: Src → BaseWidget → <Module>Widget, AssertCommon → BaseCase → Test
   - Skip classification rules: @references/skip-classification.md
   - Assertion/Src methods: @references/youqu-po-pattern.md
   - MCP tools: @references/mcp-tool-reference.md
   - YAML schema + timing guide: @references/yaml-schema.md
   - DTK menu operations: @references/dtk-menu-guide.md
   - E2E verified templates: @references/templates/
   - Pitfalls: @references/pitfalls.md
```

---

## Pitfalls

See `@references/pitfalls.md` for the complete list. Critical ones:

1. **Sub-agents must not modify framework source.** Explicitly forbid in every prompt.
2. **AT-SPI selectors must match reality.** Never invent names — use MCP verification.
   DTK apps often use internal class names (e.g., `DTitlebarDWindowOptionButton`).
3. **File name ID must match method name ID.** Mismatch → silently skipped.
4. **Every source case needs a file.** Non-automatable → `@pytest.mark.skip`, never omit.
5. **Widget methods: one thing each.** Don't combine operations — defeats PO composability.
6. **YAML is preferred over Python for AI automation.** LLMs generate more correct
   YAML than Python. Use Python only for complex branching.
7. **YAML action/assert names must match the reference table.** Unknown types cause
   runtime errors. See Step 8 reference tables for supported types.
8. **YAML steps must use ref, NOT inline selector/x/y/items.** Inline definitions
   scatter element info across files and cause ambiguity. All elements must be
   registered in elements.yaml. The executor resolves ref at runtime.
9. **elements.yaml is mandatory for YAML tests.** Missing elements.yaml causes
   all ref-based steps to fail. Place it at `autotest/yaml/elements.yaml` (the
   shared root). Subdirectory test files find it via upward lookup (searches up
   to 4 directory levels).
10. **Wait conditions**: Always add `wait_for` before steps that depend on UI state
   changes (dialog opens, page loads, etc.). Default timeout: 3000ms.
   wait_for uses inline selectors (not ref) since it targets transient UI state.
11. **Timing defaults are mandatory** — see `@references/yaml-schema.md` Timing Guide.
   session_start.wait=1.0, step.wait=0.3, wait_for.timeout=3000ms. Do NOT
   invent larger values without verification.
12. **Last step before teardown MUST wait** — never jump from an operation directly
   to session_stop. Add a final `action: wait` + `wait: 0.3` step with an assert
   to verify the operation took effect before killing the app.

---

## Reference Files

| File | Purpose |
|------|---------|
| `@references/youqu-po-pattern.md` | Inheritance chain, Src methods, assertions, Widget conventions |
| `@references/mcp-tool-reference.md` | MCP tool reference with parameters and usage |
| `@references/skip-classification.md` | Full skip rules with detection patterns |
| `@references/atspi-tree-acquisition.md` | AT-SPI tree capture procedure (env, launch, dump, persist) |
| `@references/pitfalls.md` | Complete pitfalls list with root causes |
| `@references/yaml-schema.md` (NEW) | YAML schema reference with all actions, asserts, selectors, and timing guide |
| `@references/dtk-menu-guide.md` (NEW) | DTK menu operations: main menu, context menu, MenuNavigator strategies |
| `@references/templates/` (NEW) | Verified E2E YAML templates (main menu, context menu) in ref format |
| `@scripts/export_xlsx.py` | Batch export xlsx/csv rows to JSON |
| `@assets/widget_template.py` | Widget file template with common method patterns |
| `@assets/case_template.py` | Test case file template |
