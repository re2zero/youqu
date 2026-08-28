# Stage 2: Generation (AI Sub-Agent Pool)

**由子 agent 池执行**。每个切片一个子 agent。

> 产物目录固定 `tests/at/`（见 stage-1）。不要改用其它目录。

## 输入

每个子 agent 收到：
- `tests/at/modules/<slice>.input.json` — 该切片用例（token 预算内）
- `tests/at/element-coverage-manifest.yaml` — 权威元素白名单（**selector.name 必须从中选取**）
- `tests/at/at-tree-annotated.yaml`（可选）— role/层级参考

## 输出

每个子 agent 输出：`tests/at/modules/<slice>.output.json`
- 格式：见 `templates/at-case-mapping-prompt-template.md`
- 由 `pipeline_assemble.py` 在阶段 3 校验

## 子 agent 调度

| 切片数 | 策略 |
|--------|------|
| ≤ 2 | 单 agent 顺序 |
| 3-9 | 并行，上限 3 |
| > 9 | 分批并行，每批 ≤ 3，批间串行 |

上限 3：并行过多时协调开销 > 并行收益。

## 核心原则（子 agent 必须遵守）

### 元素驱动，先理解再映射

1. **读所有 cases** — 理解切片测什么功能
2. **查元素清单** — 确定断言目标（selector.name 必须来自白名单）
3. **分组** — 按操作逻辑分组为 suites（每 suite 5-15 条 case）
4. **逐条映射** — 四字段分解（操作/目标/预期/前置）
5. **声明覆盖** — 每个 suite 的 `annotation.AT元素引用` 声明覆盖的元素

### 每个 suite 的骨架

```
1. [action] session_start          → 启动应用（第一个 step）
2. [action] 前置操作
3. [action] 核心操作
4. [action] 等待（仅在需要时）
5. [assert] assert_element        → 验证操作结果（最后一个 step）
```

**禁止**：没有 `session_start` 的 suite、没有 `assert_element` 的 suite。

### 覆盖声明

每个 suite 的 `annotation.AT元素引用` 必须列出该 suite 实际引用的元素名（从白名单选取）。这是覆盖门禁的输入。

## 主 agent 执行

对每个切片用 `templates/at-case-mapping-prompt-template.md` 构建 prompt，注入切片内容 + 元素清单白名单。自适应调度：

```python
summary = read("tests/at/modules/_summary.json")
slices = summary["slices"]  # [ {file, module, case_count, est_tokens}, ... ]

def run_slice(s):
    return agent(prompt=build_prompt(s))  # 写 tests/at/modules/<slice>.output.json

if len(slices) <= 2:
    for s in slices:
        run_slice(s)          # 单 agent 顺序
else:
    for batch in chunks(slices, 3):
        parallel([run_slice(s) for s in batch])  # 每批 ≤3，批间串行
```

## 子 agent 失败处理

| 失败 | 行为 |
|------|------|
| 某切片生成失败 | 不阻塞：跳过该切片，标记 `status: skipped`，报告里说明 |
| 某切片 0 条用例通过校验 | 停止该模块，需重试 |
| 输出 JSON 不合法 | 重试一次；仍失败则跳过并报告 |

## 不支持的动作

| 动作 | 原因 |
|------|------|
| 跳过元素清单 | selector 白名单是 100% 覆盖的基础 |
| 合并多个切片到同一 agent | 上下文混杂，token 超预算 |
| 并行 > 3 | 太多反而慢 |
