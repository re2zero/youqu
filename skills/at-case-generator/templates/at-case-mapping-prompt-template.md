# Phase 2: AT-SPI 语义映射 — 模块级映射协议

## 角色
你是桌面应用 AT-SPI YAML 测试套件映射智能体。
当前任务：将一个**功能模块**的测试用例从 `input.json` 映射为 `output.json`。

## 输入
- `input.json` — 当前模块的用例（约 15-30 条，~50-100 步），每条用例包含 `id`、`name`、`steps[]`（每个 step 有 `step_type` 和 `description`）
- `context-bundle.md` — 全量上下文包（三张表：元素-功能对照 / 界面-元素映射 / 功能-操作-断言映射）
- `at-tree-annotated.yaml` — 全量 AT-SPI 标注树（写 selector 时查元素名/role/层级/comment）

## 输出
每个模块一个 `output.json`，格式见下方"完整示例"。

---

## 核心流程：先理解，再映射

**不要逐条直接翻译 description 为 action。** 这是导致输出质量低下的根本原因。

正确流程：
1. **读所有 cases** — 理解这个模块测什么功能、涉及哪些界面
2. **查 context-bundle.md** — 找功能-操作-断言映射表，确定每个场景的断言目标
3. **查 at-tree-annotated.yaml** — 找元素名、role、层级关系
4. **分组** — 按操作逻辑分组为 suites（每 suite 5-15 条 case）
5. **逐条映射** — 对每条 case 的每个 description，做四字段分解

---

## 完整示例（通用）

假设输入是"键盘交互"模块，包含"Tab键切换"、"快捷键"等用例。
`{占位符}` 表示从 at-tree-annotated.yaml 中查找的真实元素名。

### 正确的输出

```json
{
  "meta": {
    "app": "<应用名，来自 input.json>",
    "module": "<模块名，来自 input.json>",
    "module_slug": "<slug，来自 input.json>",
    "module_short": "<短模块名，来自 input.json>"
  },
  "suites": [
    {
      "id": "suite_<module_short>_001",
      "name": "首页Tab键切换",
      "annotation": {
        "测试界面": "主窗口-工具栏与菜单栏",
        "测试功能": "Tab键在工具栏按钮间切换焦点",
        "前置条件": "应用已启动，首页已打开，无文档打开",
        "AT元素引用": ["{主菜单按钮}", "{打开按钮}"]
      },
      "steps": [
        {
          "step_type": "action",
          "action": "session_start",
          "command": "<应用名>",
          "description": "启动应用"
        },
        {
          "step_type": "action",
          "action": "keyboard_press",
          "key": "Tab",
          "description": "按Tab键切换焦点到下一个按钮"
        },
        {
          "step_type": "action",
          "action": "keyboard_press",
          "key": "Tab",
          "description": "再次按Tab键切换焦点"
        },
        {
          "step_type": "assert",
          "action": "assert_element",
          "selector": {"name": "{主菜单按钮}", "role": "push button"},
          "description": "验证焦点切换到主菜单按钮"
        }
      ]
    },
    {
      "id": "suite_<module_short>_002",
      "name": "快捷键操作",
      "annotation": {
        "测试界面": "文档区域",
        "测试功能": "Ctrl+O打开文件、Ctrl+S保存、Ctrl+W关闭",
        "前置条件": "应用已启动",
        "AT元素引用": ["{文档内容区域}"]
      },
      "steps": [
        {
          "step_type": "action",
          "action": "session_start",
          "command": "<应用名>",
          "description": "启动应用"
        },
        {
          "step_type": "action",
          "action": "keyboard_hot_key",
          "key": "ctrl+o",
          "description": "按Ctrl+O打开文件"
        },
        {
          "step_type": "action",
          "action": "file_dialog_select",
          "path": "${TEST_FILES_DIR}/test_file",
          "wait": 3.0,
          "description": "选择文件并打开"
        },
        {
          "step_type": "assert",
          "action": "assert_element",
          "selector": {"name": "{文档内容区域}", "role": "form"},
          "description": "验证文档已打开"
        }
      ]
    },
    {
      "id": "suite_<module_short>_003",
      "name": "展开侧栏后Tab键切换",
      "annotation": {
        "测试界面": "主窗口-左侧栏+文档区域",
        "测试功能": "Tab键在左侧栏与文档区域间切换焦点",
        "前置条件": "应用已启动，文档已打开，左侧栏已展开",
        "AT元素引用": ["{侧栏切换按钮}", "{侧栏列表}"]
      },
      "steps": [
        {
          "step_type": "action",
          "action": "session_start",
          "command": "<应用名> ${TEST_FILES_DIR}/test_file",
          "description": "启动应用并打开文档"
        },
        {
          "step_type": "action",
          "action": "element_action",
          "selector": {"name": "{侧栏切换按钮}", "role": "check box"},
          "do": "click",
          "description": "点击展开左侧栏"
        },
        {
          "step_type": "action",
          "action": "keyboard_press",
          "key": "Tab",
          "description": "按Tab键在左侧栏和文档区域间切换"
        },
        {
          "step_type": "assert",
          "action": "assert_element",
          "selector": {"name": "{侧栏列表}", "role": "list"},
          "description": "验证焦点切换到左侧栏列表"
        }
      ]
    }
  ]
}
```

### 常见的错误输出

```json
{
  "meta": { "module_short": "键盘" },
  "suites": [
    {
      "id": "suite_v25_xxx_case_1580879",
      "name": "首页Tab键切换",
      "steps": [
        {"step_type": "assert", "action": "assert_window", "description": "1. 打开应用进入首页界面"},
        {"step_type": "action", "action": "wait", "description": "2. 按enter或空格键"},
        {"step_type": "action", "action": "dtk_main_menu", "description": "3. 主菜单弹出后按方向键"},
        {"step_type": "action", "action": "wait", "description": "4. 主菜单弹出后按esc键"}
      ]
    }
  ]
}
```

**错误分析**：
| 错误 | 正确做法 |
|------|----------|
| `assert_window` 作为第一个 step | 第一个 step 必须是 `session_start`，不是断言 |
| `wait` 作为主要操作 | `wait` 只能用于等待加载，不能替代 `keyboard_press` |
| `dtk_main_menu` 无 `items` | 菜单操作必须有 `items: ["菜单项名"]` |
| suite id 使用了原始 case_id | suite id 应为 `suite_<模块短名>_XXX` |
| description 照搬原始文本（含数字编号） | description 应简化为操作描述 |
| 无断言验证操作结果 | 每个 case 至少一个 `assert_element` |
| 无 `session_start` | 每个 suite 必须有一个 `session_start` 作为第一个 action |

---

## 核心映射规则

### 0. 每个 suite 的骨架

每个 suite 的结构必须是：

```
1. [action] session_start          → 启动应用（第一个 step）
2. [action] 前置操作（如展开侧栏、打开菜单等）
3. [action] 核心操作（点击、按键、输入等）
4. [action] 等待（仅在需要时，如等待文件对话框）
5. [assert] assert_element         → 验证操作结果（最后一个 step）
```

**禁止**：没有 `session_start` 的 suite、没有 `assert_element` 的 suite。

### 1. 四字段分解（每步必做）

对每条 `description`，拆解为 4 层：
- **操作**（operation）→ `action` + `selector`/`key`/`items`
- **目标**（target）→ `selector` 中的元素名
- **预期**（expected）→ `assert_*` 步骤
- **前置**（precondition）→ 前置 action 步骤，**不可跳过**

### 2. 预期结果 → assert 步骤

**禁止**把预期结果放进 `wait` 或 `keyboard_type.text`。
```json
# 正确：
{"step_type": "assert", "action": "assert_element", "selector": {"name": "{元素名}", "role": "push button"}}

# 错误：
{"step_type": "action", "action": "wait", "description": "验证窗口出现"}
```

### 3. 关于 wait 的严格约束

`wait` **只能**用于以下场景：
- 文件对话框操作后（`wait: 3.0`）
- 应用启动后（`wait: 3.0`，已在 `session_start` 中隐式处理）
- 动画/渲染完成后（`wait: 1.0`）

**禁止**：
- 用 `wait` 替代 `keyboard_press`、`keyboard_hot_key`、`element_action`
- 用 `wait` 替代断言（wait 不验证任何结果）
- 一个 case 中超过 1 个 `wait`

### 4. 菜单项 → dtk_main_menu / dtk_context_menu

菜单项是瞬态元素，**禁止**用 `element_action` 定位。

```json
# 正确（items 必须有具体菜单项名，从 context-bundle.md 的界面-元素映射中查找）：
{"action": "dtk_main_menu", "items": ["菜单项", "子菜单项"]}

# 错误（无 items）：
{"action": "dtk_main_menu"}
```

### 5. 断言质量

- 每个 case 至少有一个 `assert_*` 步骤，且**不是** `assert_window`
- `assert_element` 的 selector 必须有 `name`（从 at-tree-annotated.yaml 中找）
- 推荐：`assert_element`（元素出现），`assert_not_exists`（元素消失）
- 断言目标从 context-bundle.md 的"功能-操作-断言映射"表中选取

### 6a. 分组与去重策略（关键）

**不要 1:1 映射**。不要为每个 input case 创建一个 suite。多个相似 case 应合并为一个 suite。

分组规则：
- 相同操作逻辑（如"打开文档"、"Tab键切换"）合并为同一个 suite
- 参数化差异（如"打开PDF/打开DOCX/打开DJVU"）合并为同一个 suite，用不同文件路径
- 每 suite 5-15 条 case，超出则拆分为多个 suite

去重规则：
- **公共前置条件放 suite 级**：公共前置条件放在 suite 的 `前置条件` 注释中或 setup 步骤中，**不在每个 case 的 step 中重复**
- **相同断言去重**：同一 suite 中，**禁止**发出重复的断言（相同 `action` + 相同 `selector`）
- **有意重复按键保留**：重复按键（如 `Tab` `Tab` `Tab`）是测试逻辑的一部分，**不得**盲目合并为一个
- **相同操作序列只保留一个**：多条 case 的操作序列完全一致时，只保留一条作为 suite，其余标注 `status: duplicate`

```json
# 正确：3 个"打开不同类型文档"的 case 合并为 1 个 suite
{
  "id": "suite_文档打开_001",
  "name": "打开不同格式文档",
  "steps": [
    {"step_type": "action", "action": "session_start", "command": "deepin-reader"},
    {"step_type": "action", "action": "keyboard_hot_key", "key": "ctrl+o"},
    {"step_type": "action", "action": "file_dialog_select", "path": "${TEST_FILES_DIR}/test.pdf", "wait": 3.0},
    {"step_type": "assert", "action": "assert_element", "selector": {"name": "PagingWidget"}}
  ]
}

# 错误：3 个 case 各自是 1 个 suite，操作序列完全相同
```

### 6b. 字段名规范（强制）

输出 JSON 必须使用**规范的字段名**，不得使用旧版字段名：
| 规范字段 | 旧版字段（禁止） | 说明 |
|----------|-----------------|------|
| `step_type` | `type` | `action` 或 `assert` |
| `action` | `operation` | 动作类型 |
| `selector.name` | `target` | 元素名称 |
| `selector.role` | — | 元素角色 |
| `do` | `value` 且值为 click/clear/set | 操作类型 |
| `key` | — | 键盘按键 |
| `items` | — | 菜单路径 |

**错误（会被 pipeline_assemble.py 过滤为空步骤）：**
```json
{"type": "action", "operation": "element_action", "target": "Button_Save", "value": "click"}
```
**正确：**
```json
{"step_type": "action", "action": "element_action", "selector": {"name": "Button_Save"}, "do": "click"}
```
### 6c. 不可自动化分类规则（关键）
以下情况**必须**标记 `status: unsupported` + `reason`：
- 触屏/触控板多点触控手势（单指点击/双击可用 `mouse_click`/`mouse_double_click` 替代，不标记）
- 纯视觉判断（"界面美观""动画流畅""显示正常"）
- 外部硬件依赖（连接显示器、U盘）
- 跨应用拖拽（跨进程拖拽到其他应用）
- 性能/压力测试（大量窗口、长时间运行）
- 纯终端命令（非 GUI 操作）
- 系统级操作（重启/关机/注销、用户切换、多屏）

以下情况**不得**标记 unsupported，必须找替代方案：
| 原始描述 | 替代方案 | 说明 |
|----------|----------|------|
| "拖拽标签页" | `mouse_drag` + selector | 同窗口拖拽可用 `mouse_drag` |
| "双击文档打开" | `keyboard_hot_key ctrl+o` + `file_dialog_select` | 文件菜单打开 |
| "从文件管理器拖拽/双击" | `keyboard_hot_key ctrl+o` + `file_dialog_select` | 应用内打开文件 |
| "右键点击" | `mouse_right_click` + `dtk_context_menu` | 右键菜单可用 |
| "点击X关闭" | `element_action` + selector (close button) | 关闭按钮在 AT 树中 |
| "滚动页面" | `mouse_wheel` | 滚轮操作可用 |
| "按文件名搜索" | `keyboard_type` + `keyboard_press Enter` | 搜索框输入

### 7. 输出约束

1. 每个 `output.json` 只包含当前模块的 suites
2. 每 suite 的 `id` 前缀为 `suite_<module_short>`，如 `suite_键盘交互_001`
3. 每个 `step_type: assert` 的步骤必须有 `assert_*` 的 action
4. 每个 suite 的第一个 step 必须是 `session_start`
5. 每个 suite 的最后一个 step 必须是 `assert_*`
6. 输出 JSON 格式，禁止 YAML 锚点/别名

### 8. 禁止清单

| 禁止动作 | 理由 | 替代方案 |
|----------|------|----------|
| 用 `wait` 替代键盘操作 | wait 不执行任何操作 | `keyboard_press` + 具体 key |
| `dtk_main_menu` 无 `items` | 菜单无法导航 | `items: ["菜单项", "子菜单项"]` |
| `assert_window` 作为唯一断言 | 不验证具体操作结果 | `assert_element` + 具体元素名 |
| 无 `session_start` | 应用未启动，后续操作全失败 | 第一个 step 必须是 `session_start` |
| `keyboard_type` 输入描述文本 | 文本不是真实输入数据 | 替换为如 `"test_input_123"` |
| `element_action` 点击菜单项 | 菜单项瞬态弹出，运行时找不到 | `dtk_main_menu` / `dtk_context_menu` |
| suite id 使用原始 case_id | 不唯一且过长 | `suite_<模块短名>_XXX` |
| description 照搬原始文本（含"1. ""2. "前缀） | 包含步骤编号和多余描述 | 简化为操作描述 |
| 在 `selector.name` 中使用中文描述 | 元素名必须是 AT-SPI 中的精确英文名 | 从 at-tree-annotated.yaml 中查找英文名 |

## 验证自查（输出前逐条检查）

- [ ] 每个 suite 第一个 step 是 `session_start` 吗？
- [ ] 每个 suite 最后一个 step 是 `assert_*` 吗？
- [ ] 所有 `wait` 都有合理用途（启动等待、文件对话框、动画等待）？
- [ ] 所有 `dtk_main_menu` 都有 `items` 数组？
- [ ] 没有使用 `assert_window` 作为唯一断言？
- [ ] 所有 `keyboard_type` 的 text 是真实输入数据？
- [ ] suite id 使用 `suite_<模块短名>_XXX` 格式？
- [ ] 所有 `selector.name` 的值来自 at-tree-annotated.yaml（不是中文描述，不是虚构名）？
- [ ] 不可自动化的 case 已标记 `unsupported` + `reason`？
- [ ] JSON 格式正确，无 YAML 语法？