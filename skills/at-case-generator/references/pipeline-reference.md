# AT Case Generator Pipeline Reference

This document provides a reference for the YouQu AT test pipeline CLI commands, input formats, intermediate YAML formats, and LLM configuration. It is intended for AI agents and developers using the `youqu at` pipeline.

## Pipeline Overview

```
xlsx/csv ──[parse]──→ cases.yaml ──[map]──→ mappings.yaml
                                                 │
                      at-tree.yaml ──────────────┘
                                                 │
                 cases.yaml + mappings.yaml ──[generate]──→ suite YAML + elements.yaml
```

## CLI Commands

### parse

Converts xlsx or text input into `cases.yaml`.

Command:
```bash
youqu at parse --input <path> --output <path> [--at-tree <path>]
```

Parameters:
- `--input`: required. xlsx or text directory path.
- `--at-tree`: optional (default=""). path to at-tree.yaml for UI context.
- `--output`: required. output cases.yaml path.

### map

Maps `cases.yaml` steps to AT-SPI elements using `at-tree.yaml`, producing `mappings.yaml`.

Command:
```bash
youqu at map --at-tree <path> --cases <path> --output <path>
```

Parameters:
- `--at-tree`: required. path to at-tree.yaml.
- `--cases`: required. path to cases.yaml.
- `--output`: required. output mappings.yaml path.

**Special Case: dtk_context_menu — two requirements**

Right-click context menus are **dynamically generated** at runtime. Their menu items are NOT present in at-tree.yaml. The map phase should NOT attempt to match context menu items to at-tree nodes.

A dtk_context_menu step requires TWO pieces of information:

1. **Whose context menu** — the target UI component where the right-click happens. The map phase must provide a `selector` (or coordinates) for this component (e.g., terminal display area, tab bar, dock icon).
2. **Menu item names** — the menu_path items for navigating the dynamically opened menu, including sub-menu items if any (e.g., `["编码"]` or `["自定义命令", "添加自定义命令"]`).

See e2e test case pattern: `context_menu_comb` action uses `x`/`y` (target location) + `items` (menu item names). The AT executor `dtk_context_menu` follows the same logic.

Current framework limitation: the generator outputs only `items` (menu_path) without a `selector` for the target component. The agent should verify dtk_context_menu steps capture both target component info and menu items during parse.

### generate

Generates suite YAML and elements.yaml from `cases.yaml` and `mappings.yaml`.

Command:
```bash
youqu at generate --cases <path> --mappings <path> --output <dir>
```

Parameters:
- `--cases`: required. path to cases.yaml.
- `--mappings`: required. path to mappings.yaml.
- `--output`: required. output directory.

## xlsx/csv Input Format

The input xlsx or csv file should contain the following columns. Supported column name aliases are:

- `id`: 用例编号, ID, 编号, 序号
- `title`: 用例标题, 标题, 用例名称, 测试点
- `module`: 所属模块, 模块, 功能模块, 测试模块
- `priority`: 用例级别, 优先级, 级别, 重要程度
- `precondition`: 前置条件, 前提条件, 预置条件
- `steps`: 步骤, 测试步骤, 操作步骤, 用例步骤
- `expected`: 预期, 预期结果, 期望结果, 预期输出
- `case_type`: 用例类型, 类型, 测试类型

## at-tree.yaml Structure

The `at-tree.yaml` file contains the AT-SPI tree structure of the application.

Example structure:
```yaml
metadata:
  app: "app-name"
  source_commit: ""
  generated_at: "ISO8601"
  scan_mode: "hybrid"
structure:
  windows:
    - id: "node-id"
      role: "panel"
      name: "Window Title"
      object_name: "ClassName"
      accessible_id: ""
      source: "runtime"  # or "static"
      note: ""
      children: [...]
```

**Note**: The agent should check `metadata.generated_at` and `metadata.source_commit` to verify the freshness of the at-tree.yaml file before using it.

## cases.yaml Structure

The `cases.yaml` file contains the parsed test cases from the xlsx/csv input.

Example structure:
```yaml
metadata:
  generated_at: "ISO8601"
  source: "input-file-name"
suites:
  - id: "suite-id"
    name: "Suite name"
    module: "module-name"
    description: ""
    status: "active"   # or "skipped"
    reason: ""
    steps:
      - step_type: "action"  # action | assert | navigate
        description: "step description"
        element_hint: "dtk_main_menu"  # see element hint list
        menu_path: ["Item1", "Item2"]
```

## mappings.yaml Structure

The `mappings.yaml` file contains the mapping between test case steps and AT-SPI elements.

Example structure:
```yaml
metadata:
  generated_at: "ISO8601"
  at_tree_source: ""
mappings:
  - case_id: "suite-id"
    step_index: 0
    description: "step description"
    step_type: "action"
    element_hint: "click"
    menu_path: null
    element_ref: "ref-name"
    selector:
      name: "OK"
      role: "push button"
      name_pattern: null
    status: "mapped"  # mapped | unmapped | deprecated
    reason: ""
    fix_suggestion: ""
    note: ""
    context: ""
```

## Element Hint Mapping Requirements

The following table shows which element_hints need at-tree mapping vs not:

| element_hint | Needs at-tree selector? | Notes |
|---|---|---|
| keyboard_shortcut | No | Converts directly to `keyboard_press` action |
| input_text | No | Converts directly to `keyboard_type` action |
| assert_window | No | Uses description as name_pattern |
| scroll | No | No target element |
| dbus_call | No | Not a UI operation |
| screenshot | No | Captures screen |
| dtk_main_menu | No (uses menu_path) | Menu items found in at-tree under DTitlebarMainMenu |
| dtk_context_menu | Yes (target component) | Menu items are dynamic; only need selector for WHERE to right-click |
| click | Yes | Need selector for target element |
| hover | Yes | Need selector for target element |
| drag_drop | Yes | Need selector for drag source (and drop target) |
| titlebar | Yes | Need selector for titlebar element |
| tab_bar | Yes | Need selector for tab bar element |
| dialog | Yes | Need selector — see dialog mapping strategy below |
| toolbar | Yes | Need selector for toolbar element |
| sidebar | Yes | Need selector for sidebar element |
| tooltip | Yes | Need selector for tooltip element |
| dock | Yes | Need selector for dock element |
| assert_element | Yes | Need selector for element being asserted |
| assert_window_count | No | Just count windows |
| assert_not_exists | Yes | Need selector for element that should not exist |
| vlm_assert | No | Uses VLM model for assertion |
| visual_check | N/A | Skip — not automatable |
| physical_device | N/A | Skip — not automatable |
| cross_device | N/A | Skip — not automatable |

## LLM Configuration

The `parse` and `map` phases require an OpenAI-compatible LLM API.

Configuration is read from the `globalconfig.ini` `[vlm]` section with environment variable overrides:

- `YOUQU_AT_MODEL`: model name (default: `Qwen/Qwen2.5-VL-7B-Instruct`)
- `YOUQU_AT_BASE_URL`: API base URL (default: `http://localhost:8000/v1`)
- `VLM_BASE_URL`: fallback from `globalconfig.ini` if the env var is not set

Verify LLM availability before running the `parse` or `map` phases.
