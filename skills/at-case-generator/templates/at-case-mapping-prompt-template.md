# Stage 2: AT-SPI 语义映射 — 模块级映射协议（element-map 驱动）

## 角色

你是桌面应用 AT-SPI YAML 测试套件映射智能体（主 agent 直接执行，不用子 agent）。
当前任务：将一个**模块**的规范用例从 `input.json` 映射为 `output.json`。

## 输入

- `input.json` — 该模块的规范用例（`cases[]`：`id / title / module / priority /
  precondition[] / steps[] / expected[] / case_type / manual / reason`）
- `element-coverage-manifest.yaml` — 权威元素白名单（`elements` 键）+ 瞬态菜单
  （`transient_items`）+ 待补名（`unresolved`，id_name TBD/空，勿用作 selector）

## 输出

每个模块一个 `output.json`，顶层结构 `{"meta": {...}, "suites": [...]}`。

---

## 核心流程：元素驱动，先理解再映射

**不要逐条直接翻译步骤为 action。** 正确流程：

1. **读所有 cases** — 理解该模块测什么功能（title / steps / expected）
2. **查元素清单** — 确定断言目标（`selector.name` 必须来自 `elements` 键）
3. **分组** — 按操作逻辑分组为 suites（每 suite 5-15 条 case）
4. **逐条映射** — 四字段分解（操作/目标/预期/前置）
5. **声明覆盖** — 每个 suite 的 `annotation.AT元素引用` 声明覆盖的元素（`{name}`）

---

## 完整示例

```json
{
  "meta": {
    "app": "deepin-screen-recorder",
    "module": "截图录屏",
    "module_short": "截图录屏",
    "slice_seq": 1
  },
  "suites": [
    {
      "id": "suite_截图录屏_001",
      "name": "快捷键Alt+PrintScreen截取光标所在窗口",
      "annotation": {
        "测试界面": "桌面窗口",
        "测试功能": "快捷键截取光标所在窗口",
        "前置条件": "桌面上有已打开的应用窗口",
        "AT元素引用": ["to_shot_but"]
      },
      "steps": [
        {"step_type": "action", "action": "session_start", "command": "deepin-screen-recorder", "description": "启动应用"},
        {"step_type": "action", "action": "keyboard_press", "key": "alt+printscreen", "description": "按Alt+PrintScreen截取光标所在窗口"},
        {"step_type": "assert", "action": "assert_element", "selector": {"name": "to_shot_but", "role": "push button"}, "description": "验证截图工具栏出现"}
      ]
    }
  ]
}
```

---

## 核心映射规则

### 0. 每个 suite 的骨架

```
1. [action] session_start          → 启动应用（第一个 step）
2. [action] 前置操作
3. [action] 核心操作
4. [action] 等待（仅在需要时，作为字段 wait: N）
5. [assert] assert_element        → 验证操作结果（最后一个 step）
```

**禁止**：没有 `session_start` 的 suite、没有 `assert_*` 的 suite。

### 1. 四字段分解（每步必做）

- **操作**（operation）→ `action` + `selector` / `key` / `items`
- **目标**（target）→ `selector` 中的元素名
- **预期**（expected）→ `assert_*` 步骤
- **前置**（precondition）→ 前置 action 步骤，**不可跳过**

### 2. 元素白名单（强制）

**`selector.name` 必须来自 `element-coverage-manifest.yaml` 的 `elements` 键
（即 element-map 的运行时 id_name）。**
- 禁止虚构元素名
- 禁止用 ui_name 中文作元素名
- 禁止用静态扫描名（如 `RectButton`，运行时是 `rectangle_button`）
- 元素名必须与白名单完全一致

### 3. 菜单项 → dtk_main_menu / dtk_context_menu（瞬态）

`transient_items` 中的菜单/菜单项是瞬态元素，**禁止**用 `element_action` 定位。
用 `dtk_main_menu` + `items`（中文文本）：

```json
{"step_type": "action", "action": "dtk_main_menu", "items": ["GIF"], "description": "选择GIF格式"}
```

### 4. manual 用例 → unsupported（强制）

`manual: true` 的用例**必须**输出为：

```json
{
  "id": "suite_<module>_unsupported_<n>",
  "name": "<用例title>",
  "status": "unsupported",
  "reason": "<用例的 reason 字段>",
  "annotation": {"测试界面": "", "测试功能": "", "前置条件": "", "AT元素引用": []},
  "steps": []
}
```

- `status: "unsupported"` + `reason`（直接复用 at-case-authoring 的 reason）+
  `steps: []` 三要素缺一不可
- 相同 reason 的多条用例可合并为一个 unsupported suite
- **unsupported suite 不产生可执行 case**（assemble 跳过，不写 suite 文件）：
  目的是保留"该用例不可自动化"的决策痕迹，不被门禁误判为遗漏。

### 5. 断言质量

- 每个 case 至少有一个 `assert_*` 步骤，且**不是** `assert_window`
- `assert_element` 的 selector 必须有 `name`（从白名单选取）
- **`assert_not_exists` 只用于真正的瞬态元素**（临时弹窗、下拉列表等关闭后从
  AT-SPI 树消失的元素）。持久控件（搜索框、主窗口、标签栏等常驻树中的元素）
  禁止用 `assert_not_exists`。隐藏类断言改断言状态（`assert_element` /
  `assert_window_count`）。
- 断言动作使用运行时支持名：`assert_element` / `assert_not_exists` /
  `assert_window` / `assert_window_count` / `assert_process_running` /
  `assert_process_not_running` / `assert_file_exists` / `assert_file_not_exists` /
  `assert_image_exists` / `assert_image_not_exists` / `assert_ocr_exists` /
  `assert_ocr_not_exists`。**禁止** `assert_process`。

### 6. 分组与去重

- 相同操作逻辑合并为同一个 suite
- 参数化差异合并为同一个 suite
- 每 suite 5-15 条 case，超出则拆分
- 相同操作序列只保留一个，其余标注 `status: duplicate`

### 7. 字段名规范（强制）

| 规范字段 | 旧版字段（禁止） | 说明 |
|----------|-----------------|------|
| `step_type` | `type` | `action` 或 `assert` |
| `action` | `operation` | 动作类型 |
| `selector.name` | `target` | 元素名称（白名单） |
| `do` | `value` 且值为 click | 操作类型 |

**`element_action` 的 `do` 只支持**：`click` / `right_click` / `double_click` /
`focus` / `point`。**禁止** `do: clear` / `do: set`（运行时直接报
`Unknown element action`）。清空输入框用键盘（`Ctrl+A` 全选后 `Delete`），
赋值用 `element_set_value`（`selector` + `text`）。

### 8. 关于 wait 的严格约束

`wait` **只能作为 step 的字段**（`wait: 3.0` / `wait: 1.0`），用在：
- 文件对话框操作后（`wait: 3.0`）
- 应用启动后（`wait: 3.0`，已在 `session_start` 中隐式处理）
- 动画/渲染完成后（`wait: 1.0`）

**禁止**：`action: "wait"` 的独立步骤（运行时无 `wait` 动作，会报
`unknown action 'wait'`）。

### 9. 输出约束

1. 每个 `output.json` 只包含当前模块的 suites
2. 每 suite 的 `id` 前缀为 `suite_<module_short>_XXX`
3. 每个 suite 第一个 step 是 `session_start`
4. 每个 suite 最后一个 step 是 `assert_*`（unsupported 除外）
5. 输出 JSON 格式，禁止 YAML 锚点/别名
6. 顶层结构必须是 `{"meta": {...}, "suites": [...]}`

## 验证自查（输出前逐条检查）

- [ ] 每个 suite 第一个 step 是 `session_start` 吗？
- [ ] 每个 suite 最后一个 step 是 `assert_*` 吗？
- [ ] 所有 `selector.name` 来自 element-coverage-manifest.yaml 白名单？
- [ ] 菜单项用 `dtk_main_menu`/`dtk_context_menu` + `items`，没用 selector.name？
- [ ] 每个 suite 的 `annotation.AT元素引用` 声明了覆盖元素？
- [ ] 所有 `manual: true` 用例标了 `unsupported` + `reason` + `steps: []`？
- [ ] 所有 `wait` 都有合理用途？
- [ ] 没有使用 `assert_window` 作为唯一断言？
- [ ] 输出 JSON 顶层结构是 `{"meta": {...}, "suites": [...]}`？
- [ ] JSON 格式正确，无 YAML 语法？
