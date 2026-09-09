---
name: at-suite-generator
description: >
  Generate runnable AT-SPI YAML test suites for a Linux desktop app from an
  xlsx/csv case doc or feature requirements. Use when the user asks to 生成
  AT用例 / 生成测试套件 / 把用例文档转成 suite for a desktop app.
  Triggers: AT用例生成, 生成AT用例, AT套件生成, suite生成, 元素驱动用例, 覆盖率生成用例.
version: "0.1.2"
license: MIT
author: Uniontech
---
# AT-Suite Generator — Element-Driven

## What this skill does

Generates executable AT-SPI `*.suite.yaml` suites for a Linux desktop app, guaranteed to cover 100% of the app's named interactive elements.

- **Input**: source code (for scan, required) + xlsx/csv case doc (optional; feature-driven if absent)
- **Output**: `*.suite.yaml` + `elements.yaml` + coverage report, ready for `youqu at run`

**Default path (standard)**: scan → slice → element manifest → generate → assemble + coverage gate → fill gaps → verify.

## Boundary

- **Owns**: end-to-end generation of AT-SPI suites from scan products + case docs.
- **Does NOT own**: the source scan internals (libclang parsing) — see `at-spi-coverage`. Fixing missing `setAccessibleName()` is `at-spi-completion`.
- **Scan products**: produced by `at-spi-coverage`'s `coverage_stats.py`, either run directly or via `pipeline_run.py --src`; or reused from a prior run via `--scan-dir`.
- **Output location**: all products go to `tests/at/` under the project root. Do not pick another directory — a self-chosen output dir breaks stage linkage and makes commits inconsistent.

## Default workflow

1. **Scan** — run `at-spi-coverage`'s `coverage_stats.py` → `coverage_scan/` (authoritative element set).
2. **Slice** — `scripts/pipeline_parse.py` splits the xlsx/csv by module + token budget (never a full file).
3. **Manifest** — `scripts/element_manifest.py` builds the authoritative element whitelist (the 100% denominator).
4. **Generate** — one sub-agent per slice maps cases → suites, picking `selector.name` only from the whitelist. Dispatch strictly by `scripts/gen_schedule.py` batches (≤3 parallel, serial between batches).
5. **Assemble + gate** — `scripts/pipeline_assemble.py` assembles suites; `scripts/cover.py` enforces the hard 100% gate.
6. **Fill gaps** — for uncovered elements, run a focused single sub-agent until 100% or manual exemption.
7. **Verify** — Gates 3/5/4 (static YAML checks, no desktop needed), runtime verify (needs DISPLAY; on headless machines wrap with `xvfb-run -a -s "-screen 0 1920x1080x24" dbus-run-session --`), coverage report.

Full stage details: `references/stage-1-prep.md`, `references/stage-2-generate.md`, `references/stage-3-assemble.md`, `references/stage-4-verify.md`. Sub-agent prompt: `templates/at-case-mapping-prompt-template.md`.

## Core rules (why)

- **Element-driven, not case-driven.** The coverage target is set at generation time, not measured after. This is why the whitelist is a hard constraint, not a suggestion.
- **100% gate is hard.** Every named interactive element (`pre_scan_ok.yaml` + `qml_ok.yaml`) must be referenced by a persistent `selector.name`. Gap elements (missing names / dynamic concatenation) are excluded from the denominator — they cannot be located by name.
- **Token-budget slicing.** Never emit a full `cases_raw.yaml`; a 2000+ case doc would blow the LLM context. Slice by module + `--budget` (16k default).
- **Sub-agent pool caps at 3 (HARD).** The workflow mandates running `scripts/gen_schedule.py` before spawning generation sub-agents and dispatching strictly by its emitted batches (≤3 per batch, serial between batches); the plan is the checkable artifact for the cap. Never fire all slices at once — more parallelism costs more tokens/time than it saves. Small input (≤2 slices) → single agent.
## Gotchas

- **`elements.yaml` ≠ source scan.** `elements.yaml` is assembled output; the scan products (`coverage_scan/`) are the authority for the 100% denominator. Do not let `elements.yaml` drive the gate.
- **Dynamic names invisible to static scan.** `setAccessibleName("Button_" + objName)` can't be resolved by libclang — those show as gaps even though they get names at runtime. They're allowed to be inconsistent (excluded from hard 100%).
- **QML without `Accessible.name`** appears as gap; only QML ok elements with `accessible_name` count toward the denominator.
- **`unreachable.yaml` is the only 100% exemption.** Conditionally-rendered / dynamic elements must be explicitly listed + reasoned, manually confirmed. Don't use it to bypass real coverage.
- **`name_source` ≠ runtime-locatable.** The manifest/coverage tag each element's `name_source` (`accessible` = `setAccessibleName()`/`Accessible.name` found in source; `object` = only `setObjectName()`). This is a static-scan FACT. It does NOT claim runtime locatability: how an element resolves at runtime depends on widget type (a QAction's objectName is a valid locator; a QWidget's is not) and the Qt/DTK build. Runtime locatability must be verified empirically (e.g. a live AT-SPI check), not assumed from the scan.
- **`pipeline_run.py` requires `--src` or `--scan-dir`.** No element universe → no denominator → the 100% gate is impossible. The script exits 1 without one; don't skip it.
- **Scan success ≠ exit code.** `coverage_stats.py` exits non-zero below its threshold (80%) or with no QML (pure-C++ project), even though products are written. `pipeline_run.py` judges scan success by `pre_scan_ok.yaml`/`qml_ok.yaml` existing, not the exit code.
- **Noise filter:** filenames containing `.` (e.g. `normal.pdf`) are treated as noise and excluded from coverage — SPI element names never contain `.`.
- **openpyxl required** for xlsx input (`pip install openpyxl`); missing it aborts the parse.
- **`.suite.yaml` uses `suites:` not `specs:`** (Gate 4 checks this).

## Scripts

| Script | Purpose | Run when |
|--------|---------|----------|
| `scripts/pipeline_run.py` | One-shot: scan → slice → manifest | Default entry point |
| `scripts/pipeline_parse.py` | Slice xlsx/csv by module + token budget; short module-slug filenames | After scan, with xlsx |
| `scripts/element_manifest.py` | Build whitelist from scan products | After scan |
| `scripts/gen_schedule.py` | Deterministic batch plan (≤3 per batch) for generation sub-agents | After manifest, before generation |
| `scripts/pipeline_assemble.py` | Validate + assemble suites + elements.yaml | After generation |
| `scripts/cover.py` | Enforce 100% coverage gate | After assemble |

## Banned

| Action | Reason |
|--------|--------|
| Generate a full `cases_raw.yaml` | Blows context at 2000+ cases |
| Sub-agent parallelism > 3 per batch | More cost than benefit; enforce via `gen_schedule.py` |
| Skip `gen_schedule.py` and fire all slices at once | Exceeds the hard cap-3; blows token/time budget |
| `selector.name` outside the whitelist | Fictional names fail at runtime |
| Skip the `cover.py` gate | 100% is a hard requirement |
| Modify `cover.py` to bypass the gate | Safety valve |
| `element_action` on menu items | Transient, not findable at runtime |

## Dependencies

| Dependency | When | Install |
|-----------|------|---------|
| Python >= 3.10 | always | system |
| `youqu` CLI | always | `pip install youqu-ai` |
| PyYAML | always | `pip install pyyaml` |
| openpyxl | xlsx mode | `pip install openpyxl` |
| `at-spi-coverage` skill | scan step | sibling skill (produces `coverage_scan/`) |
| libclang (binding + .so) | scan step | auto via `at-spi-coverage` bootstrap (sudo-free) |

## Errors & fallbacks

| Failure | Behavior |
|---------|----------|
| Scan fails (no libclang) | Stop, check deps |
| No xlsx | Fall back to feature-driven mode (still needs --src/--scan-dir for element universe) |
| No DISPLAY | Gates still run (static); for runtime verify wrap with `xvfb-run -a -s "-screen 0 1920x1080x24" dbus-run-session --` or skip and mark "needs desktop acceptance" |
| One slice generation fails | Skip that slice, mark `skipped` |
| Coverage gate FAIL | Gap-fill loop until 100% or manual exemption |
| Runtime verify fails | Mark suite `status: unstable` |

## Verification checklist

- [ ] All referenced `references/` / `templates/` / `scripts/` exist
- [ ] `coverage_scan/` products present before generation
- [ ] Slices preserve every case (integrity check passed)
- [ ] `selector.name` all within the whitelist
- [ ] `cover.py` reports 100% (or exemptions in `unreachable.yaml`)
- [ ] No full `cases_raw.yaml` emitted
