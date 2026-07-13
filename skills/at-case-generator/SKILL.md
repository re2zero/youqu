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
not a regex script, not an external API request. **You (the agent reading
this) are the AI.** Framework provides data tools; you provide understanding.

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

**You (the agent executing this skill) do the mapping.** No external API
calls, no scripts, no intermediate files. Read each case description,
understand the intent, fill semantic fields directly.

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

**Element Target Priority** (executor checks in this order):
1. **`selector`** — runtime AT-SPI lookup by name/role/name_pattern. Preferred.
2. **`ref`** — at-tree node ID lookup in elements.yaml. Fallback when selector
   is unavailable (e.g., element has no accessible name).
3. **`x`/`y`** — coordinate-based click. Last resort when no AT-SPI metadata.

Both `selector` and `ref` may appear in the same step; the executor uses
`selector` first, falling back to `ref` if `selector` is null.

**Every `assert_element` MUST have a concrete `selector`** — an assertion
without a target is a vacuous no-op.

**Every `keyboard_type` text must be real input data** — not description
fragments. If text is "任意长度字符" → use placeholder "test_input_123".
If text contains "后" → it's a precondition, skip.

See `references/pitfalls.md` for documented edge cases and their correct
handling. Review pitfalls before starting Step 3 and verify
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
| `youqu at dump dtk` | type, --app, --src | --output |
| `youqu at parse` | --input, --output | — |
| `youqu at tree-info` | --at-tree, --output | — |
| `youqu at generate` | --cases, --output | --app, --at-tree, --assert-gate |
| `youqu at run` | — | --suite, --testdir, -k, --spec-ids, --tags |

## Reference Files

| File | Purpose |
|------|---------|
| `references/pipeline-reference.md` | CLI commands, input/output formats, cases.yaml schema |
| `references/suite-format.md` | Generated suite YAML structure, action fields, elements.yaml, action types |
| `references/pitfalls.md` | 18 documented edge cases — review before Step 3, verify after |
