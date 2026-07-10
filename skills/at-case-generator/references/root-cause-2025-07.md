# Root Cause: AT Pipeline YAML Quality Failure (2025-07)

## Symptom

`youqu at` pipeline tested on deepin-terminal: **0% suite execution success**.
Old pipeline (`youqu-case-generator` + `youqu run`): **30%+ success** on same project.

## Data Flow

```
xlsx → youqu at parse → cases_raw.yaml (format-only, no semantics)
                                    ↓
              [Step 3: AI semantic mapping — THE KEY STEP]
                                    ↓
                    cases.yaml (action/selector/items filled)
                                    ↓
              youqu at generate → suite.suite.yaml + elements.yaml
                                    ↓
              youqu at run → AtSuiteExecutor (src/at/executor/)
```

## Root Cause: Three Compounding Factors

### Factor 1 — Skill did not explicitly ban script-based mapping

SKILL.md Step 3 said:
> "This is NOT a CLI command — the AI does this in-session."

This prohibits a framework LLM call (`youqu at map`), but does NOT prohibit the AI
from writing a Python script (`map_cases.py` / `parse_cases.py`) to do the mapping
via regex. "In-session" was ambiguous — the AI interpreted it as "within this
session, I'll write code to do it" rather than "I will use my own understanding
to fill each field manually."

**Evidence**: The AI created `parse_cases.py` (657 lines) and `map_cases.py`
(1220 lines) as regex-based mapping scripts. After v1 achieved only 7% selector
coverage, the AI expanded to v2 (1220 lines) — still regex, not understanding.

### Factor 2 — Skill rules written as algorithm spec, not understanding guide

Step 3's rules read like an algorithm specification:

| Section | What it looks like | How AI interprets it |
|---------|-------------------|---------------------|
| "Compound Step Splitting" 3 sub-steps | Tokenization pseudocode | "Implement a splitter" |
| "Universal Detection Rules" table | If-else rule engine | "Build a classifier" |
| "Precondition Patterns" regex list | `PRECONDITION_PATTERNS = [...]` | "Copy these regexes" |
| "Input Text Cleaning" 6-step pipeline | Data sanitization spec | "Write a cleaning function" |
| "Context Menu Classification" tree | State machine | "Implement a state machine" |

The rules **describe what to do** at algorithmic precision, making script
implementation the natural response. They should instead **describe what to
understand** — semantic cues and reasoning hints, not exact regex patterns.

### Factor 3 — No batch processing guidance for large datasets

The test project had ~200 cases across 22 modules. With no batching guidance,
the AI faced a choice:

- Read each case description + tree → fill fields through understanding (slow, repetitive)
- Write a script to process all cases at once (fast, automated)

Without explicit "process in batches of ≤10" guidance (which
`deepin-testcase-generator` has), the AI defaulted to automation.

### Missing Anti-Pattern Warning

`deepin-testcase-generator` explicitly labels regex-based mapping as its #1 pitfall:

> "Keyword matching produces trivial passes. Regex-based generation creates cases
> that start the app, wait, and exit — they 'pass' without testing anything. LLM
> generation understands the case intent and produces real operations. This is
> the single most important thing to get right."

`at-case-generator` had no equivalent warning. The AI had no signal that
script-based mapping was a known failure mode.

## Quantified Impact

| Metric | Script mapping (map_cases.py v2) | AI understanding (old pipeline) |
|--------|----------------------------------|----------------------------------|
| Selector coverage | ~7% of steps had selectors | ~90%+ via ref to elements.yaml |
| Assert with selector | 0% — all assertions vacuous | Assertions had real targets |
| elements.yaml quality | 599 lines, keys are raw Chinese description text | 378 lines, semantic ref keys |
| Execution success | 0% (initial), 46% after 6 framework bug fixes | 30%+ baseline |

## Secondary Finding: Wrong Execution Path

The test session ran suites via `python -m src.yaml_test.suite` (SuiteExecutor
from `src/yaml_test/suite/`), NOT via `youqu at run` (AtSuiteExecutor from
`src/at/executor/`). This caused 5 framework bugs in yaml_test that are
irrelevant to the AT pipeline:

1. wait unit mismatch (3000ms → 3000s)
2. by_alias serialization mismatch
3. ElementNotFound not caught (extends BaseException)
4. SuiteExecutor doesn't load elements.yaml
5. __main__.py doesn't pass suite_path

Correct command: `youqu at run --testdir tests/at/yaml_out [--suite NAME]`

## Fix

SKILL.md changes (see commit diff):

1. **Explicit ban** on script-based mapping in Step 3
2. **Anti-pattern warning** with quantified failure data from this incident
3. **Batch processing guidance** for large case sets (≤10 per batch)
4. **Restructure rules** from algorithm-spec to understanding-guide
5. **Execution path clarification**: `youqu at run`, not `python -m src.yaml_test.suite`
