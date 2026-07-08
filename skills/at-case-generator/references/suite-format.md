# AT Suite YAML Format

## Output File Structure

```
<output_dir>/
├── elements.yaml                         # shared element registry
└── <module>/
    ├── test_<suite_id>.yaml              # per-suite test steps
    └── <module>_suite.suite.yaml         # suite config with setup/teardown/suites
```

## Suite Config File

The `<module>_suite.suite.yaml` file contains the suite configuration with setup, teardown, and suites.

```yaml
name: "module_suite"
app: "app-name"
description: ""
module: "module-name"
tags: []
skip: null               # string reason if skipped, else null
fast_fail: false
env_check: []
setup:
  - action: session_start
    command: "app-name"   # launch path, NOT AT-SPI registered name
    wait: 3000
suites:                   # IMPORTANT: must be "suites:" NOT "specs:"
  - id: "suite_id_s0"
    name: ""
    description: ""
    tags: []
    skip: null
    steps:
      - action: element_action
        ref: "ok_button"
        do: "click"
        wait: 0
    assert_steps:         # case-level assertions
      - action: assert_element_exists
        ref: "ok_button"
    timeout: null
teardown:
  - action: session_stop
```

Note: `suites:` is the YAML alias — the file MUST use `suites:` not `specs:`.

## Suite Case Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | string | yes | Case identifier (format: suite_id_sN) |
| name | string | no | Case name |
| description | string | no | Description |
| tags | list[string] | no | Tags for filtering |
| skip | string/null | no | Skip reason (null = active) |
| steps | list[step] | yes | Action steps |
| assert_steps | list[step] | no | Assertion steps (case-level, run after steps) |
| timeout | int/null | no | Timeout in seconds |

## Step Fields

| Field | Type | Description |
|-------|------|-------------|
| action | string | Action type (see list below) |
| ref | string/null | Element reference name (lookup in elements.yaml) |
| selector | dict/null | Inline selector (name, role, name_pattern) |
| command | string/null | Command for session_start/dbus_call |
| wait | float/null | Wait time in ms (session_start default: 3000, others: 0) |
| do | string/null | Operation: click, hover, drag |
| x | int/null | X coordinate |
| y | int/null | Y coordinate |
| items | list[string]/null | Menu path items |
| path | string/null | File path (screenshot) |
| prompt | string/null | VLM prompt |
| evidence | string/null | Evidence file path |
| app | string/null | App name (assert_window_count) |
| expected | int/null | Expected count |
| name_pattern | string/null | Regex pattern for name matching |
| key | string/null | Key name (keyboard_press) |
| text | string/null | Text to type (keyboard_type) |
| value | any/null | Arbitrary value |

## Action Types

| Action | Key Fields | Description |
|--------|-----------|-------------|
| session_start | command, wait | Launch app (wait default 3000ms) |
| session_stop | — | Terminate app |
| dtk_main_menu | items | Navigate DTK main menu by keyboard |
| dtk_context_menu | items | Navigate DTK context menu by keyboard |
| element_action | ref, do | AT-SPI element operation (click/hover/drag) |
| keyboard_press | key | Press key (e.g. "Return", "ctrl+a") |
| keyboard_type | text | Type text string |
| mouse_scroll | amount | Scroll (negative=down, positive=up) |
| dbus_call | command | D-Bus method call |
| screenshot_save | path | Save screenshot |
| assert_vlm | prompt | VLM visual assertion |
| assert_window_exists | selector | Window exists |
| assert_element_exists | ref, selector | Element exists in AT-SPI tree |
| assert_window_count | app, expected | Window count matches |
| assert_element_not_exists | ref, selector | Element NOT in AT-SPI tree |

## elements.yaml

The `elements.yaml` file is the shared element registry.

```yaml
elements:
  ref_name:
    name: "OK"
    role: "push button"
    name_pattern: null
  another_ref:
    name: "File"
    role: "menu"
```

Format: flat dict under `elements:` key. Each entry maps ref name → selector dict (name/role/name_pattern, all optional).

## Differences from Standard YAML

| Aspect | Standard YAML (youqu-case-generator) | AT Suite (at-case-generator) |
|--------|--------------------------------------|------------------------------|
| Suite cases field | specs: | suites: |
| Menu actions | main_menu_comb, context_menu_comb | dtk_main_menu, dtk_context_menu |
| Assertions | Inline per step (step.assert) | Case-level assert_steps[] |
| Element registry | elements.yaml (app, vars, elements) | elements.yaml (elements only) |
| Setup wait | wait: 1.0 (seconds) | wait: 3000 (milliseconds) |

## Key Notes

- `suites:` field spelling: must be `suites:` in YAML output
- `session_start.command` is the app launch path, not the AT-SPI registered name
- `wait` values in AT suite are in **milliseconds** (not seconds like standard YAML)
- `assert_steps` are at the **case level**, not per-step
- Skipped suites (status=skipped in cases.yaml) are excluded from generate output
