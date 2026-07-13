# AT Suite YAML Format

## Output File Structure

```
<output_dir>/
├── elements.yaml                         # shared element registry
├── app-optimization.md                   # (optional) elements needing setAccessibleName()
└── <module>/
    └── {module}.suite.yaml             # suite config with setup/teardown/specs
```

## Suite Config File

```yaml
name: "module_suite"
app: "app-name"
description: ""
module: "module-name"
tags: []
fast_fail: false
env_check: []
setup:
  - action: session_start
    command: "app-name"
    wait: 3.0
suites:                   # MUST be "suites:" NOT "specs:"
  - id: "suite_id_s0"
    name: ""
    description: ""
    tags: []
    steps:
      - action: dtk_main_menu
        items: ["主题", "深色"]
        wait: 0
        note: "切换深色主题"
      - action: element_action
        ref: "ok_button"
        do: "click"
        wait: 0
    assert_steps:
      - action: assert_element
        ref: "ok_button"
    timeout: null
teardown:
  - action: session_stop
```

## SuiteActionStep Fields

| Field | Type | Description |
|-------|------|-------------|
| action | string | Action type (must match HANDLERS) |
| ref | string/null | Element reference (lookup in elements.yaml) |
| selector | dict/null | Inline selector {name, role, name_pattern} |
| command | string/null | Command for session_start |
| wait | float/null | Wait time in seconds (passed to time.sleep; session_start default: 3.0, others: 0) |
| do | string/null | Operation: click, hover, drag |
| x | int/null | X coordinate |
| y | int/null | Y coordinate |
| items | list[string]/null | Menu path (dtk_main_menu, dtk_context_menu) |
| path | string/null | File path |
| prompt | string/null | VLM prompt |
| evidence | string/null | Evidence file path |
| app | string/null | App name (assert_window_count) |
| expected | int/null | Expected count |
| name_pattern | string/null | Regex pattern for name matching |
| key | string/null | Key name (keyboard_press, keyboard_hot_key) |
| text | string/null | Text to type (keyboard_type, element_set_value) |
| value | any/null | Arbitrary value (mouse_scroll amount, dbus params) |
| note | string/null | Human-readable note (e.g., dialog description) |

## Context Preservation in SuiteCases

The generator groups CaseSteps into SuiteCases with context preservation:

1. **session_start** → breaks into a new SuiteCase
2. **Assert steps** → attach to current SuiteCase's `assert_steps`
3. **Other steps** → append to current SuiteCase's `steps`
4. **Invalid action** → skipped with warning (not included in any SuiteCase)

This means steps from the same test case (between two session_start boundaries)
remain in the same SuiteCase, preserving inter-step context.

## DTK Menu Actions

### dtk_main_menu

Keyboard navigation: Alt opens menu → Down/Right navigates → Enter confirms.
**Does NOT use AT-SPI element lookup.**

```yaml
- action: dtk_main_menu
  items: ["主题", "深色"]
  wait: 0
```

`items` is the menu path. Single-level: `["帮助"]`. Multi-level:
`["主题", "深色"]`.

### dtk_context_menu

Right-click at target → keyboard navigates → Enter confirms.

```yaml
- action: dtk_context_menu
  items: ["设置"]
  ref: "terminal_area"    # via elements.yaml
  # OR
  x: 500
  y: 300
  wait: 0
```

Requires TWO pieces:
1. **Where to right-click**: `ref`/`selector` (AT-SPI element) or `x`/`y`
2. **Menu path**: `items` list

## Action Types

| Action | Key Fields | Description |
|--------|-----------|-------------|
| session_start | command, wait | Launch app (wait default 3.0s) |
| session_stop | — | Terminate app |
| dtk_main_menu | items | Navigate DTK main menu by keyboard |
| dtk_context_menu | items | Navigate DTK context menu by keyboard |
| element_action | ref, selector, do | AT-SPI element operation |
| element_set_value | ref, text | Set text value on element |
| keyboard_press | key | Press single key (e.g., "enter") |
| keyboard_hot_key | key | Press key combo (e.g., "ctrl+c") |
| keyboard_type | text | Type text string |
| keyboard_type_text | text | Alias for keyboard_type |
| mouse_click | ref/selector or x/y | Left click |
| mouse_right_click | ref/selector or x/y | Right click |
| mouse_double_click | ref/selector or x/y | Double click |
| mouse_drag | ref/selector | Drag |
| mouse_scroll | value | Scroll (negative=down) |
| dbus_call | value | D-Bus method call (value is param dict) |
| dbus_get_property | value | Read D-Bus property (value is param dict) |
| screenshot | — | Capture screenshot |
| assert_element | ref, selector | Assert element exists |
| assert_window | name_pattern | Assert window exists (name_pattern is regex; defaults to DMainWindow) |
| assert_not_exists | ref, selector | Assert element NOT exists |
| assert_window_count | app, expected | Assert window count |
| assert_process_running | app | Assert process running |
| assert_process_not_running | app | Assert process NOT running |
| assert_file_exists | path | Assert file exists |
| assert_file_not_exists | path | Assert file NOT exists |
| assert_image_exists | path | Assert image matches |
| assert_image_not_exists | path | Assert image NOT matches |
| assert_ocr_exists | value | Assert OCR text exists |
| assert_ocr_not_exists | value | Assert OCR text NOT exists |
| wait | wait | Wait |

## elements.yaml

Generated from at-tree.yaml (full extraction) + cases.yaml mappings (priority).

```yaml
elements:
  n42:
    name: "确定"
    role: "push button"
  n57:
    name: "TerminalDisplay"
    role: "panel"
  n6:
    name: "主题"
    role: "menu item"
```

With `--at-tree` parameter, ALL at-tree nodes appear in elements.yaml (not just
referenced ones). Cases.yaml mappings override at-tree entries with the same ID.

## app-optimization.md

Collects all steps with `needs_accessible_name: true`:

```markdown
# App Optimization Report: <app_name>

## Elements Needing setAccessibleName()

### Suite: <suite_id> — <suite_name>
- **Step**: <step description>
- **Suggestion**: <accessible_name_suggestion>
```

## Differences from Standard YAML

| Aspect | Standard YAML (youqu-case-generator) | AT Suite (at-case-generator) |
|--------|--------------------------------------|------------------------------|
| Suite cases field | suites: | suites: |
| Menu actions | main_menu_comb, context_menu_comb | dtk_main_menu, dtk_context_menu |
| Assertions | Inline per step (step.assert) | Case-level assert_steps[] |
| Element registry | elements.yaml (app, vars, elements) | elements.yaml (elements only) |
| Setup wait | wait: 1.0 (seconds) | wait: 3.0 (seconds) |
| Suite filename | various | {module}.suite.yaml |
