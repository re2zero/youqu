# Stage 3: Assembly + Coverage Gate

> 本阶段由确定性脚本自动执行，主 agent 不参与。

产物目录固定 `tests/at/`（见 stage-1）。

## 执行

```bash
# 1. 组装
python3 <skill>/scripts/pipeline_assemble.py \
    --modules tests/at/modules/ \
    --output tests/at/ \
    --manifest tests/at/element-coverage-manifest.yaml \
    --generate-mapped tests/at/cases_mapped.yaml

# 2. 覆盖门禁（硬性 100%）
python3 <skill>/scripts/cover.py \
    --scan-dir tests/at/coverage_scan/ \
    --testdir tests/at/yaml/ \
    --manifest tests/at/coverage-report.yaml \
    --unreachable tests/at/unreachable.yaml \
    --threshold 100
```

## 组装（pipeline_assemble.py）

1. 读取 `tests/at/modules/*.output.json`
2. 对每个 output.json 做 JSON Schema 校验（Gate 5 语义安全阀）
3. 校验通过后按模块分组组装
4. 生成 `tests/at/yaml/elements.yaml` + `tests/at/yaml/<module>/*.suite.yaml`
5. 从 `element-coverage-manifest.yaml` 补充元素到 elements.yaml（权威白名单）
6. 收集每个 suite 的 `annotation.AT元素引用` 声明覆盖元素

## 覆盖门禁（cover.py）

硬性目标：**ok 集（`pre_scan_ok.yaml` + `qml_ok.yaml` 已命名交互元素）中每个元素必须被至少一个 suite 的持久 `selector.name` 引用**。

```
coverage = covered / (scan_total - unreachable) × 100%
```

- **covered** = 持久 selector.name（去重，剔文件名噪音）
- **scan_total** = ok 集元素数
- **unreachable** = 人工确认的不可达元素（`tests/at/unreachable.yaml`，唯一豁免通道）
- **gap 元素不计入分母**（缺名/动态拼接，无法按名定位）
- 退出码 0 = 达标，1 = 未达标；扫描产物缺失时报错退出（防空门禁）

## 校验规则

| 检查项 | 失败行为 |
|--------|----------|
| step_type 不是 action/assert | 跳过该 suite |
| action 不在 VALID_ACTIONS | 跳过该 suite |
| assert 步骤 action 不以 assert_ 开头 | 跳过该 suite |
| 菜单动作缺少 items | 跳过该 suite |
| keyboard_type 缺少 text | 跳过该 suite |
| suite 没有断言步骤 | 跳过该 suite |
| selector 缺少 name | 警告 |

## 产物

| 产物 | 生成者 | 谁读 |
|------|--------|------|
| `tests/at/yaml/elements.yaml` | pipeline_assemble.py | AT-SPI 执行器 |
| `tests/at/yaml/<module>/*.suite.yaml` | pipeline_assemble.py | AT-SPI 执行器 |
| `tests/at/cases_mapped.yaml` | pipeline_assemble.py | Gate 校验 |
| `tests/at/coverage-report.yaml` | cover.py | 主 agent（补漏输入） |
