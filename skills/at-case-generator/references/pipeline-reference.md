# AT Case Generator Pipeline Reference

CLI commands, input/output formats, and cases.yaml schema for the `youqu at`
pipeline. The pipeline is agent-driven: you (the agent executing this skill)
do semantic mapping in the session, not a CLI LLM call.

## Pipeline Overview

```
xlsx/csv ──[parse]──→ cases_raw.yaml ──[AI normalize]──→ suite-cases.yaml
                                                              │
at-tree.yaml ──[tree-info --format yaml]──→ at-tree-annotated.yaml (draft)
                                                        │
                                    AI annotates → at-tree-annotated.yaml (reviewed)
                                                        │
                                    suite-cases.yaml + at-tree-annotated.yaml
                                              ──[AI map]──→ cases_mapped.yaml
                                                                   │
                                          cases_mapped.yaml ──[generate]──→ suite YAML
```

1. `youqu at parse` — format-only conversion (no LLM, no semantic mapping)
2. `youqu at dump` — AT-SPI tree dump with built-in denoise filtering + element_gaps.yaml
3. `youqu at tree-info --format yaml` — structured YAML for AI annotation (replaces compact_tree.txt)
4. AI annotation — fill `comment` field for each interactive element, human review
5. `youqu at validate --gate 1` — verify denoising + annotation completeness
6. AI normalization — group cases by GUI interface, add suite annotations, split compound steps
7. `youqu at validate --gate 2` — verify normalization + suite annotations
8. You (the agent) — semantic mapping (fills action, element_ref, selector, etc.)
9. `youqu at validate --gate 3` — verify mapping format + selector cross-references
10. `youqu at generate` — pure rules-based generation with post-validation
11. `youqu at validate --gate 4` — verify generation output

## CLI Commands

### parse

Format-only conversion of xlsx/csv into raw cases.yaml. No LLM, no semantic
mapping. Produces CaseStep entries with step_type, description, element_hint,
items — but action/element_ref/selector are null. The parser classifies
step_type by keyword heuristic (verification keywords: 检查, 查看, 验证,
确认, 是否, 应该, 符合, 出现, 消失, 正确, 可见 → "assert") and appends
the xlsx "expected" column as assert steps.

```bash
youqu at parse --input <path> --output <path>
```

Parameters:
- `--input`: required. xlsx or csv file path.
- `--output`: required. output cases.yaml path.

### tree-info

Generates a structured YAML file from at-tree.yaml for AI in-session annotation.
Output includes `comment`, `annotation_status`, `classification` fields for each node.
Replaces the old flat `compact_tree.txt` format.

```bash
youqu at tree-info --at-tree <path> --output <path> [--format yaml|text]
```

Parameters:
- `--at-tree`: required. path to at-tree.yaml.
- `--output`: required. output path (default format: yaml).
- `--format`: optional. `yaml` (default, structured YAML for annotation) or `text` (legacy flat format).

YAML output fields per node: `id`, `role`, `name`, `object_name`, `accessible_id`,
`classification`, `comment`, `annotation_status`, `children`.

### map (deprecated)

```bash
youqu at map --at-tree <path> --cases <path> --output <path>  # DEPRECATED
```

Emits a DeprecationWarning. Use AI semantic mapping in session instead.

### validate

Runs programmatic verification gates on AT pipeline artifacts. No LLM.

```bash
youqu at validate --gate <1|2|3|4|all> [artifact paths...]
```

Gates:
- **Gate 1** (Denoising & Annotation): `--at-tree-annotated <path> --element-gaps <path>`.
  Checks: no noise names (Form_XXX/numeric), every interactive element has `comment`
  in `GUI位置: ... | 功能: ...` format, `annotation_status` set.
- **Gate 2** (Normalization & Suite Annotation): `--suite-cases <path> --at-tree-annotated <path>`.
  Checks: non-GUI separated, every active case has assert steps, every suite has
  4-field annotation, `AT元素引用` entries exist in annotated tree.
- **Gate 3** (Mapping Completeness & Format): `--cases-mapped <path> --at-tree-annotated <path>`.
  Checks: format example exists in header, selectors cross-reference annotated tree,
  no noise selectors, valid action values.
- **Gate 4** (Generation): `--generate-output <path>`.
  Checks: suite files exist, no noise selectors, no Form_DMainWindow generic assertions.

Exit code 0 = all gates passed; 1 = some gates failed.

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
cases:
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
        items: ["Item1", "Item2"]
        action: "dtk_main_menu"          # filled by AI
        key: null                         # keyboard combo
        text: null                        # input text / path / app name
        element_ref: null                 # at-tree node ID
        selector: null                    # {"name": ..., "role": ..., "name_pattern": ...}
        assertion: null                   # assert type
        needs_accessible_name: false
        accessible_name_suggestion: null
        value: null                       # dbus params dict, scroll amount, OCR text
      - step_type: "action"
        description: "right-click context menu"
        element_hint: "dtk_context_menu"
        items: ["Copy"]
        action: "dtk_context_menu"
        selector: {"name": "SomeWidget"}  # right-click target (persistent AT-SPI element; menu items are transient)
        element_ref: null
        key: null
        text: null
        assertion: null
        needs_accessible_name: false
        accessible_name_suggestion: null
        value: null
```

### CaseStep Fields

| Field | Type | Description |
|-------|------|-------------|
| step_type | string | "action" \| "assert" \| "navigate" |
| description | string | Step description from xlsx |
| element_hint | string | Hint for element type |
| items | list[string]/null | Menu navigation path |
| action | string/null | Action type (AI fills — see valid values below) |
| key | string/null | Keyboard combo (e.g., "ctrl+shift+a", "enter") |
| text | string/null | Text to type for keyboard_type; also used as path/app/value for assert actions |
| command | string/null | Launch command for session_start (full command incl. file args, e.g. "deepin-reader ${TEST_FILES_DIR}/normal.pdf"); propagated to `command` in generated suite YAML |
| element_ref | string/null | AT-SPI element reference (at-tree node ID) |
| selector | dict/null | {"name": str, "role": str, "name_pattern": str(regex)} — for `assert_element`, only `name` is used in the dogtail search expression; `role` is metadata only |
| assertion | string/null | Assert type for assert steps |
| needs_accessible_name | bool | True if element lacks accessible name |
| accessible_name_suggestion | string/null | Suggested name for app fix |
| value | any/null | Dict for dbus_call/dbus_get_property params; int for mouse_scroll |

See `suite-format.md` for the complete list of action types and their
key fields. Action values must match executor HANDLERS exactly.
