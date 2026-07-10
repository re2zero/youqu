# AT Case Generator Pitfalls

## 1. Compound steps not split

**Problem**: xlsx test steps often combine multiple operations in one
description (e.g., "打开终端，主菜单点击主题，切换深色" = 3 operations).

**Impact**: If not split, only the first operation matches a regex/action,
the rest are lost. The generated suite has incomplete operations.

**Solution**: The AI MUST split compound steps into individual CaseStep
entries during semantic mapping. See SKILL.md "Compound Step Splitting" table.

## 2. Menu items using element_action instead of dtk_main_menu

**Problem**: Menu items appear in at-tree as `role: menu item` nodes.
The AI may map them to `element_action` (AT-SPI click).

**Impact**: Menu items are NOT visible/clickable in AT-SPI until the menu
is opened. `element_action` on a menu item fails at runtime.

**Solution**: Menu items MUST use `dtk_main_menu` (main menu) or
`dtk_context_menu` (right-click menu) with `items` field for keyboard
navigation. NEVER use `element_action` for menu items.

## 3. DTK menu does not use AT-SPI element click

**Problem**: DTK main menu (`DTitlebarMainMenu`) creates transient popup
menus not in the AT-SPI accessibility tree until opened.

**Impact**: `element_action` cannot find/click menu items. The executor
returns "element not found".

**Solution**: `dtk_main_menu` uses keyboard navigation (Alt → Down → Enter),
not AT-SPI element lookup. `dtk_context_menu` uses right-click → keyboard
navigation. Both use `items` field, not `ref`/`selector`.

## 4. keyboard_press (single) vs keyboard_hot_key (combo)

**Problem**: Using `keyboard_press` for key combinations (Ctrl+C) or
`keyboard_hot_key` for single keys (Enter).

**Impact**: `keyboard_press` handler only handles single keys.
`keyboard_hot_key` handler handles combinations with `+` separator.

**Solution**:
- Single key (Enter, Escape, F1, Tab) → `keyboard_press`, `key: "enter"`
- Key combination (Ctrl+C, Alt+Tab) → `keyboard_hot_key`, `key: "ctrl+c"`

## 5. dtk_context_menu missing right-click target coordinates

**Problem**: `dtk_context_menu` needs to know WHERE to right-click before
navigating the menu. Missing target → executor cannot open context menu.

**Impact**: Context menu never opens; menu navigation fails.

**Solution**: Provide either:
- `ref`/`selector` — AT-SPI element to right-click (executor resolves center
  coordinates)
- `x`/`y` — direct coordinates for fixed positions
Both need `items` for the menu path.

## 6. needs_accessible_name elements

**Problem**: Some AT-SPI elements lack accessible names (empty `name` field).
DTK6/Qt6 does not expose objectName via AT-SPI.

**Impact**: Steps requiring these elements cannot be reliably mapped.

**Solution**: Set `needs_accessible_name: true` and
`accessible_name_suggestion: "suggested name"`. The generate phase collects
these into `app-optimization.md` for future app source code fixes.

## 7. session_start.command must be app name

**Problem**: Using AT-SPI registered name or full path in `command` field.

**Impact**: App fails to launch.

**Solution**: `session_start.command` is the app's executable name (e.g.,
"deepin-terminal"), not the AT-SPI name or full path. Pass `--app` to
`youqu at generate` to set this.

## 8. suites: vs specs: field name

**Problem**: Writing `specs:` instead of `suites:` in suite config YAML.

**Impact**: `youqu at run` fails to load the suite file.

**Solution**: Always use `suites:` (the YAML alias). The pydantic model field
is `specs` with `alias="suites"` — YAML must use the alias.

## 9. at-tree.yaml is stale

**Problem**: UI changed after at-tree was generated; elements no longer match.

**Impact**: AI semantic mapping produces incorrect element_ref/selector.

**Solution**: Re-run `youqu at dump` whenever the app's UI changes. Check
`metadata.generated_at` for freshness.

## 10. xlsx column names not recognized

**Problem**: Input xlsx uses column names that don't match supported aliases.

**Impact**: Columns read as empty; cases have missing data.

**Solution**: Ensure column names match supported aliases (see
pipeline-reference.md).

## 11. at-tree simplification loses parent-child hierarchy

**Problem**: If compact tree drops parent path, the AI cannot distinguish
same-named elements under different parents.

**Impact**: AI maps to wrong element; executor clicks wrong component.

**Solution**: `youqu at tree-info` includes full parent path
(e.g., `parent: n5 > n6 > n7`). The AI uses this to disambiguate.

## 12. DTK button names — spacing varies

**Problem**: DTK dialog buttons may have AT-SPI names with inter-character
spacing (e.g., "添 加" not "添加"). Inconsistent across buttons.

**Impact**: selector.name does not match actual AT-SPI name.

**Solution**: Copy name from at-tree.yaml exactly (including spaces,
non-breaking spaces, or lack thereof). Do not assume from visible UI text.

## 13. Dialog name="" mapping

**Problem**: DTK6/Qt6 dialog nodes have `name=""` (objectName not exposed).

**Impact**: Cannot match dialog steps using dialog's name.

**Solution**: Use child panel class names to reverse-lookup dialogs.
Common patterns:
- `CustomCommandOptDlg` → "自定义命令" dialog
- `CustomThemeSettingDialog` → "自定义主题" dialog
- `TabRenameDlg` → "重命名标签" dialog

## 14. Invalid action names

**Problem**: AI outputs action names that don't match executor HANDLERS
(e.g., "assert_element_exists" instead of "assert_element").

**Impact**: `youqu at run` fails with "no handler for action" error.

**Solution**: Generate post-validates action names against HANDLERS registry.
Invalid actions are skipped with a warning. Always use exact names from the
Action Types table in suite-format.md (30 handlers).
