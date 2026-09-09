# 用例编写规范（本技能的唯一权威）

> 来源：《AT用例自动化-质量分析与编写规范.md》v1.0。本文件是技能的蒸馏版本，如需完整背景见源文档。

## 1. 为什么需要规范

测试人员写中文 UI 步骤，AI 要据此生成 AT-SPI 自动化测试。现状 AI 常翻译错，原因三层：

1. **步骤文本不规范** — 前置空缺 40%、预期混入步骤 37%、标题无【模块】78%、无具体输入 55 处
2. **UI 名 ↔ AccessibleName 无桥** — AT-SPI `name` 来自 `setAccessibleName()`（如 `Button_SelectFile`），不是 objectName，测试人员看不到，需要 element-map.yaml 桥接
3. **语义不可自动化** — 颜色/光标/tooltip/系统环境/硬件/性能等在 AT-SPI 树上无状态，需标【人工】

## 2. 列级规范

| 列 | 规则 | 好 | 坏 |
|---|---|---|---|
| 用例标题 | 自动化用例 `【模块】功能_场景`；不可自动化用例 `【人工】功能_场景`（见 §7） | 【查找】向上查找_循环匹配 / 【人工】语音朗读_音频缺失 | 最小窗口-检查最小窗口680*510 |
| 前置条件 | 只写**状态**、可断言；构造不了标 [手工] | 已有 3 个日程；网络连接正常 | 1.首次打开日历管理页面 |
| 步骤 | 每行**一个动作** `<动词> <UI目标> <参数>`；禁止含断言词（完整清单见 §3.1） | 输入：武汉 | 2. 观察文本编辑区域的高亮状态（含断言词"观察"） |
| 预期 | 每行一个断言目标；禁止"操作正常/无异常" | 下方显示查找窗口 | 1. 操作正常 |

## 3. 解析关键词白名单

### 3.1 断言关键词（禁止写进步骤，写进预期列）

```
检查 / 确认 / 查看 / 验证 / 是否 / 应该 / 符合 / 出现 / 消失 / 正确 / 可见 / 观察 / 对比
```

命中 → 解析器判为断言，不生成操作。

> 与 `scripts/validate_cases.py` 的 `ASSERT_KEYWORDS` 保持一致（含 观察/对比）。

### 3.2 角色关键词（写步骤时带，AI 推断控件角色）

| AT-SPI 角色 | 中文关键词 | 英文关键词 |
|---|---|---|
| button | 按钮 | button, btn |
| check box | 复选, 勾选 | checkbox, check box |
| menu item | 菜单项 | menu item |
| menu | 菜单 | menu |
| text | 文本, 输入框 | text, input |
| entry | 输入, 编辑 | entry, edit |
| list | 列表 | list |
| tree | 树 | tree |
| combo box | 下拉, 选择器 | combo |
| tab | 标签 | tab |
| slider | 滑块 | slider |
| link | 链接 | link |

### 3.3 菜单关键词（决定主/右键菜单）

右键菜单：`右键 / 右击 / 右键菜单 / context menu / contextmenu / right-click / right click`
主菜单：`主菜单 / 标题栏菜单 / 标题栏 / menu bar / menubar / titlebar menu`
无关键词默认 fallback 右键菜单。

### 3.4 描述文本检测关键词（禁止出现在输入内容里）

```
显示 / 被清空 / 可以重新 / 正常 / 异常 / 检查 / 查看 / 应当 / 应该
```

### 3.5 操作动词（建议优先使用）

点击：点击/单击/双击/右键/左键/左键选中/长按
输入：输入/键入/粘贴
键鼠：按<键>/快捷键<组合>/回车/滚轮/拖拽
界面：打开/关闭/新建/删除/重命名/清空/展开/收起/切换/进入/退出/执行
状态：勾选/取消勾选/等待/选择/选中/等待<秒>

> 完整检测清单以 `scripts/validate_cases.py` 的 `ACTION_VERBS` 为准（含左键/进入/退出/选择/选中），本表是编写时的建议子集。


## 4. UI 目标引用

- 写控件**显示文本**：`点击"替换"按钮`，不要 `点击右上角的"替换"按钮`（必须带文本）
- 无文本控件写**从属容器+位置**：`点击查找弹窗底部的"全部替换"按钮`
- 菜单写**路径**：`右键-查找` / `主菜单-设置-高级设置`
- **禁止写代码标识**：`accessible_id=FindNext`、`点击 Search 元素`
  （例外：DDropdownMenu 下拉菜单项写**功能描述**，如 `切换行尾格式为 Windows`，
  由 element-map 填 `object_name`（如 WindowsAction）→ 生成技能映射为`selector.accessible_id`——本阶段仍以人读文本为准）

## 4.1 VLM 参考图断言（`vlm_assert` hint）

断言目标涉及**整界面视觉状态对比**（参考图 vs 实际截图），用 `vlm_assert` hint：

```yaml
- description: 对比参考图与实际界面是否一致
  element_hint: vlm_assert
  value: references/fm_open.png    # 参考图路径（相对 suite 目录）
  text: 窗口整体界面状态|strict    # 断言特征 | 判定模式
```

字段：

| 字段 | 说明 |
|---|---|
| `element_hint: vlm_assert` | 触发 `assert_vlm_reference` 动作 |
| `value` | 参考图路径（期望状态），相对 suite 目录或绝对路径 |
| `text` | 断言特征描述，`|` 后接判定模式（见下） |
| `ignore`（可选） | 可忽略的差异列表，如 `["时间戳", "进度条"]` |

判定模式（`text` 里 `|` 后的值）：

- `strict`（默认）：任何边框/颜色/高亮/透明度/布局差异 → FAIL，仅时间/进度数值变化可忽略
- `tolerant`：仅关注 `text` 指定的特征本身是否一致，其他区域差异可忽略

录制时可用 `youqu at record --reference references` 自动生成参考图（存到 `references/` 目录，按 segment 命名）。

## 5. 输入数据

- 必填具体 payload：`输入：123ASsdh周圣》?:%$%^&`
- 无具体值占位写死：`输入：test_input_001`
- 边界/超长给字符数：`输入：1000个字符'A'`

## 6. 状态/时序

- 时序拆独立步骤：`1. 输入关键词 2. 回车 3. 检查结果包含<文件名>`
- "过程中"标 `[时序敏感]`
- 等待必须有后续断言

## 7. 不可自动化用例标记

**判定**：断言目标属于以下任一类 → 该用例不可自动化，须标记：

| 类别（与 validate_cases.py 的 UNSUPPORTED_TARGETS 一致） | 示例 |
|---|---|
| 颜色/高亮/置灰 | 背景变模糊、语法高亮、按钮置灰 |
| 光标/选区形态 | 焦点聚焦、光标形态、选区形态 |
| tooltip/悬停 | Tip框、悬停 |
| 系统环境 | dock右键、休眠、锁屏、开机自启 |
| 外部硬件 | 触控板、触摸屏、麦克风、音频 |
| 文件/网络依赖 | U盘、光驱、smb、ftp、1G大文件 |
| 性能/资源 | 内存、冷热启动、长时间运行 |
| 跨应用/破坏性 | 关机、重启、强制退出 |

**标记规则**：`manual: true` 与标题前缀 `【人工】` **必须同时存在**（只标其一 → 违规）：

- 用例不可自动化 → yaml 置 `manual: true`，标题加前缀 `【人工】`
- 前置条件含无法自动构造的状态（U盘/网络/登录）→ 前置标 `[手工]`，且用例 `manual: true`
- 外部依赖类用例不再单用 `【外部】`，统一 `manual: true` + `【人工】`（reason 注明类别）

## 8. 界面元素映射表（必填）

| id_name | 开发人员 | 至少一个必填 | AccessibleName（setAccessibleName 的值），运行时是 AT-SPI 树的 `name`，selector 用 `selector.name` |
| object_name | 开发人员 | 至少一个必填 | QObject::objectName（setObjectName 的值）。Qt6 bridge 把它编码进 accessible_id 点分路径后缀（如 `EditorApplication.DropdownMenu.UnixAction`），运行时经 `get_accessible_id()` 读取，executor 按**后缀匹配**定位，selector 用 `selector.accessible_id` |
| role | 开发人员 | 否 | AT-SPI 角色 |
规则：
- **`id_name`/`object_name` 至少填一个**：仅 setAccessibleName 的控件只填
  `id_name`（selector.name）；QAction/DAction 等无 setAccessibleName 的控件填
  `object_name`（selector.accessible_id）；两者都有的控件**都填**——映射阶段
  有 object_name 时**优先用 `selector.accessible_id`**（更稳定：objectName 唯一，
  AccessibleName 可能被文本/角色污染）。两者都空 → 视同 TBD，不进分母。
- 重名控件 → 开发人员改源码 AccessibleName 使其唯一，**不在映射表加 parent 消歧**
- **菜单项不填 menu_type 字段**：executor 运行时按菜单项父 popup 的
  accessible_id 段模式自动分类触发方式（DropdownMenu 段→点共享 PToolButton；
  Menu_/Menu 段→标题栏 OptionMenu 按钮 + 键盘导航，禁 TAB；QMenu 段+嵌套
  段→父链展开；纯 QMenu 段→右键，需用例提供 context_trigger 触发点）。
  实测 deepin-editor：DDropdownMenu 项（WindowsAction）与主菜单项
  （Settings/NewWindow）关闭态树有节点 + objectName 编码，可智能路由；
  QMenu 右键菜单项关闭态**无节点**（CloseTab 等）或节点无 objectName
  （大写/小写），不可智能路由，用例用 `dtk_context_menu` + 右键触发点 +
  items 文本。
- **菜单项持久/瞬态判定**：有 `object_name` → 持久（进分母，accessible_id
  智能路由）；无 `object_name` 或关闭态无节点 → 瞬态（不进分母，
  dtk_context_menu + 文本）。
- AI 查表解析，查不到 → 标 UNSUPPORTED，禁止编造
- 活文档：代码变更新 `id_name`/`object_name`，UI 变更新 `ui_name`

## 9. 范本

见 `assets/case-template.yaml`。
