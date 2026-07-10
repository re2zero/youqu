---
name: at-case-generator
version: "0.4.0"
description: >
  Use when generating AT-SPI test suites from xlsx/csv test case documents
  for a Linux desktop application. Triggers: AT用例生成, at-case generation,
  AT suite generation, AT-SPI suite YAML, at-tree用例, 桌面应用AT测试,
  AT自动化用例, youqu at parse, youqu at generate, youqu at tree-info.
---

# AT Case Generator

Convert xlsx/csv test case documents into executable AT-SPI suite YAML.
The AI does semantic mapping through understanding — not a CLI LLM call,
not a regex script. Framework provides data tools; AI provides understanding.

## When to Use

- xlsx/csv test case documents for a Linux desktop application
- Need executable AT-SPI test suites from those documents
- Input is a PR/issue/requirement and you want to generate cases directly

## When NOT to Use

- Standard YAML test cases → use `youqu-case-generator`
- Run existing AT suites → use `youqu at run`
- Dump AT-SPI tree only → use `youqu at dump`

## Pipeline

```
Step 1: Pre-flight checks
Step 2: Data preparation
    youqu at parse <xlsx> → cases.yaml (raw, format-only)
    youqu at tree-info <at-tree> → compact_tree.txt (for AI reading)
Step 3: AI semantic mapping (KEY STEP — AI does this through understanding)
    AI reads compact_tree.txt + raw cases.yaml
    AI fills action, element_ref, selector, items, key, text, assertion
    AI writes semantically mapped cases.yaml
Step 4: Generate + validate
    youqu at generate --cases <mapped> --output <dir> --app <app> --at-tree <tree>
    youqu at run --testdir <dir>  [NOT python -m src.yaml_test.suite]
```

`youqu at map` is **deprecated**. Mapping is done by the AI in Step 3.

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
`menu_path` filled; `action`, `element_ref`, `selector` are null. Format-only.

### 2b: Generate compact tree for AI reading

```bash
youqu at tree-info --at-tree <at_tree.yaml> --output <compact_tree.txt>
```

One line per AT-SPI node: `nID | role: <role> | name: <name> | parent: <path>`.
Typically 500-2000 lines. Contains full parent-child hierarchy.

### 2c: Acquire at-tree.yaml (if not present)

```bash
youqu at dump dtk <app_name> --src <source_dir> --output <output_dir>
```

Requires desktop environment with target app running.

## Step 3: AI Semantic Mapping (KEY STEP)

The AI reads the compact tree and raw cases.yaml, then fills semantic fields
for each step through **direct understanding** — not script-based pattern matching.

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
1. Read 10 case descriptions + relevant compact_tree.txt sections
2. Map all 10 through understanding
3. Append to cases.yaml
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

**Every `assert_element` MUST have a concrete `selector`** — an assertion
without a target is a vacuous no-op.

**Every `keyboard_type` text must be real input data** — not description
fragments. If text is "任意长度字符" → use placeholder "test_input_123".
If text contains "后" → it's a precondition, skip.

See `references/pitfalls.md` for 27 documented edge cases and their correct
handling. The AI should review pitfalls before starting Step 3 and verify
output against them after mapping.

### Writing the Mapped cases.yaml

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
      - step_type: "action"
        description: "主菜单点击主题，切换深色"
        action: "dtk_main_menu"
        items: ["主题", "深色"]
      - step_type: "assert"
        description: "验证主题已切换"
        action: "assert_window"
        assertion: "window_exists"
```

See `references/pipeline-reference.md` for full cases.yaml schema and
`references/suite-format.md` for all 30 action types and their fields.

## Step 4: Generate + Validate

### 4a: Generate

```bash
youqu at generate --cases <mapped_cases.yaml> --output <output_dir> \
  --app <app_name> --at-tree <at_tree.yaml>
```

Output: `elements.yaml`, `<module>/suite.suite.yaml`, `app-optimization.md`.

### 4b: Validate

**Structure checks**:
- Suite files use `suites:` (NOT `specs:`)
- `session_start.command` uses app launch command
- `wait` values are in **seconds** (float: 0, 1.0, 3.0)
- `dtk_main_menu` / `dtk_context_menu` for menu operations (NOT `element_action`)
- Steps from the same test case are in the same SuiteCase

**Quality checks**: Verify output against `references/pitfalls.md` — no empty
selectors, no garbage keyboard_type text, no precondition fragments as steps.

**Runtime validation** (requires desktop):
```bash
youqu at run --testdir <output_dir> [--suite <suite_file>]
```
**NOT** `python -m src.yaml_test.suite` — that is a different executor.
The AT pipeline uses `AtSuiteExecutor` in `src/at/executor/`.

## CLI Quick Reference

| Command | Required Args | Optional Args |
|---------|--------------|---------------|
| `youqu at dump dtk` | type, --app, --src | --output |
| `youqu at parse` | --input, --output | — |
| `youqu at tree-info` | --at-tree, --output | — |
| `youqu at generate` | --cases, --output | --app, --at-tree |
| `youqu at run` | — | --suite, --testdir, -k, --spec-ids, --tags |

## Reference Files

| File | Purpose |
|------|---------|
| `references/pipeline-reference.md` | CLI commands, input/output formats, cases.yaml schema, 30 action types |
| `references/suite-format.md` | Generated suite YAML structure, action fields, elements.yaml |
| `references/pitfalls.md` | 27 documented edge cases — review before Step 3, verify after |
| `references/root-cause-2025-07.md` | Root cause analysis of script-based mapping failure |
