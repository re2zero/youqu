# Stage 1: Data Preparation

> 本阶段由确定性脚本自动执行，主 agent 不参与。

**输出目录约定**：本技能所有产物固定写入 `tests/at/`（项目根下）。运行前如
`tests/at/` 下已有旧产物（suite-cases.yaml / cases_mapped.yaml / yaml/* 等），
先备份再生成，避免新旧混放。

## 前置条件：at-case-authoring 模式 B 产物

本技能不解析 xlsx、不扫描源码。必须有：

- `cases_standard.yaml`（AI 规范化全量）或 `normalized/*.yaml`（按模块规范化，
  含 `manual`/`reason`）— 规范用例
- `element-map.yaml` — 元素映射表（`id_name` = 运行时 AT-SPI 名）

> **不要用 `slices/`**：那是 at-case-authoring 的机械切分产物，manual 全为
> false，缺 AI 规范化标记，会丢失不可自动化信息。用 `normalized/`。

## 1. 用例 → input.json（parse_cases_standard.py）

```bash
python3 <skill>/scripts/parse_cases_standard.py \
    --input tests/at/casefile/out/cases_standard.yaml \
    --output tests/at/modules/ --app deepin-screen-recorder

# 或直接用 normalized/（AI 规范化后按模块，含 manual/reason）
python3 <skill>/scripts/parse_cases_standard.py \
    --input tests/at/casefile/out/normalized/ \
    --output tests/at/modules/ --app deepin-screen-recorder
```

- 整模块一片（`modules/<slug>_<seq>.input.json`），token 保护不做语义重切。
- 完整性校验：重读所有切片验证用例数 + id 集合与源一致。
- 产物：`modules/*.input.json` + `modules/_summary.json`（含每模块 manual_count）。

## 2. 元素清单（element_manifest.py）

```bash
python3 <skill>/scripts/element_manifest.py \
    --element-map tests/at/casefile/out/element-map.yaml \
    --output tests/at/element-coverage-manifest.yaml
```

产物 `tests/at/element-coverage-manifest.yaml`：

- `elements` — 持久命名元素（100% 分母 + selector 白名单）
- `transient_items` — 菜单 / 菜单项（role=menu / menu item，排除出分母）
- `unresolved` — id_name TBD/空（运行时无法按名定位，**不进分母**；文档性
  清单，供开发补名）

> **术语区分**（勿混淆）：
> - `unresolved`（清单段）= id_name TBD/空 → 不进分母，待补名。
> - `unreachable.yaml`（用户文件）= **已命名**但运行时不可达元素的人工豁免 →
>   由 cover.py 消费。
> 二者用途不同，不可互换。

## 验证（后续阶段输入，出错会级联）

| 检查 | 失败提示 |
|------|----------|
| `modules/_summary.json` 存在且 total_cases 与源一致 | 有遗漏/篡改，停止 |
| `element-coverage-manifest.yaml` 的 `elements` 键非空 | element-map 缺失或全 TBD |

## Gotchas

- **`module` 字段是切分依据**：cases_standard 的 `module` 可能很杂（如
  "AI全量" / "V25新需求" / "1070-新需求"），直接作为模块名，slug 冲突自动
  加序号唯一化。
- **manual_count**：`_summary.json` 记录每模块 manual 用例数，Stage 2 主 agent
  据此预判 unsupported 规模。
- **不要改 modules/ 文件名**：assemble 按 `<slug>_<seq>.output.json` 对应读取。
