# AT Case Generator Pipeline Reference

CLI commands, input/output formats, and cases.yaml schema for the `youqu at`
pipeline. The pipeline is agent-driven: you (the agent executing this skill)
do semantic mapping in the session, not a CLI LLM call.

## Pipeline Overview

```
xlsx/csv ──[parse]──→ cases.yaml (raw) ──[you map]──→ cases.yaml (mapped)
                                                                   │
at-tree.yaml ──[tree-info]──→ compact_tree.txt ──────────────────────┘
                                                                   │
                             cases.yaml (mapped) ──[generate]──→ suite YAML
```

1. `youqu at parse` — format-only conversion (no LLM, no semantic mapping)
2. `youqu at tree-info` — compact tree for AI reading
3. You (the agent) — semantic mapping (fills action, element_ref, selector, etc.)
4. `youqu at generate` — pure rules-based generation with post-validation

## CLI Commands

### parse

Format-only conversion of xlsx/csv into raw cases.yaml. No LLM, no semantic
mapping. Produces CaseStep entries with step_type, description, element_hint,
menu_path — but action/element_ref/selector are null.

```bash
youqu at parse --input <path> --output <path>
```

Parameters:
- `--input`: required. xlsx or csv file path.
- `--output`: required. output cases.yaml path.

### tree-info

Generates a compact, human-readable text file from at-tree.yaml for AI
in-session reading. Each line: `nID | role: <role> | name: <name> | parent: <path>`.

```bash
youqu at tree-info --at-tree <path> --output <path>
```

Parameters:
- `--at-tree`: required. path to at-tree.yaml.
- `--output`: required. output compact_tree.txt path.

### map (deprecated)

```bash
youqu at map --at-tree <path> --cases <path> --output <path>  # DEPRECATED
```

Emits a DeprecationWarning. Use AI semantic mapping in session instead.

### generate

Generates suite YAML and elements.yaml from semantically mapped cases.yaml.

```bash
youqu at generate --cases <path> --output <dir> --app <app_name> [--at-tree <path>]
```

Parameters:
- `--cases`: required. path to mapped cases.yaml.
- `--output`: required. output directory.
- `--app`: recommended. application name for session_start.command and suite app.
- `--at-tree`: recommended. path to at-tree.yaml (for full elements.yaml extraction).

Post-validation: generate validates action names against executor HANDLERS
registry. Invalid actions are skipped with a warning.

## xlsx/csv Input Format

Supported column name aliases:

| Field | Aliases |
|-------|---------|
| id | 用例编号, ID, 编号, 序号 |
| title | 用例标题, 标题, 用例名称, 测试点 |
| module | 所属模块, 模块, 功能模块, 测试模块 |
| priority | 用例级别, 优先级, 级别, 重要程度 |
| precondition | 前置条件, 前提条件, 预置条件 |
| steps | 步骤, 测试步骤, 操作步骤, 用例步骤 |
| expected | 预期, 预期结果, 期望结果, 预期输出 |
| case_type | 用例类型, 类型, 测试类型 |

## cases.yaml Structure

```yaml
metadata:
  generated_at: "ISO8601"
  source: "input-file-name"
suites:
  - id: "suite-id"
    name: "Suite name"
    module: "module-name"
    description: ""
    status: "active"
    reason: ""
    steps:
      - step_type: "action"
        description: "step description"
        element_hint: "dtk_main_menu"
        menu_path: ["Item1", "Item2"]
        action: "dtk_main_menu"          # filled by AI
        key: null                         # keyboard combo
        text: null                        # input text / path / app name
        element_ref: null                 # at-tree node ID
        selector: null                    # {"name": ..., "role": ..., "name_pattern": ...}
        assertion: null                   # assert type
        needs_accessible_name: false
        accessible_name_suggestion: null
        value: null                       # dbus params dict, scroll amount, OCR text
```

### CaseStep Fields

| Field | Type | Description |
|-------|------|-------------|
| step_type | string | "action" \| "assert" \| "navigate" |
| description | string | Step description from xlsx |
| element_hint | string | Hint for element type |
| menu_path | list[string]/null | Menu navigation path |
| action | string/null | Action type (AI fills — see valid values below) |
| key | string/null | Keyboard combo (e.g., "ctrl+shift+a", "enter") |
| text | string/null | Text to type for keyboard_type; also used as path/app/value for assert actions |
| element_ref | string/null | AT-SPI element reference (at-tree node ID) |
| selector | dict/null | {"name": str, "role": str, "name_pattern": str(regex)} |
| assertion | string/null | Assert type for assert steps |
| needs_accessible_name | bool | True if element lacks accessible name |
| accessible_name_suggestion | string/null | Suggested name for app fix |
| value | any/null | Dict for dbus_call/dbus_get_property params; int for mouse_scroll |

See `suite-format.md` for the complete list of 31 action types and their
key fields. Action values must match executor HANDLERS exactly.
