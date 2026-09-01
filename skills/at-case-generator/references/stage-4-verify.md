# Stage 4: Gap-Filling Loop + Verification

> 产物目录固定 `tests/at/`（见 stage-1）。

## 补漏循环（仅当有未覆盖元素）

cover.py 报出未覆盖元素时，进入补漏循环（**主 agent** 聚焦补充，不并行）：

1. 读取 `tests/at/coverage-report.yaml` 的 `uncovered_elements` 列表
2. 主 agent 聚焦生成补充用例，写入新的 `modules/<slug>_<seq>.output.json`
3. 重新 `pipeline_assemble.py` + `cover.py`
4. 循环直到 100% 或人工确认不可达

**人工豁免（unreachable.yaml）**：条件渲染 / 动态名等**已命名**但运行时无法稳定
定位的持久元素，人工确认后写入 `tests/at/unreachable.yaml`：

```yaml
unreachable:
  - name: ZoomButton
    reason: 条件渲染，仅特定状态出现
```

人工确认后从分母剔除。**这是 100% 的唯一豁免通道。**

> **区分 `unresolved` 与 `unreachable.yaml`**：
> - `element-coverage-manifest.yaml` 的 `unresolved` 段是 id_name TBD/空——本
>   就不进分母（清单阶段已排除），是"待开发填名"的文档清单，**不要**抄进
>   unreachable.yaml。
> - `unreachable.yaml` 是**已命名但不可达**元素的人工豁免，由 cover.py 消费。

## 验证流程

### 1. Gate 5 — 语义安全阀

```bash
youqu at validate --gate 5 --cases-mapped tests/at/cases_mapped.yaml
```

> 本技能不产出 `at-tree.yaml`（无源码扫描）。Gate 4 的 `--at-tree` 参数无法
> 提供，故 Gate 4 仅作生成产物结构校验（`--generate-output`），跳过需要
> at-tree 的对照检查。

### 2. Gate 4 — 生成产物校验（结构部分）

```bash
youqu at validate --gate 4 --generate-output tests/at/yaml/
```

### 3. 运行时验证（有 DISPLAY 时）

```bash
youqu at run --testdir tests/at/yaml/
youqu at verify --suite tests/at/yaml/<module>/<module>.suite.yaml --spec-id <id>
```

### 4. 覆盖率报告

```bash
python3 <skill>/scripts/cover.py \
    --element-map tests/casefile/out/element-map.yaml \
    --testdir tests/at/yaml/ \
    --coverage-report tests/at/coverage-report.yaml \
    --threshold 100
```

## 交付说明

**每次生成提交保留一致的产物**。提交到版本控制的是以下成品（固定位置
`tests/at/` 下）：

- `yaml/` — 生成的 suite YAML 目录（`elements.yaml` + `<module>/*.suite.yaml`）
- `element-coverage-manifest.yaml` — 权威元素清单（白名单 + transient + unresolved）
- `coverage-report.yaml` — 覆盖率报告
- `cases_mapped.yaml` — 合并映射文件
- `unreachable.yaml` — 人工豁免清单（如有）

`modules/` 是中间产物，**不纳入提交**（每次重新生成，提交它们会造成版本噪音）。

## 错误处理

| 失败点 | 行为 |
|--------|------|
| 覆盖门禁 FAIL | 补漏循环，直到 100% 或人工豁免 |
| Gate 5 失败 | 停止，检查语义映射 |
| Gate 4 失败 | 停止，检查生成产物 |
| 运行时验证失败 | 降级：标记 suite `status: unstable` |
| 无 DISPLAY | 跳过运行时验证 |
