# Stage 4: Gap-Filling Loop + Verification

> 产物目录固定 `tests/at/`（见 stage-1）。

## 补漏循环（仅当有未覆盖元素）

cover.py 报出未覆盖元素时，进入补漏循环：

1. 读取 `tests/at/coverage-report.yaml` 的 `uncovered_elements` 列表
2. 启动**单 agent** 聚焦生成补充用例（不并行，缺口通常少）
3. 补充用例写入新的 output.json，重新组装 + 覆盖门禁
4. 循环直到 100% 或人工确认不可达

**不可达元素豁免**：条件渲染/动态名等无法覆盖的元素，写入 `tests/at/unreachable.yaml`：

```yaml
unreachable:
  - name: ZoomButton
    reason: 条件渲染，仅特定状态出现
```

人工确认后从分母剔除。**这是 100% 的唯一豁免通道**。

## 验证流程

### 1. Gate 3 — 映射格式校验

```bash
youqu at validate --gate 3 \
    --cases-mapped tests/at/cases_mapped.yaml \
    --at-tree-annotated tests/at/at-tree-annotated.yaml
```

### 2. Gate 5 — 语义安全阀

```bash
youqu at validate --gate 5 --cases-mapped tests/at/cases_mapped.yaml
```

### 3. Gate 4 — 生成产物校验

```bash
youqu at validate --gate 4 \
    --generate-output tests/at/yaml/ \
    --at-tree tests/at/at-tree.yaml
```

### 4. 运行时验证（有 DISPLAY 时）

```bash
youqu at smoke --modules-dir tests/at/yaml/
youqu at verify --suite tests/at/yaml/<module>/<module>.suite.yaml --spec-id <id>
```

### 5. 覆盖率报告

```bash
python3 <skill>/scripts/cover.py \
    --scan-dir tests/at/coverage_scan/ \
    --testdir tests/at/yaml/ \
    --manifest tests/at/coverage-report.yaml \
    --threshold 100
```

## 交付说明

**每次生成提交保留一致的产物**。提交到版本控制的是以下成品（固定位置 `tests/at/` 下）：

- `yaml/` — 生成的 suite YAML 目录（`elements.yaml` + `<module>/*.suite.yaml`）
- `element-coverage-manifest.yaml` — 权威元素清单
- `coverage-report.yaml` — 覆盖率报告
- `cases_mapped.yaml` — 合并映射文件
- `unreachable.yaml` — 人工豁免清单（如有）

`modules/`、`coverage_scan/` 是中间产物，**不纳入提交**（每次由上游重新生成，提交它们会造成版本噪音）。提交时保持上述成品清单一致，避免不同批次提交内容漂移。

## 错误处理

| 失败点 | 行为 |
|--------|------|
| 覆盖门禁 FAIL | 进入补漏循环，直到 100% 或人工豁免 |
| Gate 3 失败 | 停止，检查 cases_mapped.yaml |
| Gate 5 失败 | 停止，检查语义映射 |
| Gate 4 失败 | 停止，检查生成产物 |
| 运行时验证失败 | 降级：标记 `status: unstable` |
| 无 DISPLAY | 跳过运行时验证 |
