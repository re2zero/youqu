# Stage 1: Data Preparation

> 本阶段由确定性脚本自动执行，主 agent 不参与。

**输出目录约定**：本技能所有产物固定写入 `tests/at/`（项目根下）。不要改用其它目录——AI 自行选择输出目录会导致交付物位置漂移，后续阶段找不到产物。参数化的是具体示例值（`<app>`、`<source_dir>`、`<casefile>`），目录结构固定。

默认用 `pipeline_run.py` 一键执行（scan → slice → manifest）：

```bash
python3 <skill>/scripts/pipeline_run.py \
    --app <app> --src <source_dir> \
    --xlsx <casefile.xlsx> --output tests/at/
```

变体：

```bash
# feature-driven（无 xlsx，从需求生成）：仍需 --src 提供元素全集
python3 <skill>/scripts/pipeline_run.py \
    --app <app> --src <source_dir> --output tests/at/

# 复用已有扫描产物：跳过 scan
python3 <skill>/scripts/pipeline_run.py \
    --app <app> --scan-dir tests/at/coverage_scan/ \
    --xlsx <casefile.xlsx> --output tests/at/
```

`pipeline_run.py` 内部依次调用下面三个脚本，也可分步手动执行（需要单独控制某一步时）。

## 各模式跳过逻辑

| 模式 | 跳过 | 原因 |
|------|------|------|
| 标准 | 无 | 全量执行 |
| feature-driven（无 xlsx） | `parse` | 无 xlsx 源；**仍需 `--src` 或 `--scan-dir`**（元素全集来源） |
| 复用扫描产物 | `scan` | 传入 `--scan-dir` |

## 执行内容

### 1. 扫描（at-spi-coverage 技能）

```bash
python3 <skill>/../at-spi-coverage/scripts/coverage_stats.py \
    --src <source_dir> -o tests/at/coverage_report.json
```

产物（`tests/at/coverage_scan/`）：
- `pre_scan_ok.yaml` — C++ 已命名交互控件（`existing_accessible_name`）
- `pre_scan_gaps.yaml` — C++ 缺名控件（动态拼接/未命名，不计入 100% 分母）
- `qml_ok.yaml` / `qml_gaps.yaml` — QML 元素（`accessible_name`）

ok 集是 100% 覆盖门禁的分母（权威元素全集）。

### 2. 切片（pipeline_parse.py）

```bash
python3 <skill>/scripts/pipeline_parse.py \
    --input <casefile.xlsx> \
    --output tests/at/modules/ \
    --app <app> \
    --budget 16000
```

- 绝不生成全量 `cases_raw.yaml`（2000+ 用例爆上下文）；按模块 + token 预算切片
- 每切片 token ≤ 预算（默认 16k）
- 切片后重读所有切片验证用例数 + id 集合与源一致（完整性校验）

产物：
- `tests/at/modules/<slug>_<seq>.input.json` — 每切片一个
- `tests/at/modules/_summary.json` — 切片清单

### 3. 元素清单（element_manifest.py）

```bash
python3 <skill>/scripts/element_manifest.py \
    --scan-dir tests/at/coverage_scan/ \
    --output tests/at/element-coverage-manifest.yaml
```

产物：`tests/at/element-coverage-manifest.yaml` — 权威元素白名单（name + role + source），100% 分母 + selector 白名单。

## 验证（后续阶段输入，出错会级联）

| 检查 | 失败提示 |
|------|----------|
| `coverage_scan/pre_scan_ok.yaml`（或 `qml_ok.yaml`）非空 | 未扫描或 libclang 缺失 |
| `pipeline_parse.py` 输出 "Integrity OK: N/N cases preserved" | 有遗漏/篡改，停止 |
| `element-coverage-manifest.yaml` 的 `elements` 键非空 | 扫描产物缺失 |

## Gotchas

- **openpyxl 必装**（xlsx 模式）：缺失时 `pipeline_parse.py` 直接报错退出。
- **无模块列时按标题聚类**：`_cluster_by_title` 用中文功能动词（打开/保存/缩放…）分组，无法识别关键词的用例归入"其他"。
- **单条超预算用例**：独享一个切片，不拆分不丢弃。
- **`coverage_stats.py` 默认扫 C++ + QML**：不要传 `--cpp-only`，除非确认项目纯 C++。
- **`pipeline_run.py` 强制 `--src` 或 `--scan-dir`**：否则 exit 1（100% 门禁无分母）。

## 产物结构

```
tests/at/
├── coverage_scan/               # 扫描产物
│   ├── pre_scan_ok.yaml
│   ├── pre_scan_gaps.yaml
│   ├── qml_ok.yaml
│   └── qml_gaps.yaml
├── element-coverage-manifest.yaml  # 权威元素清单（100% 分母）
└── modules/                     # 切片输出
    ├── _summary.json
    └── <module>_<seq>.input.json
```
