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

## LLM Configuration

The `parse` and `map` phases require an OpenAI-compatible LLM API.

Configuration is read from the `globalconfig.ini` `[vlm]` section with environment variable overrides:

- `YOUQU_AT_MODEL`: model name (default: `Qwen/Qwen2.5-VL-7B-Instruct`)
- `YOUQU_AT_BASE_URL`: API base URL (default: `http://localhost:8000/v1`)
- `VLM_BASE_URL`: fallback from `globalconfig.ini` if the env var is not set

Verify LLM availability before running the `parse` or `map` phases.
