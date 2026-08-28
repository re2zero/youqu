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

## 子 agent 调度（硬约束：每批 ≤ 3）

**上限 3 是硬约束，不是建议。** 先运行确定性调度脚本生成批次计划，
主 agent 严格按计划分批派发，批间串行。禁止一次性派发全部切片。

```bash
python3 <skill>/scripts/gen_schedule.py \
    --modules tests/at/modules/ --max-parallel 3
```

输出批次计划（stdout 或 `--output` 文件），每批 ≤ 3 个切片：

```json
{
  "max_parallel": 3,
  "total_slices": 27,
  "total_batches": 9,
  "batches": [
    {"batch": 1, "slices": [{"file": "...", "seq": 1, ...}]},
    ...
  ]
}
```

派发规则：
- 每批只派发该批内的切片（`batches[batch].slices`），**绝不超过 3 个**
- 批内并行，批间串行：等上一批全部完成（`completed`）再派发下一批
- 小切片合并已在 `pipeline_parse.py` 完成；若切片数 ≤ 2，单 agent 顺序处理
- 若某批有切片失败，跳过该切片标记 `skipped`，继续后续批次

**校验**：派发前对比 `gen_schedule.py` 的计划批次与当前派发的切片数，
任何一批超过 `--max-parallel` 即为违规，必须重新分批。

上限 3 的原因：并行过多时协调开销 > 并行收益（实测一次性派发 27 个
agent 会让效率显著下降，且容易越过 token/上下文预算）。

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

对每个切片用 `templates/at-case-mapping-prompt-template.md` 构建 prompt，
注入切片内容 + 元素清单白名单。**派发顺序必须来自 `gen_schedule.py` 的计划**：

```python
plan = read_json("tests/at/modules/_schedule.json")  # gen_schedule.py 输出
for batch in plan["batches"]:
    slices = batch["slices"]          # 本批 ≤ max_parallel(3)
    results = parallel([run_slice(s) for s in slices])  # 批内并行
    assert len(slices) <= plan["max_parallel"]          # 硬校验
    # 等本批全部完成后，再进入下一批（批间串行）

def run_slice(s):
    return agent(prompt=build_prompt(s))  # 写 tests/at/modules/<slice>.output.json
```

**禁止**：跳过 `gen_schedule.py` 直接派发全部切片；任何一批超过 3 个。
切片数 ≤ 2 时单 agent 顺序处理（计划只有 1 批）。

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
| 并行 > 3 | 太多反而慢；必须用 `gen_schedule.py` 分批 |
| 跳过 `gen_schedule.py` 一次性派发全部切片 | 违反硬性 cap-3 |
