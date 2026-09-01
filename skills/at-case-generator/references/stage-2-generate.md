# Stage 2: Semantic Mapping（主 agent 直接映射）

> 本阶段由**主 agent** 执行（不用子 agent——用户决策：协调开销 > 收益）。
> 逐模块顺序处理，每模块一个 input.json → output.json。

**产物目录固定 `tests/at/`**（见 stage-1）。

## 输入

每个模块映射时，主 agent 读取：
- `tests/at/modules/<slug>_<seq>.input.json` — 该模块规范用例（含
  `manual` / `reason` / `steps[]` / `expected[]` / `precondition[]`）
- `tests/at/element-coverage-manifest.yaml` — 权威元素白名单（`elements` 键）
  + 瞬态菜单（`transient_items`）+ 待补名（`unresolved`）

## 输出

每个模块一个 `tests/at/modules/<slug>_<seq>.output.json`，格式见
`templates/at-case-mapping-prompt-template.md`。由 `pipeline_assemble.py`
在 Stage 3 校验。

## 主 agent 执行流程

```python
summary = read_json("tests/at/modules/_summary.json")
for slice_info in summary["slices"]:
    in_path = f"tests/at/modules/{slice_info['file']}"
    build_prompt(in_path)                    # 注入 input.json + element-map
    write(f"tests/at/modules/{out_name}")    # output.json
```

- 顺序执行，不并行（无子 agent）。
- 每个模块独立 prompt：读该模块全部用例 → 查元素清单 → 分组映射 → 写 output.json。
- 模块内用例分组为 suites（每 suite 5-15 条 case），相同操作逻辑合并。
- **不修改 `meta`**：output.json 的 `meta` 原样沿用 input.json（assemble 据此
  决定输出文件名与模块归属）。

## 核心原则（映射时必须遵守）

1. **元素驱动**：先读该模块所有用例理解测什么 → 查 element-map 白名单确定
   断言目标 → 分组 → 逐条四字段分解（操作/目标/预期/前置）。
2. **selector.name 只从白名单 `elements` 键取**（element-map id_name，运行时名）。
   禁止虚构、禁止 ui_name 中文、禁止菜单项、禁止 unresolved（TBD）名。
3. **菜单（transient_items）**：用 `dtk_main_menu` / `dtk_context_menu` + `items`
   文本操作，不写 `selector.name`。
4. **manual 用例**：`manual: true` → `status: "unsupported"` + `reason`（直接用
   at-case-authoring 的 reason），`steps: []`。不再自行判断。
   **unsupported 不会产生可执行 case**（见 stage-3 处置说明）；多个同 reason
   的 manual 用例可合并为一个 unsupported suite，以保留决策痕迹。
5. **骨架**：每个 suite 第一个 step 是 `session_start`（command=应用名），
   最后一个 step 是 `assert_*`。禁止无 session_start / 无断言的 suite。
6. **wait 只作 step 字段**（`wait: 3.0`），禁止 `action: "wait"` 独立步骤。
7. **断言动作运行时支持名**：`assert_element` / `assert_not_exists` /
   `assert_window` / `assert_window_count` / `assert_process_running` /
   `assert_process_not_running` / `assert_file_exists` / `assert_file_not_exists` /
   `assert_image_exists` / `assert_image_not_exists` / `assert_ocr_exists` /
   `assert_ocr_not_exists`。禁止 `assert_process`。
8. **`element_action` 的 `do`**：仅 `click` / `right_click` / `double_click` /
   `focus` / `point`。禁止 `do: clear` / `do: set`。

## 失败处理

| 失败 | 行为 |
|------|------|
| 某模块映射失败 | 重试一次；仍失败跳过该模块，报告标注 |
| 某模块 0 条用例通过校验 | 停止该模块，需重试 |
| 输出 JSON 不合法 | 重试一次；仍失败跳过并报告 |

## 字段名规范（强制）

| 规范字段 | 旧版字段（禁止） | 说明 |
|----------|-----------------|------|
| `step_type` | `type` | `action` 或 `assert` |
| `action` | `operation` | 动作类型 |
| `selector.name` | `target` | 元素名称（白名单） |
| `do` | `value` 且值为 click | 操作类型 |

每个 suite 的 `annotation.AT元素引用` 必须列出该 suite 实际引用的白名单元素名
（`{name}` 包裹），这是覆盖门禁的输入。
