# AT Case Generator Pipeline Reference

CLI commands, input/output formats, and cases.yaml schema for the `youqu at`
pipeline. The pipeline is agent-driven: you (the agent executing this skill)
do semantic mapping in the session, not a CLI LLM call.

## Pipeline Overview

```
xlsx/csv ──[parse]──→ cases_raw.yaml ──[AI normalize]──→ suite-cases.yaml
                                                              │
--- AT tree acquisition ---
    source ──[scan]──→ scanned_ok.yaml + element_gaps.yaml
    ⏸ STOP: ask user to run `youqu at record` and return with results
    scan + record ──[merge]──→ at-tree.yaml (v2.0, with transient_contexts)
---
                                                              │
at-tree.yaml ──[tree-info --format yaml]──→ at-tree-annotated.yaml (draft)
                                                          │
                                      AI annotates → at-tree-annotated.yaml (reviewed)
                                                          │
                                      [optional] youqu at split → per-module dirs
                                      [optional] youqu at docs → help manual chapters
                                      [optional] youqu at precandidate → pre-filtered candidates
                                                          │
                                      suite-cases.yaml + at-tree-annotated.yaml
                                                ──[AI map]──→ cases_mapped.yaml
                                                                     │
                                            cases_mapped.yaml ──[generate]──→ suite YAML
                                                                     │
                                            [optional] youqu at smoke → L2 module smoke
                                            [optional] youqu at verify → L3 single case
```

1. `youqu at parse` — format-only conversion (no LLM, no semantic mapping)
2. AT tree acquisition:
   - `youqu at scan` — source code scanning (headless, no desktop required)
   - `youqu at record` — event-driven recording (requires desktop + user interaction)
   - `youqu at merge` — layered merge of scan + record output
3. `youqu at tree-info --format yaml` — structured YAML for AI annotation (replaces compact_tree.txt)
4. AI annotation — fill `comment` field for each interactive element, human review
5. `youqu at validate --gate 1` — verify denoising + annotation completeness
6. AI normalization — group cases by GUI interface, add suite annotations, split compound steps
7. `youqu at validate --gate 2` — verify normalization + suite annotations
8. [optional] `youqu at split` — split cases_raw into per-module directories with at-tree subsets
9. [optional] `youqu at docs` — import help manual chapters for LLM-assisted grouping
10. [optional] `youqu at precandidate` — constraint-based selector pre-filtering
11. You (the agent) — semantic mapping (fills action, element_ref, selector, etc.)
12. `youqu at validate --gate 3` — verify mapping format + selector cross-references
13. `youqu at validate --gate 5` — semantic safety (description-as-input, missing precondition, empty selector)
14. `youqu at generate` — pure rules-based generation with post-validation
15. `youqu at validate --gate 4` — verify generation output
16. [optional] `youqu at smoke` — L2: one representative case per module (runtime addressability)
17. [optional] `youqu at verify` — L3: single case deep verification

## CLI Commands

### scan

Scans application source code for DTK/Qt widget classes using libclang.
Does NOT require a desktop environment — can run in CI/headless.

```bash
youqu at scan --src <dir> --app <id> [--output <dir>] [--include-dirs src widgets]
```

Output: `scanned_ok.yaml` (classes with names), `scanned_gaps.yaml` (missing names),
`element_gaps.yaml` (summary report).

### record

Event-driven AT-SPI recording. Captures focus/window/children-changed events
and input events (mouse/keyboard via X11 XRecord or Wayland evdev).

```bash
youqu at record --app <id> [--launch <cmd>] [--output <dir>] [--gui]
```

CLI controls: `s`+Enter = new segment, `q`+Enter or Ctrl+C = finish.

Output: `record_session.yaml` (event sequence + segments), `states/*.yaml` (subtree snapshots).

### merge

Layered merge: scan + record → at-tree.yaml (v2.0 with transient_contexts).

```bash
youqu at merge --record <dir> [--scan <dir>] [--app <id>] [--output <dir>]
```

Output: `at-tree.yaml` (v2.0: `tree` + `transient_contexts`), `element_gaps.yaml`.

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
youqu at validate --gate <1|2|3|4|5|all> [artifact paths...]
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
- **Gate 5** (Semantic Safety): `--cases-mapped <path>`.
  Checks: no description text as keyboard input, no keyboard_press without prior
  panel-opener action, no selector missing both name and accessible_id.

Exit code 0 = all gates passed; 1 = some gates failed.

### split

Splits `cases_raw.yaml` into per-module directories, each with its own
`cases.md`, `at-tree-subtree.yaml`, and `manifest.yaml` entry.

```bash
youqu at split --cases <cases_raw.yaml> --at-tree <at-tree-annotated.yaml> --output <dir> [--app <app_name>]
```

Parameters:
- `--cases`: required. Path to cases_raw.yaml.
- `--at-tree`: required. Path to at-tree-annotated.yaml (for subtree extraction).
- `--output`: required. Output directory for module directories.
- `--app`: optional. Application name (default: from cases source).

Output structure:
```
<output>/
├── manifest.yaml
├── modules/
│   ├── find/
│   │   ├── cases.md
│   │   ├── at-tree-subtree.yaml
│   │   └── suite-cases.yaml
│   ├── settings/
│   │   └── ...
```

### docs

Imports help manual chapters for an application, split by `##` headings
into per-module markdown files for LLM-assisted case grouping.

```bash
youqu at docs <app> [--output <dir>]
```

Parameters:
- `app`: required. App ID (e.g. `deepin-terminal`).
- `--output`: optional. Output directory (default: `docs`).

### precandidate

Pre-filters AT-SPI elements as candidate selectors for each case step using
weighted keyword matching. Produces `suite-cases.yaml` with embedded
candidates and `action_rules` auto-mapping (role → action, wait injection).

```bash
youqu at precandidate --cases <cases_raw> --at-tree <annotated> --output <suite-cases.yaml>
# or per-module:
youqu at precandidate --module-dir <module_dir>
```

Parameters:
- `--cases`: Path to cases_raw.yaml (alternative to --module-dir).
- `--at-tree`: Path to at-tree-annotated.yaml.
- `--output`: Output suite-cases.yaml path.
- `--module-dir`: Module directory (uses its cases.md + at-tree-subtree.yaml).

### smoke

L2 runtime verification: runs one representative case per module to verify
AT-SPI element addressability at runtime.

```bash
youqu at smoke --modules-dir <dir>           # all modules
youqu at smoke --module-dir <dir>            # single module
```

Parameters:
- `--modules-dir`: Directory containing all module subdirectories.
- `--module-dir`: Single module directory.
- `--skip-env-check`: Skip environment checks.

### verify

L3 deep verification: runs a single case and reports detailed results.

```bash
youqu at verify --suite <suite.yaml> [--spec-id <id>]
```

Parameters:
- `--suite`: required. Path to .suite.yaml file.
- `--spec-id`: optional. Specific spec ID to verify.
- `--skip-env-check`: Skip environment checks.

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
