## 1. at-tree.yaml is stale

**Problem**: UI changed after at-tree was generated; elements no longer match.

**Impact**: map phase produces unmapped elements, generate produces incomplete selectors.

**Solution**: Re-run `youqu at dump` whenever the app's UI changes; check metadata.generated_at.

## 2. LLM API unavailable

**Problem**: parse and map phases call an OpenAI-compatible LLM; if the API server is down or unreachable, both phases fail.

**Impact**: parse exits with "Error calling LLM API" or empty response; no cases.yaml produced.

**Solution**: Before running parse/map, verify the API is reachable. Check env vars: YOUQU_AT_BASE_URL (default: http://localhost:8000/v1), YOUQU_AT_MODEL.

## 3. Parse output fails schema validation

**Problem**: LLM returns JSON that doesn't match the expected cases.yaml schema (missing fields, wrong types, invalid enum values).

**Impact**: parse exits with "LLM output failed schema validation".

**Solution**: Check LLM response quality — try a different model, increase max_tokens, or adjust input data format. Ensure xlsx columns match supported aliases.

## 4. Map produces unmapped elements

**Problem**: Some steps cannot be matched to any AT-SPI element in at-tree.yaml; their mapping status is "unmapped".

**Impact**: Those steps get no selector in the generated suite; they may fail at runtime but generate does NOT crash.

**Solution**: Check unmapped entries in mappings.yaml (status=unmapped). Review fix_suggestion. May need to update at-tree.yaml or adjust element hints in cases.yaml.

## 5. Generate produces empty output

**Problem**: All suites in cases.yaml are skipped (status=skipped), or all steps have visual_check/physical_device/cross_device hints (which are excluded).

**Impact**: Output directory has elements.yaml but no module subdirectories or suite files.

**Solution**: Check cases.yaml for suite status and step element_hint values. Ensure some suites are active and steps use mappable hints (click, dialog, toolbar, etc.).

## 6. suites: vs specs: field name

**Problem**: The suite config YAML uses `suites:` as the field name for test cases; writing `specs:` instead will cause parsing errors at execution time.

**Impact**: `youqu at run` fails to load the suite file.

**Solution**: Always use `suites:` in the YAML output. Do not write `specs:`.

## 7. session_start command is not AT-SPI name

**Problem**: The `session_start` step's `command` field is the app launch path (e.g., "deepin-music"), not the AT-SPI registered name. The AT-SPI name is configured separately.

**Impact**: Using the wrong value in command causes the app to fail to launch.

**Solution**: Set command to the app's executable name or path. The AT-SPI registered name comes from the suite config's `app` field.

## 8. xlsx column names not recognized

**Problem**: The input xlsx/csv uses column names that don't match any supported aliases (e.g., "操作" instead of "步骤").

**Impact**: Those columns are read as empty; cases have missing data.

**Solution**: Ensure column names match the supported aliases. Supported name sets:
  - Steps: 步骤, 测试步骤, 操作步骤, 用例步骤
  - Expected: 预期, 预期结果, 期望结果, 预期输出
  - Module: 所属模块, 模块, 功能模块, 测试模块
  - ID: 用例编号, ID, 编号, 序号
  - Title: 用例标题, 标题, 用例名称, 测试点
  - Priority: 用例级别, 优先级, 级别, 重要程度
  - Precondition: 前置条件, 前提条件, 预置条件
  - Case type: 用例类型, 类型, 测试类型

## 9. dtk_context_menu menu_path must contain complete menu item names

**Problem**: menu_path values must contain the **complete** menu item name (e.g., `["设置"]`, `["远程管理"]`, `["横向分屏"]`), NOT truncated fragments (e.g., `["置"]`, `["理"]`, `["屏"]`).

**Impact**: The executor cannot navigate the context menu correctly; menu selection fails.

**Solution**: This happens when regex-based extraction is used instead of LLM semantic understanding. If the agent is performing parse manually (without LLM API), it must verify that every menu_path entry is a complete, meaningful menu item name extracted from the step description.

- Example of correct extraction: description="右键菜单选择设置" → menu_path=["设置"]
- Example of broken extraction: description="右键/菜单栏选择设置" → menu_path=["置"] (truncated)

## 10. Dialog name="" mapping strategy

**Problem**: In at-tree.yaml, dialog nodes often have `name=""` (empty). This is a known DTK6/Qt6 limitation — objectName is not exposed via AT-SPI attributes.

**Impact**: The map phase cannot match dialog steps to at-tree nodes using the dialog's name.

**Solution**: Use child panel names to reverse-lookup the dialog. Common patterns:
  - Child panel named `CustomCommandOptDlg` → "自定义命令" dialog
  - Child panel named `CustomThemeSettingDialog` → "自定义主题" dialog
  - Child panel named `TabRenameDlg` → "重命名标签" dialog
  - Child panel named `GroupConfigOptDlg` → "服务器分组配置" dialog
  - Child panel named `ServerConfigOptDlg` → "服务器配置" dialog
  - Child panel named `SearchBar` or `PageSearchBar` → "搜索" dialog/bar

The LLM (or agent acting as LLM) should use these child panel class names as the selector.name for dialog mapping.

## 11. DTK button names — spacing varies by character translation

**Problem**: DTK dialog buttons may have AT-SPI names with inter-character spacing, but this is **inconsistent** — it depends on DTK's character translation behavior:
- Some buttons have a regular space (0x20): `"取 消"`, `"添 加"`
- Some buttons have a non-breaking space (U+00A0): `"取\xa0消"`, `"添\xa0加"`
- Some buttons have no space at all: `"继续"`, `"高级选项"`, `"删除服务器"`

**Impact**: The map phase selector.name does not match the actual AT-SPI name; mapping fails.

**Solution**: The map phase selector.name MUST match whatever is in at-tree.yaml exactly — including spaces, non-breaking spaces, or lack thereof. Do not assume a button name has or does not have spaces. Always copy the name from at-tree.yaml, not from the visible UI text.
