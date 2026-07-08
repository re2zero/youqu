---
name: at-case-generator
version: "0.1.0"
description: >
  Generate AT-SPI test suites from xlsx/csv test case documents using the
  `youqu at` CLI pipeline (parse → map → generate). Produces executable
  suite YAML + elements.yaml for `youqu at run`. Use whenever: AT用例生成,
  at-case generation, youqu at parse, youqu at map, youqu at generate,
  AT suite generation, AT-SPI suite YAML, at-tree用例, 桌面应用AT测试,
  AT自动化用例.
---

# AT Case Generator

Generate executable AT-SPI test suites from xlsx/csv test case documents using the
`youqu at` CLI pipeline (parse → map → generate). The pipeline uses an LLM to
understand test intent and map steps to AT-SPI elements from a tree dump.
Output is executable by `youqu at run`.

## Two Operating Modes

- **xlsx/csv-driven** (standard): Input is xlsx/csv with columns (id, title,
  module, steps, expected, etc.) → parse → map → generate → suite YAML.
- **Requirement-driven** (feature): Input is PR/issue/requirement text → agent
  writes cases.yaml directly (skip parse) → map → generate → suite YAML.

## Execution Steps

### Step 1: Pre-flight Checks

Verify prerequisites before running the pipeline:

- Verify `youqu` CLI is installed: `youqu --version`
- Verify LLM API is reachable (parse/map need it): check `YOUQU_AT_BASE_URL`
  env var (default: `http://localhost:8000/v1`)
- Verify xlsx/csv input exists and columns are readable

Supported xlsx/csv column aliases:
- `id`: 用例编号, ID, 编号, 序号
- `title`: 用例标题, 标题, 用例名称, 测试点
- `module`: 所属模块, 模块, 功能模块, 测试模块
- `priority`: 用例级别, 优先级, 级别, 重要程度
- `precondition`: 前置条件, 前提条件, 预置条件
- `steps`: 步骤, 测试步骤, 操作步骤, 用例步骤
- `expected`: 预期, 预期结果, 期望结果, 预期输出
- `case_type`: 用例类型, 类型, 测试类型

### Step 2: Acquire at-tree.yaml (if stale or missing)

Check if `at-tree.yaml` exists and is fresh (check `metadata.generated_at`).

If stale or missing, re-run:
```bash
youqu at dump dtk <app_name> --src <source_dir> --output <output_dir>
```

Note: This step requires the target app running on a desktop environment.

Validate output: read `metadata.generated_at` from the produced `at-tree.yaml`.

### Step 3: Parse Input → cases.yaml

Command:
```bash
youqu at parse --input <xlsx_or_csv_path> --output <cases_yaml_path> [--at-tree <at_tree_path>]
```

Verify output: `cases.yaml` should contain `suites` array with `steps`.

If parse fails with schema validation error → check LLM response quality, try
different model.

### Step 4: Map cases.yaml → mappings.yaml

Command:
```bash
youqu at map --at-tree <at_tree_path> --cases <cases_yaml_path> --output <mappings_yaml_path>
```

Verify output: check for unmapped entries (`status=unmapped`).

Unmapped entries → review `fix_suggestion`, may need to update at-tree or
adjust element hints.

### Step 5: Generate Suite YAML

Command:
```bash
youqu at generate --cases <cases_yaml_path> --mappings <mappings_yaml_path> --output <output_dir>
```

Verify output: check that `output_dir` contains `elements.yaml` and module
subdirectories with suite files.

If empty output → check `cases.yaml` for skipped suites.

### Step 6: Validate Output

Check the following:

- `elements.yaml` exists and has entries
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
   - Executable suite YAML in <output_dir>/<module>/ directory
   - elements.yaml in <output_dir>/ with all element selectors
   - Suite files with setup (session_start), cases (steps + assert_steps), teardown (session_stop)
   - All suites use "suites:" field (NOT "specs:")
   - Skipped cases from input: status=skipped with reason in suite

3. REQUIRED TOOLS: read, write, bash

4. MUST DO:
   - Run the full pipeline: parse → map → generate
   - Verify at-tree.yaml freshness before map phase
   - Check LLM API availability before parse/map
   - Verify each phase output before proceeding to next
   - Use exact CLI parameters (see CLI Quick Reference below)
   - Check for unmapped elements in mappings.yaml and report them
   - Ensure session_start.command is the app launch path
   - Ensure wait values are in milliseconds
   - Use "suites:" in suite YAML (NOT "specs:")
   - Read references/pipeline-reference.md for CLI parameters and formats
   - Read references/suite-format.md for output format details
   - Read references/pitfalls.md for common issues

5. MUST NOT DO:
   - Modify youqu framework source code
   - Invent AT-SPI element names without at-tree.yaml evidence
   - Skip the map phase (unmapped elements cause runtime failures)
   - Use "specs:" instead of "suites:" in suite YAML
   - Hardcode absolute paths

6. CONTEXT:
   - Pipeline overview: @references/pipeline-reference.md
   - Output format: @references/suite-format.md
   - Common issues: @references/pitfalls.md
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

Reference `@references/pitfalls.md`. Top 5 critical issues:

1. **at-tree.yaml staleness** — re-dump when UI changes; check `metadata.generated_at`.
2. **LLM API unavailable** — verify before parse/map; check `YOUQU_AT_BASE_URL`.
3. **suites: vs specs: spelling** — must be `suites:` in suite YAML, not `specs:`.
4. **session_start command ≠ AT-SPI name** — command is the app launch path, not the AT-SPI registered name.
5. **wait values in milliseconds** — AT suite `wait` values are in milliseconds (not seconds like standard YAML).

## Reference Files

| File | Purpose |
|------|---------|
| `@references/pipeline-reference.md` | CLI commands, input/output formats, LLM config |
| `@references/suite-format.md` | Generated suite YAML structure, action types, elements.yaml |
| `@references/pitfalls.md` | Common pipeline failures and solutions |
