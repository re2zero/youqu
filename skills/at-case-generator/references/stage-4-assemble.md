# Stage 4: Assembly + Validation

> 本阶段由 `pipeline_assemble.py` 自动执行，主 agent 不参与。

## 执行

```bash
python3 skills/at-case-generator/scripts/pipeline_assemble.py \
    --modules tests/at/modules/ \
    --output tests/at/ \
    --at-tree tests/at/at-tree.yaml \
    [--generate-mapped tests/at/cases_mapped.yaml]
```

## 各模式跳过逻辑

| 模式 | 跳过 | 原因 |
|------|------|------|
| 标准 | 无 | 全量执行 |
| 无 at-tree | `--at-tree` 可选 | 不影响组装，只影响元素提取 |
| 所有模式 | 无 | assembly 是必须的 |

## 执行内容

1. 读取 `modules/*.output.json`（LLM Phase 2 输出）
2. 对每个 output.json 做 JSON Schema 校验（Gate 5 语义安全阀）
3. 校验通过后，按模块分组组装
4. 生成：
   - `yaml/elements.yaml` — 元素注册表
   - `yaml/<module_short>/<module_short>.suite.yaml` — 每模块一个 suite 文件
5. 若传 `--generate-mapped`，生成 `cases_mapped.yaml`（合并后的映射文件，用于额外的 Gate 3/5 校验）

## 校验规则

| 检查项 | 失败行为 |
|--------|----------|
| step_type 不是 action/assert | 打印错误，跳过该 suite |
| action 不在 VALID_ACTIONS 中 | 打印错误，跳过该 suite |
| assert 步骤的 action 不以 assert_ 开头 | 打印错误，跳过该 suite |
| 菜单动作缺少 items | 打印错误，跳过该 suite |
| keyboard_type 缺少 text | 打印错误，跳过该 suite |
| keyboard_type text > 50 字符 | 打印警告（可能是描述文本） |
| keyboard_hot_key 含中文 | 打印错误，跳过该 suite |
| suite 没有断言步骤 | 打印错误，跳过该 suite |
| selector 缺少 name | 打印警告（运行时可能找不到） |

## 产物

| 产物 | 生成者 | 谁读 | 命名策略 |
|------|--------|------|----------|
| `yaml/elements.yaml` | `pipeline_assemble.py` | AT-SPI 执行器 | 固定名覆盖 |
| `yaml/<module>/<module>.suite.yaml` | `pipeline_assemble.py` | AT-SPI 执行器 | 固定名覆盖 |
| `cases_mapped.yaml`（可选） | `pipeline_assemble.py` | Gate 3/5 校验 | 固定名覆盖 |