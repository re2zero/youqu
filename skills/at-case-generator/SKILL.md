---
name: at-case-generator
version: "0.6.0"
description: >
  Use when generating AT-SPI test suites from xlsx/csv test case documents
  for a Linux desktop application. Triggers: AT用例生成, at-case generation,
  AT suite generation, AT-SPI suite YAML, at-tree用例, 桌面应用AT测试,
  AT自动化用例, youqu at parse, youqu at generate, youqu at tree-info.
---

# AT Case Generator

Convert xlsx/csv test case documents into executable AT-SPI suite YAML.
The AI does semantic mapping through understanding — not a CLI LLM call,
not a regex script, not an external API request. **You (the agent reading
this) are the AI.** Framework provides data tools; you provide understanding.

## When to Use

- xlsx/csv test case documents for a Linux desktop application
- Need executable AT-SPI test suites from those documents
- Input is a PR/issue/requirement and you want to generate cases directly

## When NOT to Use

- Standard YAML test cases → use `youqu-case-generator`
- Run existing AT suites → use `youqu at run`

## Pipeline

```
Step 1: Pre-flight checks
Step 2: Data preparation
    youqu at parse <xlsx> → cases_raw.yaml (raw, format-only)
    --- AT tree acquisition (requires user interaction) ---
    youqu at scan --src <dir> --app <id> → scanned_ok.yaml + element_gaps.yaml
    ⏸ STOP: ask user to run `youqu at record` and return with results
        user runs: youqu at record --app <id> [--launch <cmd>]
        user operates app (clicks, menus, dialogs), then finishes
        user returns: record_session.yaml + states/*.yaml produced
    youqu at merge --scan <scan_dir> --record <record_dir> → at-tree.yaml (v2.0)
    ---
    youqu at tree-info --format yaml <at-tree> → at-tree-annotated.yaml (structured, for AI)
Step 2.5: AT tree annotation (AI session)
    AI fills comment for each interactive element → at-tree-annotated.yaml (draft)
    Human reviews → at-tree-annotated.yaml (reviewed)
    youqu at validate --gate 1
Step 2.7: Case normalization (AI session)
    AI groups cases by GUI interface → suite-cases.yaml + cases_non_gui.yaml
    AI adds 4-field suite annotations (测试界面, 测试功能, 前置条件, AT元素引用)
    youqu at validate --gate 2
Step 2.8: Module split (optional, for large case sets)
    youqu at split --cases <cases_raw> --at-tree <annotated> --output <dir>
    youqu at docs <app> --output <docs_dir>  (optional: import help manual chapters)
Step 3: AI semantic mapping (KEY STEP — AI does this through understanding)
    AI reads at-tree-annotated.yaml + suite-cases.yaml (or per-module files)
    AI also reads transient_contexts (if v2.0) to understand menu/dialog elements
    AI fills action, element_ref, selector, items, key, text, assertion
    AI writes cases_mapped.yaml with format example in header
    youqu at validate --gate 3
    youqu at validate --gate 5  (semantic safety: description-as-input, missing precondition, empty selector)
Step 3.5: Precandidate (optional, for constraint-based selector pre-filtering)
    youqu at precandidate --cases <cases_raw> --at-tree <annotated> --output <suite-cases.yaml>
    (or per-module: youqu at precandidate --module-dir <dir>)
Step 4: Generate + validate
    youqu at generate --cases <mapped> --output <dir> --app <app> --at-tree <tree>
    youqu at validate --gate 4
    youqu at run --testdir <dir>  [NOT python -m src.yaml_test.suite]
Step 5: Layered runtime verification (optional)
    youqu at smoke --modules-dir <dir>   (L2: one representative case per module)
    youqu at verify --suite <suite.yaml> --spec-id <id>  (L3: single case deep verify)
```

`youqu at map` is **deprecated**. Mapping is done by you (the agent) in Step 3.

## Step 1: Pre-flight Checks

- `youqu --version` — CLI installed
- xlsx/csv input exists, columns match supported aliases (see pipeline-reference.md)
- at-tree.yaml exists and is fresh (check `metadata.generated_at`)

## Step 2: Data Preparation

### 2a: Parse xlsx → raw cases.yaml

```bash
youqu at parse --input <xlsx_or_csv> --output <cases_yaml>
```

Output: CaseStep entries with `step_type`, `description`, `element_hint`,
`items` filled; `action`, `element_ref`, `selector` are null. Format-only.

### 2b: Generate structured annotated tree for AI reading

```bash
youqu at tree-info --at-tree <at_tree.yaml> --output <at-tree-annotated.yaml> --format yaml
```

Outputs structured YAML with `comment`, `annotation_status`, `classification` fields
for each node. The AI fills `comment` in Step 2.5; `classification` is pre-set by
the denoise filter (interactive/container). Replaces the old flat `compact_tree.txt`.

### 2c: Acquire at-tree.yaml (if not present)

```bash
youqu at dump dtk <app_name> --src <source_dir> --output <output_dir>
```

Requires desktop environment with target app running.

## Step 2.5: AT Tree Annotation (AI Session)

You (the agent) annotate each interactive element in `at-tree-annotated.yaml` with
a `comment` field describing its GUI location and function.

### Comment Format

```
GUI位置: <界面位置描述> | 功能: <功能描述>
```

Examples:
- `GUI位置: 工具栏第一个按钮 | 功能: 打开文件`
- `GUI位置: 左侧导航栏 | 功能: 切换书架视图`
- `GUI位置: 设置对话框-通用标签页 | 功能: 设置默认字号`

### Annotation Procedure

1. Read `at-tree-annotated.yaml`
2. For each node with `classification: interactive`:
   - Infer the GUI location from parent chain (role/name hierarchy)
   - Infer the function from `name`, `object_name`, `role`
   - Write the `comment` field
   - Set `annotation_status: draft`
3. Human reviews and corrects annotations
4. Set `annotation_status: reviewed` on corrected entries
5. Run `youqu at validate --gate 1 --at-tree-annotated <path> --element-gaps <path>`

### Element Gaps

`element_gaps.yaml` lists interactive elements missing `object_name` and
`accessible_id`. These need app-side `setAccessibleName()` to be fully
AT-SPI addressable. Report gaps to the user — do not attempt to fix app source.

## Step 2.7: Case Normalization (AI Session)

You (the agent) normalize `cases_raw.yaml` into `suite-cases.yaml` with
interface-based grouping and suite annotations.

### Normalization Procedure

1. Read `cases_raw.yaml`
2. Separate non-GUI cases (terminal commands, DBus without UI, HTTP) into
   `cases_non_gui.yaml` with `status: non_gui`
3. Group remaining cases by GUI interface (not xlsx module path):
   - Cases testing the same interface flow → one suite
   - Cap: 15 cases per suite
   - LLM-assisted grouping based on step descriptions
4. For each suite, add 4 annotation fields:
   - `测试界面`: which GUI interface this suite tests
   - `测试功能`: what functionality this suite covers
   - `前置条件`: setup requirements (moved from setup steps)
   - `AT元素引用`: list of AT tree element names used by this suite
5. Split compound steps (multiple operations in one step) into atomic steps
6. Run `youqu at validate --gate 2 --suite-cases <path> --at-tree-annotated <path>`

### Suite Annotation Example

```yaml
cases:
  - id: "suite_reader_toolbar"
    name: "阅读器工具栏功能"
    status: "active"
    annotation:
      测试界面: "主窗口-工具栏"
      测试功能: "工具栏按钮操作（打开/保存/书签）"
      前置条件: "应用已启动，文档已打开"
      AT元素引用: ["open_button", "save_button", "bookmark_button"]
    steps:
      - step_type: "action"
        description: "点击打开按钮"
      - step_type: "assert"
        description: "验证文件已打开"
```

## Step 3: AI Semantic Mapping (KEY STEP)

**You (the agent executing this skill) do the mapping.** No external API
calls, no scripts, no intermediate files. Read each case description from
`suite-cases.yaml`, understand the intent, match against the annotated AT-SPI
tree (`at-tree-annotated.yaml`), and fill semantic fields directly in
`cases_mapped.yaml`.

### CRITICAL: No Script-Based Mapping

**DO NOT write Python scripts, regex matchers, or intermediate mapping files.**
Do not create `map_cases.py`, `parse_cases.py`, or any script that uses pattern
matching to fill semantic fields. Read each case description, understand the
user's intent, match against the AT-SPI tree through semantic reasoning, and
fill fields directly in cases.yaml.

This is the single most important thing to get right. In a prior real-world
deployment, the AI created a 1220-line regex script instead of doing the
mapping through understanding. Result: 7% selector coverage, 0% assertion
coverage, 0% execution success. The old pipeline (AI generates each YAML
case individually) achieved 30%+ baseline on the same project.

Script-based mapping is a known failure mode — do not repeat it.

### Batch Processing

For >20 cases, process in batches of ≤10:
1. Read 10 case descriptions + relevant `at-tree-annotated.yaml` sections
2. Map all 10 through understanding
3. Append to `cases_mapped.yaml`
4. Next 10

### DTK Menu Actions (Core Rule)

DTK menus create transient popups NOT in the AT-SPI tree. Menu items are
NOT clickable via `element_action` — they require keyboard navigation:

- **`dtk_main_menu`**: Alt → Down/Right → Enter. Uses `items: ["菜单项"]`.
- **`dtk_context_menu`**: Right-click at target → keyboard navigate → Enter.
  Needs `items` (menu path) + target (`ref`/`selector` or `x`/`y`).
- **`element_action`**: Only for visible non-menu elements (buttons, tabs, fields).

**NEVER use `element_action` for menu items.**

### How to Map Each Step

Read each step description and understand:
1. **What action is the user performing?** (click, type, press key, open menu, assert)
2. **What element is the target?** (extract name and role from the description)
3. **Is this a compound step?** (multiple actions in one description → split into separate CaseSteps)
4. **Is there a precondition clause?** (e.g., "弹出XX后，" → strip, it's context not action)

Write `selector: {name, role}` from the description for runtime AT-SPI lookup.
Do NOT rely on static at-tree node IDs (only ~3.6% coverage). The executor
discovers elements dynamically at runtime by searching the live AT-SPI tree.

**`assert_element` uses `name` only** — the executor constructs dogtail search
expressions like `$//<name>/`, which search by element name. `role` is stored
as metadata but NOT included in the search expression (dogtail parses
`$//name/role/` as hierarchical path traversal, not attribute combination).

**Element Target Priority** (executor checks in this order):
1. **`selector.name`** — runtime AT-SPI lookup by name. Primary for assert_element.
2. **`ref`** — at-tree node ID lookup in elements.yaml. Fallback when selector
   is unavailable (e.g., element has no accessible name).
3. **`x`/`y`** — coordinate-based click. Last resort when no AT-SPI metadata.

For `mouse_click` and other coordinate-based actions, `resolve_coordinates`
uses `name` first (dogtail search), then `role` (predicate search), then
`ref` (elements.yaml), then `x`/`y` fallback.

**Every `assert_element` MUST have a concrete `selector` with a `name`** — an
assertion without a target is a vacuous no-op. If no AT-SPI element can serve
as the assertion target (e.g., purely visual state change with no accessible
element), **omit the assertion entirely** rather than creating one with an
empty or unfindable selector.

**Every `keyboard_type` text must be real input data** — not description
fragments. If text is "任意长度字符" → use placeholder "test_input_123".
If text contains "后" → it's a precondition, skip.

See `references/pitfalls.md` for documented edge cases and their correct
handling. Review pitfalls before starting Step 3 and verify
output against them after mapping.

### Writing the Mapped cases_mapped.yaml

File header MUST include a `=== 格式范例 ===` comment block showing the
exact structure for adding new cases. Each suite MUST retain its 4-field
annotation from `suite-cases.yaml`.

```yaml
# === 格式范例 ===
# metadata:
#   generated_at: "2024-01-01T00:00:00"
#   source: "input.xlsx"
# cases:
#   - id: "suite-id"
#     name: "Suite name"
#     status: "active"
#     annotation:
#       测试界面: "主窗口"
#       测试功能: "工具栏操作"
#       前置条件: "应用已启动"
#       AT元素引用: ["open_button"]
#     steps:
#       - step_type: "action"
#         action: "session_start"
#         command: "app-name"           # full launch command incl. file args
#       - step_type: "action"
#         action: "mouse_click"
#         selector: {name: "打开", role: "push button"}
#       - step_type: "assert"
#         action: "assert_element"
#         selector: {name: "文件内容", role: "text"}  # assert only uses name
# === 格式范例结束 ===

metadata:
  generated_at: "2024-01-01T00:00:00"
  source: "input.xlsx"
cases:
  - id: "suite-id"
    name: "Suite name"
    module: "module-name"
    status: "active"
    annotation:
      测试界面: "主窗口"
      测试功能: "工具栏操作"
      前置条件: "应用已启动"
      AT元素引用: ["open_button"]
    steps:
      - step_type: "action"
        description: "打开终端"
        action: "session_start"
        command: "deepin-terminal"
      - step_type: "action"
        description: "主菜单点击某项，切换设置"
        action: "dtk_main_menu"
        items: ["菜单项A", "子菜单项"]
      - step_type: "assert"
        description: "验证设置已切换"
        action: "assert_window"
        assertion: "window_exists"
```

After mapping, run `youqu at validate --gate 3 --cases-mapped <path> --at-tree-annotated <path>`
to verify format example exists, selectors cross-reference the annotated tree,
and no noise selectors remain.

Then run `youqu at validate --gate 5 --cases-mapped <path>` to verify semantic
safety: no description text as keyboard input, no keyboard_press without a prior
panel-opener action, no selector missing both name and accessible_id.

See `references/pipeline-reference.md` for full cases.yaml schema and
`references/suite-format.md` for all action types and their fields.

## Step 3.5: Assertion Coverage Gate (CRITICAL)

**Before proceeding to Step 4, every suite in cases.yaml MUST have at least
one assertion step.** A test case that performs actions without verifying the
result is a no-op — it will execute steps but never fail, wasting runtime and
providing no coverage signal.

### Gate Procedure

1. Scan every suite in cases.yaml:
   ```
   For each suite:
     has_assert = any(
       step.step_type == "assert" or
       (step.action and step.action.startswith("assert_"))
       for step in suite.steps
     )
     if not has_assert:
         → FAILS quality gate
   ```

2. For each failing suite, read the raw descriptions from cases_raw.yaml
   and identify verification intent (检查, 查看, 验证, 确认, 是否, 应该,
   符合, 出现, 消失, 正确, 可见, etc.).

3. Determine the appropriate assertion:
   - **Automatable (AT-SPI findable element exists)**:
     Insert a `step_type: assert` step with `action: assert_element` and
     a concrete `selector: {name, role}` targeting the element or state
     that the test description intended to verify.
     
     The `description` field of any assertion step MUST contain a
     verification keyword (检查, 查看, 验证, 确认, 是否, 应该, 符合,
     出现, 消失, 正确, 可见) so the parser can classify it correctly.
     
     Example: raw step "检查光标焦点" → insert `assert_element` with
     `selector: {role: "text", name: "cursor"}` after the focus operation.
     
     Example: raw step "右键菜单显示" → insert `assert_element` with
     `selector: {role: "menu", name: ""}` after the right-click.

   - **Not automatable (purely visual, no AT-SPI element)**:
     Mark the suite as `status: unsupported` and write the reason:
     ```yaml
     status: unsupported
     reason: "纯视觉验证：<description of what cannot be automated>"
     ```

   - **No verification intent at all (bare functional operations)**:
     If the case has only `session_start` + bare operations and no step
     description contains verification language, add a basic assertion
     at minimum: `assert_element` checking the application window exists
     (e.g., `selector: {role: "frame", name: "deepin-terminal"}`).

4. Re-verify after supplementing: the gate must pass with ALL suites having
   at least one assertion before proceeding to Step 4.

### Programmatic Enforcement

Use `youqu at generate --assert-gate` to enforce the gate at generation
time. The generator scans all generated SuiteCases and reports any without
assert_steps. With `--assert-gate`, it exits with error if any are found.
Without the flag, it prints warnings but proceeds.

### Why This Matters

Without this gate, many generated cases end up with zero assertion steps —
every test executes actions but never verifies anything. The quality gate
catches this gap before generation, ensuring every generated test case
provides meaningful coverage signal. Cases that cannot supply an assertion
are candidly marked `unsupported` rather than shipped as silent no-ops.

## Step 4: Generate + Validate

### 4a: Generate

```bash
youqu at generate --cases <mapped_cases.yaml> --output <output_dir> \
  --app <app_name> --at-tree <at_tree.yaml>
```

Output: `elements.yaml`, `<module>/<module>.suite.yaml`, `app-optimization.md`.

### 4b: Validate

**Structure checks**:
- Suite files use `suites:` (NOT `specs:`)
- `session_start.command` uses app launch command
- `wait` values are in **seconds** (float: 0, 1.0, 3.0)
- `dtk_main_menu` / `dtk_context_menu` for menu operations (NOT `element_action`)
- Steps from the same test case are in the same SuiteCase

**Quality checks**: Verify output against `references/pitfalls.md` — no empty
selectors, no garbage keyboard_type text, no precondition fragments as steps.
Re-verify the assertion coverage gate conditions still hold.

**Runtime validation** (requires desktop):
```bash
youqu at run --testdir <output_dir> [--suite <suite_file>]
```
**NOT** `python -m src.yaml_test.suite` — that is a different executor.
The AT pipeline uses `AtSuiteExecutor` in `src/at/executor/`.

## CLI Quick Reference

| Command | Required Args | Optional Args |
|---------|--------------|---------------|
| `youqu at scan` | --src, --app | --output, --include-dirs |
| `youqu at record` | --app | --launch, --output, --gui |
| `youqu at merge` | --record | --scan, --app, --output |
| `youqu at parse` | --input, --output | --at-tree (deprecated) |
| `youqu at tree-info` | --at-tree, --output | --format (yaml\|text, default yaml) |
| `youqu at split` | --cases, --at-tree, --output | --app |
| `youqu at docs` | app | --output |
| `youqu at precandidate` | — | --cases, --at-tree, --output, --module-dir |
| `youqu at validate` | — | --gate (1\|2\|3\|4\|5\|all), --at-tree-annotated, --suite-cases, --cases-mapped, --generate-output, --element-gaps |
| `youqu at generate` | --cases, --output | --app, --at-tree, --no-assert-gate |
| `youqu at run` | — | --suite, --testdir, -k, --spec-ids, --tags, --skip-env-check |
| `youqu at smoke` | — | --modules-dir, --module-dir, --skip-env-check |
| `youqu at verify` | --suite | --spec-id, --skip-env-check |

## at-tree.yaml v2.0 Format (scan + record + merge)

The `scan` + `record` + `merge` pipeline produces `at-tree.yaml` v2.0
with two layers:

```yaml
version: "2.0"
app: "deepin-screenshot"
tree:                       # Persistent layer (always-visible elements)
  - id: n0
    role: frame
    name: "截图区域"
    children: [...]
transient_contexts:         # Transient layer (menus, dialogs, child windows)
  - id: right_click_menu_000
    trigger:
      type: right_click
      element: {name: "View_ImageList", role: "list"}
    items:
      - {name: "复制", role: "menu item"}
      - {name: "粘贴", role: "menu item"}
    at_tree: "states/01_menu_open.yaml"
```

**AI mapper must read both layers:**
- `tree`: same as v1.0, contains persistent elements for `element_action`/`assert_element`
- `transient_contexts`: menu items, dialogs, child windows — these are NOT in the main tree
  - Menu items → use `dtk_main_menu`/`dtk_context_menu` (NOT `element_action`)
  - Dialog elements → reference via `at_tree` snapshot path
  - Child window elements → separate app, may need separate handling

The `merge` command always produces v2.0. If `record_session.yaml` is
absent, it falls back to old-style state snapshots (v1.0 without
`transient_contexts`).

## Reference Files

| File | Purpose |
|------|---------|
| `references/pipeline-reference.md` | CLI commands, input/output formats, cases.yaml schema |
| `references/suite-format.md` | Generated suite YAML structure, action fields, elements.yaml, action types |
| `references/pitfalls.md` | 18 documented edge cases — review before Step 3, verify after |
