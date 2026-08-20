# Stage 1: Data Preparation

> 本阶段由 `pipeline_run.py` 自动执行，主 agent 不参与。
> 仅当脚本不可用时（如 missing CLI），才需要手动执行。

## 各模式跳过逻辑

| 模式 | 跳过 | 原因 |
|------|------|------|
| 标准 | 无 | 全量执行 |
| auto / headless | `dump` | 无 DISPLAY |
| 仅 feature-driven（无 xlsx） | `parse`、`docs`、`plan` | 无 xlsx 源 |
| 复用已有 at-tree | `scan`、`dump`、`merge` | 传入 `--at-tree` |

## 产物

| 产物 | 生成者 | 谁读 | 命名策略 |
|------|--------|------|----------|
| `cases_raw.yaml` | `youqu at parse` | Stage 2/3（通过 input.json） | 固定名覆盖 |
| `plan.yaml` | `youqu at parse`（自动生成） | `pipeline_prep.py` | 固定名覆盖 |
| `at-tree.yaml` | `youqu at merge` 或 `scan_to_atree.py` | Stage 2/3 | 固定名覆盖 |
| `at-tree-annotated.yaml` | `youqu at tree-info` | Stage 2/3 | 固定名覆盖 |
| `modules/*.input.json` | `pipeline_prep.py` | Stage 3（子 agent） | 每次重生成 |
| `modules/_summary.json` | `pipeline_prep.py` | 主 agent | 每次重生成 |

## 手动执行命令

```bash
# 1. Parse xlsx → cases_raw.yaml + plan.yaml
youqu at parse --input tests/at/casefile/用例.xlsx --output tests/at/cases_raw.yaml

# 2. 导入帮助文档
youqu at docs deepin-reader --output tests/at/docs/

# 3. 静态扫描
youqu at scan --src /path/to/source --app deepin-reader --output tests/at/scan/

# 4. 有 DISPLAY 时 dump
youqu at dump dtk --app deepin-reader --launch /usr/bin/deepin-reader --output tests/at/dump/

# 5. 合并
youqu at merge --scan tests/at/scan/ --record tests/at/dump/ --output tests/at/

# 6. 生成 AI 标注用结构化 YAML
youqu at tree-info --at-tree tests/at/at-tree.yaml --output tests/at/at-tree-annotated.yaml --format yaml

# 7. 模块切分
python3 skills/at-case-generator/scripts/pipeline_prep.py \
    --plan tests/at/plan.yaml \
    --cases tests/at/cases_raw.yaml \
    --output tests/at/modules/ \
    --app deepin-reader
```

## 最终产物结构

```
tests/at/
├── at-tree.yaml               # 合并后的 AT 元树
├── at-tree-annotated.yaml     # AI 标注用结构化 YAML
├── cases_raw.yaml             # 原始用例（格式转换后）
├── plan.yaml                  # 模块 → case_ids 映射
├── docs/                      # 帮助文档分章
├── scan/                      # 静态扫描结果
├── dump/                      # 运行时 dump（有 DISPLAY 时）
└── modules/                   # 模块切分输出
    ├── _summary.json          # 模块汇总
    ├── <slug_1>.input.json    # 模块 1
    └── <slug_N>.input.json    # 模块 N
```