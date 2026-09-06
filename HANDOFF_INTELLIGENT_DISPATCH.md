# 接力提示词 — 智能分派（intelligent dispatch）功能收尾

> 供新会话继续使用。目标仓库：`/home/zero/work/research/youqu`。

## 背景与已完成工作

目标：让 AT 用例只需写 `selector.accessible_id`（源码 UI 的 QObjectName），引擎自动分派各种情况（普通控件点击、菜单项点击自动导航、断言），消灭 `dtk_dropdown_menu` 特判。

已完成（工作区未提交）：

1. **新建 `src/at/executor/intelligent.py`** —— 统一分派模块，含：
   - `classify_menu_type()`：按 popup accessible_id 段模式分类菜单类型（DropdownMenu→dropdown / Menu_N→main / QMenu→context）
   - `act_on_menu_item()`：菜单项点击自动导航（识别父菜单→找触发按钮点击→AtMenuNavigator 键盘导航选择，显示文本自动从关闭态节点 name 取）
   - `_find_menu_trigger()`：从 popup aid 共享段反推 DDropdownMenu 触发按钮
   - `is_menu_item()`：容错判断（roleName 非字符串返回 False）
   - `dispatch()`：统一入口，菜单项点击→返回 True（已处理）；普通控件→返回 False
2. **修改 `src/at/executor/handlers.py`**（未提交，+29 行）：
   - `handle_element_action` 接入智能分派：attrs 有 accessible_id 时调 dispatch，返回 True 则 return，否则回退传统守卫+点击
   - `handle_assert_element` / `handle_assert_not_exists` 增加 accessible_id 分支（用 `find_elements_by_accessible_id`，支持菜单项关闭态断言）
3. **新建 `tests/test_at_intelligent.py`**（未提交）

## 当前卡点（2 个测试失败）

`tests/test_at_intelligent.py` 的 `TestActOnMenuItem` 里 patch 路径错了：

```python
unittest.mock.patch("src.at.executor.intelligent.AtMenuNavigator", ...)
```

但 `act_on_menu_item` 里是 `from src.at.executor.menu_nav import AtMenuNavigator`（函数内局部 import），所以模块没有 `AtMenuNavigator` 属性。改为 patch `src.at.executor.menu_nav.AtMenuNavigator`。

## 剩余任务（按序）

1. 修上面 2 个测试的 patch 路径 → 15 单测全过
2. 跑全量：`python3 -m pytest -c pytest-tests.ini tests/ -q -k "at"`
3. 端到端验证（真实 deepin-editor，路径 `/home/zero/work/repo/github/deepin-editor`）：
   - suite `tests/at/yaml/test/test.suite.yaml` 现在用 `dtk_dropdown_menu`，改成智能分派写法：
     ```yaml
     - action: element_action
       selector:
         accessible_id: WindowsAction   # 直接写 objectName，引擎自动导航
       do: click
     ```
   - 跑 `youqu at run` 验证能切到 Windows（OCR 底栏确认）。注意：deepin-editor 是单实例，先 `pkill -9 -f deepin-editor`。teardown 应改回 session_stop 或保留应用验证后处理。
4. 同步安装包：cp 到 `~/.local/lib/python3.12/site-packages/youqu/src/at/executor/`（handlers.py + intelligent.py）
5. 提交（youqu 仓库 gitlab/main）：先 `git add src/at/executor/handlers.py src/at/executor/intelligent.py tests/test_at_intelligent.py`，commit message 说明 "intelligent accessible_id dispatch"，push
6. 可选：更新 `skills/at-mapping-rules/references/selector-guide.md` 的 §5.5，说明现在 `element_action` + accessible_id 可直接操作菜单项（引擎自动导航），`dtk_dropdown_menu` 降为歧义回退

## 关键环境事实（勿重踩坑）

- deepin-editor 是 Qt6/DTK6，**单实例**；启动需 `pkill -9 -f deepin-editor` 先清理
- **DTK DMenu 弹出后菜单项对 AT-SPI 完全不可见**（gi 查询不到）——所以菜单项点击必须"打开菜单+键盘导航"，智能分派正是封装这个
- 菜单项**关闭态**节点：accessible_id 后缀=objectName，name=显示文本（自动反查）
- DDropdownMenu 4 个触发按钮 aid 全同（PToolButton），用 `index` 消歧
- 4 个已提交 commit 均涉及 accessible_id 引擎支持（df20e47 / 900df1c / 48903cd / 1731bff），已在 gitlab/main 分支，勿重复
- 安装包与仓库需保持一致；`tests/test_at_executor.py` 的 handler 数量断言已更新为 33（新增 dtk_dropdown_menu），若再加 handler 需同步更新

## 验收标准

- 15 个智能分派单测全过
- 全量 AT 测试无新增失败（现有 579 过、1 挂；若 handler 数量断言不符需同步）
- deepin-editor 用 `element_action` + `accessible_id: WindowsAction` 能切到 Windows（OCR 确认）
- 安装包与仓库一致，提交已 push
