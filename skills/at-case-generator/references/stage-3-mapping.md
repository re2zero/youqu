# Stage 3: AI Semantic Mapping (AI Session — Parallel Sub-Agents)

**由子 agent 池执行**。每个模块一个子 agent，并行执行。

## 输入

每个子 agent 收到：
- `modules/<module_short>.input.json` — 该模块的 cases（原始步骤描述），如 `交互_键盘.input.json`
- `context-bundle.md` — 上下文包（三张表）
- `at-tree-annotated.yaml` — 标注后的 AT 树

## 输出

每个子 agent 输出：`modules/<module_short>.output.json`
- 格式：见 `templates/at-case-mapping-output-schema.json`
- 由 `pipeline_assemble.py` 在 Phase 3 校验

## 子 agent 任务模板

完整 prompt 见 `templates/at-case-mapping-prompt-template.md`。

## 核心原则（子 agent 必须遵守）

### 先理解，再映射

**不要逐条直接翻译 description 为 action。** 这是导致输出质量低下的根本原因。

正确流程：
1. 读所有 cases — 理解这个模块测什么功能、涉及哪些界面
2. 查 context-bundle.md — 找功能-操作-断言映射表，确定每个场景的断言目标
3. 查 at-tree-annotated.yaml — 找元素名、role、层级关系
4. 分组 — 按操作逻辑分组为 suites（每 suite 5-15 条 case）
5. 逐条映射 — 对每条 case 的每个 description，做四字段分解

### 每个 suite 的骨架

```
1. [action] session_start          → 启动应用（第一个 step）
2. [action] 前置操作（如展开侧栏、打开菜单等）
3. [action] 核心操作（点击、按键、输入等）
4. [action] 等待（仅在需要时，如等待文件对话框）
5. [assert] assert_element         → 验证操作结果（最后一个 step）
```

**禁止**：没有 `session_start` 的 suite、没有 `assert_element` 的 suite。

### 关于 wait 的严格约束

`wait` **只能**用于以下场景：
- 文件对话框操作后（`wait: 3.0`）
- 应用启动后（`wait: 3.0`，已在 `session_start` 中隐式处理）
- 动画/渲染完成后（`wait: 1.0`）

**禁止**：
- 用 `wait` 替代 `keyboard_press`、`keyboard_hot_key`、`element_action`
- 用 `wait` 替代断言（wait 不验证任何结果）
- 一个 case 中超过 1 个 `wait`

### 动作类型表

| 动作 | 适用场景 | 参数 |
|------|----------|------|
| `mouse_drag` | 拖拽操作 | selector 或 x/y |
| `element_action` | 点击按钮、复选框、输入框等可见控件 | selector, do(click/set/dblclick) |
| `mouse_click` | 点击文档区域、无 AT-SPI 名称的空白区域 | selector 或 x/y |
| `mouse_right_click` | 右键点击 | selector 或 x/y |
| `mouse_double_click` | 双击 | selector 或 x/y |
| `mouse_wheel` | 滚轮操作 | selector, direction(up/down), amount |
| `dtk_main_menu` | DTK 主菜单（标题栏主菜单按钮） | items: ["菜单项", "子菜单项"] |
| `dtk_context_menu` | 右键上下文菜单 | items: ["菜单项"], selector 或 x/y |
| `keyboard_press` | 单键按下（Enter, Escape, Tab, 方向键, F1-F12, PageDown, PageUp, Delete, BackSpace, Space, Home, End） | key |
| `keyboard_hot_key` | 组合键（Ctrl+O, Alt+F4, Ctrl+Shift+S） | key |
| `keyboard_type` | 输入文本 | text |
| `file_dialog_select` | 文件对话框选择文件 | path |
| `file_dialog_cancel` | 取消文件对话框 | 无参数 |
| `wait` | 等待固定时间（仅限启动/文件对话框后） | time |
| `wait_for` | 等待元素出现 | selector |
| `assert_element` | 验证元素存在 | selector.name |
| `assert_not_exists` | 验证元素不存在 | selector |
| `assert_window` | 验证窗口状态 | assertion: window_exists/window_not_exists |
| `assert_ocr_exists` | 验证 OCR 文本存在 | text |
| `assert_image_exists` | 验证图像存在 | template |
| `assert_process` | 验证进程状态 | process_name |
| `assert_file_exists` | 验证文件存在 | path |
| `element_set_value` | 设置元素值（不自带 click） | selector, value |
| `clipboard_input` | 剪贴板输入 | text |
| `hide_window` | 隐藏窗口 | 无参数 |
| `show_window` | 显示窗口 | 无参数 |

### 禁止清单

| 禁止动作 | 理由 | 替代方案 |
|----------|------|----------|
| 用 `wait` 替代键盘操作 | wait 不执行任何操作 | `keyboard_press` + 具体 key |
| `dtk_main_menu` 无 `items` | 菜单无法导航 | `items: ["菜单项", "子菜单项"]` |
| `assert_window` 作为唯一断言 | 不验证具体操作结果 | `assert_element` + 具体元素 |
| 无 `session_start` | 应用未启动，后续操作全失败 | 第一个 step 必须是 `session_start` |
| `keyboard_type` 输入描述文本 | 文本不是真实输入数据 | 替换为如 `"test_input_123"` |
| `element_action` 点击菜单项 | 菜单项瞬态弹出，运行时找不到 | `dtk_main_menu` / `dtk_context_menu` |
| suite id 使用原始 case_id | 不唯一且过长 | `suite_<模块短名>_XXX` |
| description 照搬原始文本 | 包含步骤编号和多余描述 | 简化为操作描述 |

### 功能性操作映射规则

| 用例描述模式 | 正确映射 | 错误映射 |
|-------------|----------|----------|
| 右键菜单 | 先 `mouse_right_click` 再 `dtk_context_menu` | 直接 `element_action` 点击菜单项 |
| 文件对话框操作 | 先 `element_action` 触发对话框，再 `file_dialog_select` | 直接 `file_dialog_select` |
| 快捷键操作 | `keyboard_hot_key` | `keyboard_press` 传组合键 |
| 输入框输入 | `element_action`(click) + `keyboard_type` | 直接 `element_action`(set) |
| 菜单操作 | `dtk_main_menu` | `element_action` 点击菜单项 |
| 多步骤复合操作 | 拆分为多个独立 step | 在一个 step 中写多个动作 |

### 输出格式示例

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
      "name": "Tab键切换",
      "annotation": {
        "测试界面": "主窗口-工具栏",
        "测试功能": "Tab键切换焦点",
        "前置条件": "应用已启动",
        "AT元素引用": ["{主菜单按钮}", "{打开按钮}"]
      },
      "steps": [
        {"step_type": "action", "action": "session_start", "command": "<应用名>", "description": "启动应用"},
        {"step_type": "action", "action": "keyboard_press", "key": "Tab", "description": "按Tab键切换焦点"},
        {"step_type": "assert", "action": "assert_element", "selector": {"name": "{主菜单按钮}", "role": "push button"}, "description": "验证焦点切换"}
      ]
    }
  ]
}
```

## 质量检查清单（子 agent 输出前检查）

- [ ] 每个 suite 第一个 step 是 `session_start` 吗？
- [ ] 每个 suite 最后一个 step 是 `assert_*` 吗？
- [ ] 所有 `wait` 都有合理用途（启动等待、文件对话框、动画等待）？
- [ ] 所有 `dtk_main_menu` 都有 `items` 数组？
- [ ] 没有使用 `assert_window` 作为唯一断言？
- [ ] 所有 `keyboard_type` 的 text 是真实输入数据？
- [ ] suite id 使用 `suite_<模块短名>_XXX` 格式？
- [ ] 不可自动化的 case 已标记 `unsupported` + `reason`？
- [ ] JSON 格式正确，无 YAML 语法？