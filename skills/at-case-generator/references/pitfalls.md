# AT Case Generator Pitfalls

> **How to use this file**: Each pitfall describes a quality issue in the
> OUTPUT cases.yaml — what it looks like, why it's wrong, and what the
> correct output should be. These are NOT implementation instructions for
> a script. The AI reads descriptions, understands intent, and produces
> correct output through semantic reasoning. Pitfalls describe what to
> avoid in the output, not how to write code to detect it.

## 1. Compound steps not split

**Problem**: xlsx test steps often combine multiple operations in one
description (e.g., "打开终端，主菜单点击主题，切换深色" = 3 operations).

**Impact**: If not split, only the first operation matches a regex/action,
the rest are lost. The generated suite has incomplete operations.

**Solution**: The AI MUST split compound steps into individual CaseStep
entries during semantic mapping. When a description contains multiple
operations joined by commas or sequence words (然后, 并且), split each
into a separate step.

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

## 15. Precondition clauses not stripped

**Problem**: Test step descriptions often begin with transition clauses like
"弹出输入对话框后，" (after the input dialog pops up,) or "在密码输入框后面
有一个显示密码按钮，" (behind the password input field there is a show-password
button,). These are preconditions describing UI state, not actions to perform.

**Impact**: If not stripped, comma-splitting produces fragments like "对话框后"
which the input regex misclassifies as keyboard_type text="对话框后" (garbage).
Or "有一个显示密码按钮" becomes an element_action with a description-phrase
selector.

**Solution**: Before splitting, identify and strip leading precondition
clauses that describe UI state, not actions:
- "弹出XX后，" — dialog/window already appeared
- "在XX中，" — context setting (requires comma after 中 to avoid stripping
  "在对话框中输入XX" where 输入 is an action verb in the same clause)
- "重命名标题栏后，" / "登录远程服务器后，" — after-completion transitions
- "鼠标焦点在XX上，" — focus state precondition
- "此时，" / "再次，" — temporal transitions

After stripping, the remaining text contains only actionable operations.

## 16. Input keyword matching noun phrases

**Problem**: The pattern for detecting "输入" (input/type) action
matches "输入对话框" (input dialog), "输入框" (input box), "输入栏" (input
bar) — these are noun phrases containing "输入" as a component, not the
verb "to type".

**Impact**: "弹出输入对话框后" matches as keyboard_type with text="对话框后"
(garbage). "在搜索框中输入" produces text="搜索框中" (description, not data).

**Solution**: When a description contains "输入" (input), check whether it
is the verb "to type" or part of a noun phrase. If followed by 对话框, 框,
栏, 法, or 区域 — "输入" is part of a noun (e.g., "输入对话框" = input
dialog), not the verb. In that case, do not classify as keyboard_type.

For extracted keyboard_type text, ensure it is real input data:
- Strip prefixes like "框中输入：", "命令栏输入", leading colons
- Strip trailing punctuation
- If text ends with "后" or contains "后，" → precondition, skip
- If text matches "任意(长度)?(字符|内容|文字)" → use placeholder "test_input_123"
- If text is a generic field description ("服务器的名称", "名称、命令、快捷键")
  → skip (return None)
- Only keep text that looks like real input data

## 17. Static AT-SPI tree insufficient for element mapping

**Problem**: Mapping elements against a static AT-SPI tree dump (captured with
no dialogs or menus open) yields ~3.6% coverage — the tree only contains base
window and terminal elements. Dialog fields, preference panel controls, and
dynamically created UI are absent.

**Impact**: 77-93% of element_action/assert_element steps have no selector.
Tests "pass" vacuously because the executor silently skips steps with no
target.

**Solution**: Extract element names directly from test case descriptions and
write them as `selector: {name: "...", role: "..."}` for runtime AT-SPI
lookup. Do NOT rely on element_ref from a static tree dump. The executor
discovers elements dynamically at runtime by searching the live AT-SPI tree
for matching name+role.

Examples of correct extraction from descriptions:
- "点击重命名按钮" → selector: {name: "重命名", role: "button"}
- "勾选光标闪烁" → selector: {name: "光标闪烁", role: "check box"}
- "切换基础设置" → selector: {name: "基础设置", role: "list item"}
- Strip location qualifiers: "右上角的主菜单-远程管理" → name: "远程管理"
- Strip action verbs from element names: "点击关闭按钮" → name: "关闭"

## 18. Assertions without concrete targets

**Problem**: All assert_element steps have no selector — assertions are
no-ops that always pass vacuously.

**Impact**: Tests "pass" without actually verifying anything. 100% pass rate
is meaningless.

**Solution**: Extract assertion targets from descriptions:
- "查看对话框显示" → assert_element, selector: {role: "dialog"}
- "查看窗口显示" → assert_window
- "查看标题栏显示" → assert_element, selector: {name: "标题栏"}
- "查看密码显示" → assert_element, selector: {name: "密码"}
- Strip "显示" suffix: "对话框显示" → target "对话框"
- Use assert_window for app-level state, assert_element for specific UI

## 19. Context menu garbage menu_path values

**Problem**: "右键菜单显示" (right-click menu is displayed) is an assertion,
not a menu selection. But loose regex matching extracts "显示" as menu_path.
Similarly, "右键菜单" alone produces menu_path=["菜单"] (garbage).

**Impact**: dtk_context_menu with garbage menu_path navigates to
non-existent menu items, causing timeouts or silent failures.

**Solution**:
- Require explicit "选择" (select) or "点击" (click) verb after "右键菜单"
  to confirm it's a menu selection, not a display assertion
- If no selection verb → classify as right-click without selection:
  mouse_click with button=right, NOT dtk_context_menu
- For "右键菜单，选择XX" (comma between 菜单 and 选择): split by commas
  first, then extract the menu item from the "选择XX" fragment
- Validate extracted menu items against known item names; reject "菜单",
  "显示", empty strings, and description fragments

## 20. Description text used as keyboard_type input

**Problem**: keyboard_type text contains description fragments from the xlsx
description column, not actual data to type. Examples: "对话框后" (from
"弹出输入对话框后"), "任意长度字符" (meaning "any length characters"),
"搜索内容后" (from "输入搜索内容后").

**Impact**: The test types garbage text into input fields, which doesn't
match what the test case intended to verify.

**Solution**: Ensure keyboard_type text is real input data, not description
fragments. Apply semantic understanding:
- Strip description prefixes: "框中输入：", "命令栏输入", leading colons
- Strip trailing punctuation
- If text ends with "后" or contains "后，" → precondition, skip
- If text matches "任意(长度)?(字符|内容|文字)" → use placeholder "test_input_123"
- If text is a generic field description ("服务器的名称", "分组名称",
  "名称、命令、快捷键点击XX") → skip
- Only keep text that looks like real input data

## 21. Right-click without selection misclassified

**Problem**: Descriptions like "空白处右键菜单" (right-click at blank area)
or "不做其他任何操作，右键" (just right-click, no other operation) are
right-click actions without selecting a menu item. Mapping them to
dtk_context_menu produces menu_path=None.

**Impact**: dtk_context_menu with no menu_path is a no-op — the executor
opens the menu but has no item to select.

**Solution**: Differentiate:
- "右键" + "选择"/"点击" + specific item → dtk_context_menu with menu_path
- "右键" without selection → mouse_click with button=right
- "右键菜单显示" → assert_element (menu is displayed, not a click action)

## 22. "点击右键菜单栏XX" — "栏" included in menu item name

**Problem**: "菜单栏" (menu bar) contains "栏" which is part of the bar name,
not the menu item. The menu item name should not include "栏".

**Solution**: When extracting menu item names after "右键菜单", exclude "栏"
from the menu item — it belongs to "菜单栏" (menu bar), not the item name.

## 23. "点击鼠标中键" / "点击鼠标右键" misclassified as element click

**Problem**: "点击XX" captures "鼠标中键" or "鼠标右键" as element name and
creates `element_action` with selector `{"name": "鼠标中键", "role": "button"}`.
These are mouse actions, not element clicks.

**Solution**: If the target after "点击" matches mouse action keywords
(鼠标中键, 鼠标右键, 鼠标左键), emit `mouse_click` with appropriate button
(middle/right/left) instead of `element_action`.

## 24. "标签页点击鼠标右键" — no explicit "选择"/"点击" verb for menu item

**Problem**: "标签" + "右键" without an explicit "选择" or "点击" verb means
the user is right-clicking, not selecting a menu item. Classifying this as
dtk_context_menu produces a garbage menu_path.

**Solution**: Require explicit "选择" or "点击" verb to classify as
dtk_context_menu. When no verb is present after "右键", classify as
`mouse_click` with button=right.

## 25. Menu item captured with "右键" prefix and full-width quotes

**Problem**: Descriptions like `右键选择"关闭其它标签页"` produce menu_path
`['"关闭其它标签页"']` — full-width quotes (U+201C/U+201D) not stripped, and
"右键" prefix not removed from the item name.

**Solution**: After extracting the menu item, strip full-width quote
characters (U+201C, U+201D), remove "右键" prefix, and validate the result
against mouse keywords to reject "鼠标XX" false matches.

## 26. Comma-split fallback for right-click menu captures non-menu items

**Problem**: When splitting descriptions by commas to find menu selections,
"标签页点击鼠标右键" produces "鼠标右键" as a captured menu item — it's a
mouse action, not a menu item.

**Solution**: After comma-split extraction, validate the extracted menu item
against mouse keywords (鼠标, 中键, 左键, 标签栏, 菜单栏). Reject any item
containing these keywords.

## 27. Script-based mapping instead of AI understanding (CRITICAL)

**Problem**: The AI writes a Python script (`map_cases.py`, `parse_cases.py`,
etc.) with regex patterns to fill semantic fields, instead of reading each
case description and mapping through understanding.

**Impact**: Catastrophic. In a real-world deployment on deepin-terminal:
- 7% selector coverage (93% of element_action steps had no target)
- 0% assertion coverage (every assert_element had no selector)
- 0% execution success (no suite executed correctly)
- After 6 framework bug fixes, still only 46% execution

The old pipeline (AI generates each YAML case individually) achieved 30%+
baseline on the same project. Regex cannot handle:
- Ambiguous descriptions ("左边标题" → which element?)
- Compound actions needing semantic splitting
- Context-dependent element matching
- Distinguishing input verbs from noun phrases

**Fix**: DO NOT write scripts. Read each case description, understand the
user's intent, match against the AT-SPI tree through semantic reasoning,
and fill fields directly. Process in batches of ≤10 for large datasets.

See `root-cause-2025-07.md` for the full analysis.
