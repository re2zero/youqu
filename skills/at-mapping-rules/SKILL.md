---
name: at-mapping-rules
description: >
  Step semantic parsing protocol for AT-SPI case mapping: parse each raw test
  step's operation/target/expected/precondition and never confuse them.
  Triggers: AT用例映射, LLM map, cases_mapped, 步骤语义解析, selector填写,
  映射规范, AT case mapping, precondition extraction, UNSUPPORTED classification.
version: "1.0.0"
license: MIT
author: Uniontech
---

# AT Mapping Rules

Step semantic parsing protocol for `cases_raw.yaml` → `cases_mapped.yaml` mapping.
This skill defines the **rules** the AI must follow when doing Step 3 (semantic
mapping) of the `at-case-generator` pipeline. It does NOT replace that skill —
it complements it with strict, testable mapping constraints.

## When to Use

- During Step 3 of `at-case-generator` pipeline (cases_raw → cases_mapped)
- Any time you map human-written test steps to executable YAML actions
- Reviewing/fixing existing cases_mapped.yaml that has mapping errors

## When NOT to Use

- Dumping AT-SPI tree → use `youqu at dump`
- Running AT suites → use `youqu at run`
- Full pipeline orchestration → use `at-case-generator` skill (this is a sub-skill)

## Core Problem This Skill Solves

LLM mapping routinely confuses 4 distinct semantic layers in test step descriptions:

| Layer | What it is | Correct YAML |
|-------|-----------|--------------|
| **operation** | "点击X按钮" | `element_action` / `mouse_click` + selector |
| **expected** | "显示清空按钮" | `assert_element` + selector |
| **precondition** | "打开查找框" | Must become a **prior action step**, not a description |
| **note** | "触摸屏一并测试" | Omit or mark UNSUPPORTED |

When these layers are confused, the generated YAML either inputs description
text as keyboard input, skips required preconditions, or asserts nothing useful.

## Step Semantic Parsing Protocol

### Rule 1: Four-Field Decomposition

For EVERY step in `cases_raw.yaml`, decompose the description into 4 fields
before writing any YAML:

```
description: "打开终端，右键菜单选择搜索，检查搜索显示"
         ↓ decompose
operation:    right-click → context menu → select "搜索"
target:       context menu item "搜索"
expected:     search panel visible (放大镜 + 输入框 + 向上/向下按钮)
precondition: terminal window open (from session_start)
```

Then write YAML from the decomposition — NOT from the raw description.

### Rule 2: Expected Results Become Assert Steps

**NEVER** put expected result text into `keyboard_type.text`.

Wrong:
```yaml
- action: keyboard_type
  text: 内容被清空；可以重新输入    # ← this is an EXPECTED RESULT, not input!
```

Right:
```yaml
- action: assert_element          # ← expected result → assertion
  selector:
    name: 清空
```

### Rule 3: Preconditions Become Action Steps

**NEVER** describe a precondition without executing it.

Wrong (step says "打开查找框按ESC" but only generates ESC):
```yaml
- action: keyboard_press
  key: escape                    # ← precondition "打开查找框" was skipped!
```

Right:
```yaml
- action: dtk_main_menu           # or keyboard_hot_key ctrl+alt+f
  items: [搜索]                   # ← precondition executed first
- action: keyboard_press
  key: escape                    # ← THEN press ESC
- action: assert_element         # ← expected: 查找框关闭
  selector:
    name: 搜索
  do: assert_not_exists
```

### Rule 4: Button Clicks Use Element Selector, Not Guessed Keys

**NEVER** guess keyboard shortcuts when the step says "click X button".

Wrong:
```yaml
- action: keyboard_press         # ← guessed Enter for "点击向下搜索"
  key: enter
```

Right:
```yaml
- action: element_action         # ← use selector from at-tree
  selector:
    name: 向下搜索
    role: push button
  do: click
```

If the button is not in at-tree, mark the step UNSUPPORTED (see Rule 9).

## Selector Filling Constraints

### Constraint 1: At Least One Locator

Every `element_action`, `mouse_click`, `assert_element` step MUST have a
selector with at least one of:

| Field | Priority | When to use |
|-------|----------|-------------|
| `accessible_id` | 1st | Most stable; prefer when at-tree has it |
| `name` | 2nd | AT-SPI visible name (exact match at runtime) |
| `role` | 3rd | Only when name is empty |
| `parent` + `parent_role` | disambiguation | Required when multiple elements share the same name |
| `index` | disambiguation | Zero-based; when parent alone can't disambiguate |
| `child_index` | child navigation | Picks the Nth child of a located container (see Constraint 3) |
| `child_role` / `child_name` | child filter | Optionally filter children by role/name before indexing |

### Constraint 2: Hierarchy Disambiguation

When at-tree shows multiple elements with the same name (e.g., multiple "确定"
buttons in different dialogs), the selector MUST include `parent`:

```yaml
selector:
  name: 确定
  parent: 设置对话框           # ← disambiguates which dialog's button
  parent_role: dialog
```

### Constraint 3: Dynamic List Child Navigation

When the target is a **child of a container whose contents are only known at
runtime** (e.g., a `list`/`icon list`/`tree` whose items are populated by the
app, not by the at-tree dump), locate the container first, then navigate to
its Nth child with `child_index`.

`child_index` is **orthogonal** to `index`:
- `index` = which of the *same-named containers* to pick (parent-level disambiguation)
- `child_index` = which *child inside* the chosen container to pick

Supported actions (child nav applies wherever a selector is used):
`mouse_click`, `mouse_right_click`, `mouse_double_click`, `dtk_context_menu`,
`element_action`, `element_set_value`, `assert_element`, `assert_not_exists`.

Example — right-click the 1st item in a runtime-populated image list:

```yaml
- action: dtk_context_menu
  selector:
    name: View_ImageList
    role: list
    child_index: 0          # ← the list's 1st child (runtime)
    menu:
      - 复制
```

Example — assert the 2nd list item exists:

```yaml
- action: assert_element
  selector:
    name: View_ImageList
    role: list
    child_index: 1
```

Filter children by role before indexing (e.g., 3rd `list item` in the list):

```yaml
selector:
  name: View_ImageList
  role: list
  child_role: list item
  child_index: 2
```

`child_index` is zero-based and supports negative values (`-1` = last child).

### Constraint 4: DTK Menu Items Use Menu Navigation

DTK menu items are **transient** — they only exist in AT-SPI tree when the
menu is open. **NEVER** use `element_action` for menu items.

Wrong:
```yaml
- action: element_action         # ← menu item not in AT-SPI tree when closed!
  selector:
    name: 设置
```

Right:
```yaml
- action: dtk_main_menu
  items: [设置]                  # ← keyboard navigation, not AT-SPI lookup
```


### Constraint 5: File Dialog Actions Use Keyboard Simulation

File dialog operations (`file_dialog_select`, `file_dialog_cancel`) handle the
native file picker (deepin/UOS portal) via xdotool keyboard simulation. Like
DTK menus, they do NOT use AT-SPI element lookup.

**CRITICAL: Must trigger the file dialog first.** A `file_dialog_select` or
`file_dialog_cancel` without a prior step that opens the dialog will send
keys to the main window instead.

```yaml
# Correct: trigger first, then select
- action: keyboard_hot_key
  key: ctrl+o
  wait: 1.0
- action: file_dialog_select
  path: ${TEST_FILES_DIR}/test.png
  wait: 3.0
```

```yaml
# Correct: cancel dialog
- action: file_dialog_cancel
  wait: 1.0
```

**NEVER use `element_action` to interact with file dialog elements.** The
native file dialog is a separate process, not part of the app's AT-SPI tree.
File dialog elements must be accessed via `file_dialog_select`/`file_dialog_cancel`.

## Assert Quality Rules

### Rule 5: Assert Specific, Not Generic

**NEVER** use only `assert_window` for all assertions. `assert_window` only
checks "is the app window alive" — it validates nothing about the test intent.

| Step says | Wrong assert | Right assert |
|-----------|-------------|-------------|
| "显示清空按钮" | `assert_window` | `assert_element` + selector name=清空 |
| "输入框显示123" | `assert_window` | `assert_ocr_exists` + text=123 |
| "背景变模糊" | `assert_window` | `assert_image_exists` + template |
| "窗口关闭" | `assert_window` | `assert_window_count` + expected=0 |

### Rule 6: Every Suite Has At Least One Real Assert

Each suite MUST have at least one assert step that is NOT `assert_window`.
If you cannot write a specific assert, the case is likely UNSUPPORTED.

## UNSUPPORTED Classification

### Rule 7: Mark, Don't Force

When a step cannot be automated, mark the **entire case** as UNSUPPORTED:

```yaml
- id: case_XXX
  name: 触摸屏滑动测试
  status: unsupported
  reason: requires touchscreen hardware input
```

### Rule 8: UNSUPPORTED Categories

| Category | Example | Reason |
|----------|---------|--------|
| Touchscreen/trackpad | "用触摸屏滑动" | No AT-SPI API for touch input |
| Pure human judgment | "界面美观"/"动画流畅" | No machine-verifiable assertion |
| External hardware | "连接显示器" | Requires physical hardware |
| Network environment | "SSH连接远程" | Environment-dependent |
| Time-dependent | "等待10秒后" with no state change | Only `wait` + no assert = no test |

**NEVER** generate no-op YAML (session_start → wait → session_stop → assert_window)
for UNSUPPORTED cases. Mark them and move on.

## Anti-Patterns (Real Examples)

### Anti-Pattern 1: Expected Result as Keyboard Input

**Raw**: "5. 点击x" → "5. 输入内容被清空；可以重新输入"

**Bad mapping**:
```yaml
- action: keyboard_type
  text: 内容被清空；可以重新输入    # ← expected result typed as input!
```

**Why it fails**: The text "内容被清空；可以重新输入" is the **expected result**
of clicking the X button, not text to type. At runtime this types Chinese
punctuation into the search box, which is meaningless.

**Correct**:
```yaml
- action: element_action
  selector: {name: 清空}
  do: click
- action: assert_element
  selector: {name: 清空}
  # assert_not_exists: 清空按钮消失说明内容已清空
```

### Anti-Pattern 2: Skipped Precondition

**Raw**: "打开查找框按ESC" → "查找框关闭"

**Bad mapping**:
```yaml
- action: keyboard_press
  key: escape
- action: keyboard_press
  key: escape                    # ← "打开查找框" was never executed!
```

**Why it fails**: ESC is pressed when no find bar is open → nothing happens.
The assertion `assert_window` passes trivially (app didn't crash) but the
test verified nothing.

**Correct**:
```yaml
- action: keyboard_hot_key
  key: ctrl+alt+f               # ← open find bar first
- action: assert_element
  selector: {name: 查找}
- action: keyboard_press
  key: escape
- action: assert_element
  selector: {name: 查找}
  do: assert_not_exists         # ← find bar closed
```

### Anti-Pattern 3: Guessed Shortcut for Button Click

**Raw**: "点击向下搜索按钮"

**Bad mapping**:
```yaml
- action: keyboard_press
  key: enter                     # ← guessed! button may not respond to Enter
```

**Correct**:
```yaml
- action: element_action
  selector:
    name: 向下搜索
    role: push button
  do: click
```

### Anti-Pattern 4: Description Text as Input

**Raw**: "输入任意字符：123ASsdh周圣》?:%$%^&"

**Bad mapping**:
```yaml
- action: keyboard_type
  text: 任意字符：123ASsdh周圣》?:%$%^&  # ← "任意字符：" is description, not input!
```

**Correct**:
```yaml
- action: keyboard_type
  text: 123ASsdh周圣》?:%$%^&          # ← strip the description prefix
```

### Anti-Pattern 5: No-Op Suite

**Bad mapping** (entire suite):
```yaml
setup:
- action: session_start
suites:
- id: case_X_s1
  steps:
  - action: wait
    wait: 1.0
  assert_steps:
  - action: assert_window        # ← validates nothing
teardown:
- action: session_stop
```

**Why it fails**: This suite starts the app, waits 1 second, stops it, and
"asserts" the window exists. It tests nothing. The original case probably
had steps that couldn't be mapped → should be UNSUPPORTED, not a no-op.

## Pre-Mapping Checklist

Before writing ANY YAML for a case:

- [ ] Read the case's step descriptions and identify which are operations vs.
  expected results vs. preconditions vs. notes
- [ ] For each operation, find the target element in at-tree-annotated.yaml
- [ ] If the element is NOT in at-tree, check if it's a DTK menu item (use
  `dtk_main_menu`/`dtk_context_menu`) or a file dialog operation (use
  `file_dialog_select`/`file_dialog_cancel`), or mark UNSUPPORTED
- [ ] For each expected result, determine the assert type (element/ocr/image)
- [ ] For each precondition, ensure it becomes a prior action step
- [ ] If any step is touchscreen/human-judgment/hardware → mark UNSUPPORTED

## Post-Mapping Checklist

After writing cases_mapped.yaml, before `youqu at generate`:

- [ ] No `keyboard_type.text` contains expected-result language (e.g., "显示",
  "被清空", "可以重新", "正常", "异常")
- [ ] Every `element_action`/`mouse_click` has a selector with name or
  accessible_id
- [ ] No menu item uses `element_action` (must use `dtk_main_menu`/`dtk_context_menu`)
- [ ] `file_dialog_select`/`file_dialog_cancel` has a preceding dialog trigger step
  (`keyboard_hot_key`, `element_action`, or `dtk_main_menu`)
- [ ] Runtime-populated list/tree children use `child_index` (not a bare `index`)
- [ ] Every suite has at least one non-`assert_window` assert step
- [ ] No suite is a no-op (session_start → wait → assert_window → session_stop)
- [ ] UNSUPPORTED cases are marked and have `reason` filled
