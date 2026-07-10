---
name: at-case-generator
version: "0.3.0"
description: >
  Use when needing to generate AT-SPI test suites from xlsx/csv test case
  documents for a Linux desktop application. Triggers: AT用例生成,
  at-case generation, AT suite generation, AT-SPI suite YAML, at-tree用例,
  桌面应用AT测试, AT自动化用例, youqu at parse, youqu at generate,
  youqu at tree-info.
---

# AT Case Generator

Convert xlsx/csv test case documents into executable AT-SPI suite YAML.
The pipeline is **AI-driven**: the AI in the session does semantic mapping
(not a CLI LLM call). Framework provides data tools; AI provides understanding.

## When to Use

- You have xlsx/csv test case documents for a Linux desktop application
- You need executable AT-SPI test suites from those documents
- Input is a PR/issue/requirement and you want to generate cases directly

## When NOT to Use

- You need standard YAML test cases (use `youqu-case-generator` instead)
- You need to run existing AT suites (use `youqu at run` directly)
- You need to dump the AT-SPI tree only (use `youqu at dump` directly)

## Pipeline (4 Steps)

```
Step 1: Pre-flight checks
Step 2: Data preparation
    youqu at parse <xlsx> → cases.yaml (raw, format-only)
    youqu at tree-info <at-tree> → compact_tree.txt (for AI reading)
Step 3: AI semantic mapping (THIS IS THE KEY STEP)
    AI reads compact_tree.txt + raw cases.yaml
    AI fills action, element_ref, selector, items, key, text, assertion
    AI writes semantically mapped cases.yaml
Step 4: Generate + validate
    youqu at generate --cases <mapped> --output <dir> --app <app> --at-tree <tree>
```

`youqu at map` is **deprecated**. Element mapping is done by the AI in Step 3,
not by a CLI LLM call.

## Step 1: Pre-flight Checks

- `youqu --version` — CLI installed
- xlsx/csv input exists, columns match supported aliases (see pipeline-reference.md)
- at-tree.yaml exists and is fresh (check `metadata.generated_at`)

## Step 2: Data Preparation

### 2a: Parse xlsx → raw cases.yaml

```bash
youqu at parse --input <xlsx_or_csv> --output <cases_yaml>
```

Output: `cases.yaml` with CaseStep entries containing `step_type`,
`description`, `element_hint`, `menu_path` — but **no semantic fields**
(action, element_ref, selector are null). This is a format-only conversion.

### 2b: Generate compact tree for AI reading

```bash
youqu at tree-info --at-tree <at_tree.yaml> --output <compact_tree.txt>
```

Output: human-readable text file with one line per AT-SPI node:
```
n5 | role: popup menu | name: DTitlebarMainMenu | object_name: 
n6 | role: menu item | name: 主题 | object_name:  | parent: n5
n7 | role: popup menu | name: DTitlebarThemeMenu | object_name:  | parent: n5 > n6
n8 | role: menu item | name: 浅色 | object_name:  | parent: n5 > n6 > n7
```

This file is compact enough for the AI to read in-context (typically 500-2000
lines) and contains the full parent-child hierarchy needed for semantic mapping.

### 2c: Acquire at-tree.yaml (if not present)

```bash
youqu at dump dtk <app_name> --src <source_dir> --output <output_dir>
```

Requires desktop environment with target app running.

## Step 3: AI Semantic Mapping (KEY STEP)

The AI reads the compact tree and raw cases.yaml, then fills in semantic fields
for each step. This is NOT a CLI command — the AI does this in-session.

### DTK Menu Execution Mechanism (CRITICAL)

**`dtk_main_menu`**: Alt key opens menu → keyboard Down/Right navigates →
Enter confirms. **Does NOT find AT-SPI elements**. Uses `items` field for
menu path (e.g., `["主题", "深色"]`).

**`dtk_context_menu`**: Right-click at target coordinates → keyboard
navigates menu → Enter confirms. Requires:
- `items`: menu path (e.g., `["设置"]`)
- Target: `element_ref`/`selector` (AT-SPI element to right-click) OR
  `x`/`y` (direct coordinates)

**`element_action`**: AT-SPI `find_element` → `.click()`/`.hover()`/`.drag()`.
Only for **visible non-menu elements** (buttons, labels, input fields, tabs).

**CORE RULE**: Even if at-tree has `menu item` role nodes, **DO NOT use
`element_action` for menu items**. Menu items are not visible/clickable in
AT-SPI until the menu is opened — use `dtk_main_menu` or `dtk_context_menu`
with keyboard navigation.

### Universal Detection Rules

| Detection Condition | Map to action | Fields |
|---------------------|---------------|--------|
| at-tree: `popup menu` / `DTitlebarMainMenu` child node | `dtk_main_menu` | `items: ["item name"]` |
| Menu item has `ShowMenu` action → has submenu | `dtk_main_menu` | `items: ["parent", "child"]` |
| Description: "右键"/"右击" + position | `dtk_context_menu` | `items: [...]` + ref/selector or x/y |
| Description: "菜单"+"点击" + element under menu node | `dtk_main_menu` | `items: [...]` |
| Description: "对话框"/"弹框" + at-tree `dialog` role | `element_action` | ref/selector + note |
| Description: single key (Enter/Escape/F1/Tab) | `keyboard_press` | `key: "enter"` |
| Description: combo key (Ctrl+C/Alt+Tab) | `keyboard_hot_key` | `key: "ctrl+c"` |
| Description: "输入"/"填写" | `keyboard_type` | `text: "content"` |
| Description: "确认/验证XX" | `assert_element` etc. | ref/selector |
| Has AT-SPI name+role, visible non-menu element | `element_action` | ref/selector |

**keyboard_press vs keyboard_hot_key**:
- Single key (Enter, Escape, F1, Tab) → `keyboard_press`, `key: "enter"`
- Key combination (Ctrl+C, Alt+Tab, Shift+Down) → `keyboard_hot_key`,
  `key: "ctrl+c"` (lowercase, `+` separator)

**dtk_context_menu coordinate source**:
- If at-tree has the target element → use `element_ref`/`selector`
- If target is a fixed position → use `x`/`y` coordinates
- Both approaches need `items` for the menu path

### Compound Step Splitting

Many xlsx test steps combine multiple operations in one description.
The AI MUST split compound steps into individual CaseStep entries:

| Pattern | Split into |
|---------|-----------|
| "打开XX" + app name | `session_start` with `command: "app-name"` |
| "菜单点击XX" / "主菜单XX" | `dtk_main_menu` with `items: ["XX"]` |
| "输入XX" | `keyboard_type` with `text: "XX"` |
| "按下XX快捷键" (single) | `keyboard_press` with `key: "xx"` |
| "按下XX快捷键" (combo) | `keyboard_hot_key` with `key: "ctrl+xx"` |
| "右键XX" | `dtk_context_menu` with `items` + coordinate source |
| "确认/验证XX" | `assert_element` / `assert_window` |

Example: "打开终端，主菜单点击主题，切换深色" → 3 steps:
1. `session_start` + `command: "deepin-terminal"`
2. `dtk_main_menu` + `items: ["主题", "深色"]`
3. `assert_window` (verify theme changed)

### Element Matching

When matching step descriptions to at-tree elements:
1. Search compact_tree.txt for matching `name` + `role`
2. Use `parent` path to disambiguate same-named elements
3. If no match found → set `needs_accessible_name: true` and
   `accessible_name_suggestion: "suggested name"`
4. Set `element_ref` to the at-tree node ID (e.g., "n42")
5. Set `selector` to `{"name": "...", "role": "..."}` from at-tree

### Writing the Mapped cases.yaml

After semantic mapping, the AI writes cases.yaml with all fields filled:

```yaml
metadata:
  generated_at: "2024-01-01T00:00:00"
  source: "input.xlsx"
suites:
  - id: "suite-id"
    name: "Suite name"
    module: "module-name"
    status: "active"
    steps:
      - step_type: "action"
        description: "打开终端"
        action: "session_start"
        command: "deepin-terminal"
        element_ref: null
        selector: null
      - step_type: "action"
        description: "主菜单点击主题，切换深色"
        action: "dtk_main_menu"
        items: ["主题", "深色"]
        element_ref: null
        selector: null
      - step_type: "assert"
        description: "验证主题已切换"
        action: "assert_window"
        element_ref: null
        selector: null
        assertion: "window_exists"
```

## Step 4: Generate + Validate

### 4a: Generate

```bash
youqu at generate --cases <mapped_cases.yaml> --output <output_dir> \
  --app <app_name> --at-tree <at_tree.yaml>
```

The `--at-tree` parameter enables full elements.yaml extraction from the
AT-SPI tree (not just from cases.yaml subset).

Output:
- `elements.yaml` — full element registry (at-tree nodes + cases mappings)
- `<module>/suite.suite.yaml` — executable suite files
- `app-optimization.md` — elements needing setAccessibleName()

### 4b: Validate

- `elements.yaml` exists with entries
- Suite files use `suites:` (NOT `specs:`)
- `session_start.command` uses app launch command
- `app` field in suite config is the app name
- `wait` values are in **milliseconds**
- Action names match executor HANDLERS (30 handlers — see suite-format.md)
- `dtk_main_menu` / `dtk_context_menu` used for menu operations
  (NOT `element_action`)
- `app-optimization.md` exists if any steps have `needs_accessible_name: true`
- Steps from the same test case are in the same SuiteCase (context preserved)
- Optional: Run `youqu at run --suite <suite_file>` (requires desktop)

## CLI Quick Reference

| Command | Required Args | Optional Args |
|---------|--------------|---------------|
| `youqu at dump dtk` | type, --app, --src | --output |
| `youqu at parse` | --input, --output | — |
| `youqu at tree-info` | --at-tree, --output | — |
| `youqu at map` | (deprecated) | — |
| `youqu at generate` | --cases, --output | --app, --at-tree |
| `youqu at run` | — | --suite, --testdir, -k, --spec-ids, --tags |

## Reference Files

| File | Purpose |
|------|---------|
| `references/pipeline-reference.md` | CLI commands, input/output formats, cases.yaml schema |
| `references/suite-format.md` | Generated suite YAML structure, action types, elements.yaml |
| `references/pitfalls.md` | Common pipeline failures and solutions |
