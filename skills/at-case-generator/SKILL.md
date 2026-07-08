---
name: at-case-generator
version: "0.1.0"
description: >
  Use when needing to generate AT-SPI test suites from xlsx/csv test case
  documents for a Linux desktop application. Triggers: AT用例生成,
  at-case generation, AT suite generation, AT-SPI suite YAML, at-tree用例,
  桌面应用AT测试, AT自动化用例, youqu at parse, youqu at map,
  youqu at generate.
---

# AT Case Generator

Orchestrate the `youqu at` CLI pipeline to convert xlsx/csv test case documents
into executable AT-SPI suite YAML. The pipeline uses an LLM to understand test
intent and map steps to AT-SPI elements from a tree dump. Output is executable
by `youqu at run`.

## When to Use

- You have xlsx/csv test case documents for a Linux desktop application
- You need executable AT-SPI test suites from those documents
- Input is a PR/issue/requirement and you want to generate cases directly

## When NOT to Use

- You need standard YAML test cases (use `youqu-case-generator` instead)
- You need to run existing AT suites (use `youqu at run` directly)
- You need to dump the AT-SPI tree only (use `youqu at dump` directly)

## Two Operating Modes

- **xlsx/csv-driven** (standard): Input is xlsx/csv with columns (id, title,
  module, steps, expected, etc.) → parse → map → generate → suite YAML.
- **Requirement-driven** (feature): Input is PR/issue/requirement text → agent
  writes cases.yaml directly (skip parse) → map → generate → suite YAML.

## Execution Steps

### Step 1: Pre-flight Checks

- `youqu --version` — CLI installed
- LLM API reachable (`YOUQU_AT_BASE_URL`, default `http://localhost:8000/v1`)
- xlsx/csv input exists, columns match supported aliases (see pipeline-reference.md)

### Step 2: Acquire at-tree.yaml

Check `metadata.generated_at` for freshness. Re-dump if stale:
```bash
youqu at dump dtk <app_name> --src <source_dir> --output <output_dir>
```
Requires desktop environment with target app running.

### Step 3: Parse → cases.yaml

```bash
youqu at parse --input <xlsx_or_csv> --output <cases_yaml> [--at-tree <at_tree>]
```
Verify: `cases.yaml` has `suites` array with `steps`.

### Step 4: Map → mappings.yaml

```bash
youqu at map --at-tree <at_tree> --cases <cases_yaml> --output <mappings_yaml>
```
Verify: check for `status: unmapped` entries → review `fix_suggestion`.

### Step 5: Generate Suite YAML

```bash
youqu at generate --cases <cases_yaml> --mappings <mappings_yaml> --output <output_dir>
```
Verify: `output_dir` has `elements.yaml` + module subdirectories with suite files.

### Step 6: Validate Output

- `elements.yaml` exists with entries
- Suite files use `suites:` (NOT `specs:`)
- `session_start.command` uses app launch path (NOT AT-SPI registered name)
- `wait` values are in **milliseconds** (not seconds)
- Optional: Run `youqu at run --suite <suite_file_path>` (requires desktop)

## Delegation Pattern

For multi-module generation, dispatch one sub-agent per batch in parallel.

**Sub-agent prompt template:**

```
1. TASK: Generate AT-SPI test suite for app "<app_name>" from input at <input_path>.
    Working directory: <project_root>. Output directory: <output_dir>.

2. EXPECTED OUTCOME:
    - Executable suite YAML in <output_dir>/<module>/
    - elements.yaml in <output_dir>/
    - Suite files: setup (session_start) → cases (steps + assert_steps) → teardown (session_stop)
    - Skipped input cases: status=skipped with reason

3. REQUIRED TOOLS: read, write, bash

4. MUST DO:
    - Run full pipeline: parse → map → generate, verifying each phase output
    - Check at-tree.yaml freshness and LLM API availability before starting
    - Report unmapped elements from mappings.yaml
    - Ensure: session_start.command = launch path, wait = milliseconds, suites: not specs:
    - Read references/ directory for CLI params, output format, and pitfalls

5. MUST NOT DO:
    - Modify youqu framework source code
    - Invent AT-SPI element names without at-tree.yaml evidence
    - Skip the map phase (unmapped elements cause runtime failures)
    - Use "specs:" instead of "suites:" or hardcode absolute paths
```

## CLI Quick Reference

| Command | Required Args | Optional Args |
|---------|--------------|---------------|
| `youqu at dump dtk` | type (positional), --app, --src | --output |
| `youqu at parse` | --input, --output | --at-tree |
| `youqu at map` | --at-tree, --cases, --output | — |
| `youqu at generate` | --cases, --mappings, --output | — |
| `youqu at run` | — | --suite, --testdir, -k, --spec-ids, --tags |

## Pitfalls

See references/pitfalls.md. Critical: at-tree staleness, LLM API unreachable,
`suites:` not `specs:`, command ≠ AT-SPI name, wait in milliseconds.

## Reference Files

| File | Purpose |
|------|---------|
| `references/pipeline-reference.md` | CLI commands, input/output formats, LLM config |
| `references/suite-format.md` | Generated suite YAML structure, action types, elements.yaml |
| `references/pitfalls.md` | Common pipeline failures and solutions |
