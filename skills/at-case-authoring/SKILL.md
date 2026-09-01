---
name: at-case-authoring
description: >
  测试用例编写、转换与合规检查技能。面向 Deepin/UOS 桌面应用测试人员：
  按《AT用例编写规范》编写符合自动化要求的测试用例，把存量 xlsx 用例转换为
  标准 YAML 格式供测试人员校对，并校验用例是否符合规范。
  Triggers: 用例编写, 写用例, 用例转换, xlsx转yaml, 用例规范化, 用例合规检查,
  检查用例规范, 用例校对, test case authoring, case validation, element-map,
  界面元素映射表.
version: "0.2.0"
license: MIT
author: Uniontech
---

# AT Case Authoring — 用例编写 / 转换 / 合规检查

## When to Use

| 模式 | 触发 | 输入 → 输出 |
|---|---|---|
| A 编写 | 测试人员写新用例 | 需求 → cases_standard.yaml |
| B 转换 | 存量 xlsx 转标准格式 | xlsx → cases_standard.yaml + element-map.yaml |
| C 检查 | 校验已有用例 | xlsx/yaml + element-map → 合规报告 |

## Boundary

- **Owns**：用例文档的编写规范、xlsx→标准 YAML 转换、合规校验。
- **Does NOT own**：生成 AT-SPI suite（`at-suite-generator`）；补 AccessibleName（`at-spi-completion`）；覆盖率（`at-spi-coverage`）。
- 产出是**测试人员可读/可校对**的用例文档，不是 suite YAML。

## Default Workflow

### 模式 A：编写新用例

1. 读 `references/spec.md`（规则）与 `assets/case-template.yaml`（范本）
2. 产出用例：标题 `【模块】功能_场景`；前置只写状态；步骤一行一动作；预期可断言
3. 步骤中每个 UI 目标追加到 `element-map.yaml`（`ui_name` 测试填，`id_name`/`role` 留给开发）
4. 跑 `scripts/validate_cases.py`，0 error 才交付

### 模式 B：xlsx → 标准 YAML 转换

1. 读 `references/conversion-rules.md`
2. `scripts/convert_xlsx.py` 机械转换，一次产出：
   - `cases_standard.yaml`：`raw_*` 逐字保留原始描述 + 机械预处理到 title/module/steps/expected
   - `slices/`：按模块 + token 预算切分（2000+ 条用例必需，AI 逐片处理）
   - `element-map.yaml`：机械提取 UI 目标初稿（ui_name 候选，id_name/role=TBD）
3. **AI 初步生成**：逐片基于 raw_* 规范化（补【模块】、拆一行动作、去断言词、补输入值），精修 element-map（过滤噪声、补 desc）
4. 测试人员对照 raw_* 校对（AI 是草稿，语义以原始描述为准）
5. `scripts/validate_cases.py` 0 error 才交付

### 模式 C：合规检查

1. 读 `references/checklist.md`
2. `scripts/validate_cases.py` 输出违规清单
3. 逐项修复，或标 `【人工】`+`manual: true`（标记规则见 spec §7）

## Core Rules

- **列级**：标题 `【模块】功能_场景`；前置只写状态；步骤一行一动作；预期可断言。
- **断言词不进步骤**：完整清单见 `references/spec.md` §3.1——命中会被解析器判为断言。
- **描述词不进输入内容**：完整清单见 `references/spec.md` §3.4。
- **UI 目标写屏幕可见文本**，不写代码标识（accessible_id/objectName）。
- **输入必须具体**：禁止"任意字符/很长的字符/任意长度"。
- **测不了的标【人工】**：8 类不可自动化目标见 `references/spec.md` §7，标记规则：`manual: true` 与标题 `【人工】` 必须同时存在。
- **element-map 必填**：用例中每个 UI 目标都要能在表里查到，否则 AI 无法解析。

## Verification

- 每份产出跑 `scripts/validate_cases.py`，0 error（warning 人工确认）
- 转换模式：case_count = 原始数量，raw_* 可还原原始描述
- 用例 + element-map 齐了才算交付

## Resources

| 文件 | 用途 | 何时读 |
|---|---|---|
| `references/spec.md` | 规则全文 | 模式 A/B 必读 |
| `references/conversion-rules.md` | 转换 + 校对细节 | 模式 B 必读 |
| `references/checklist.md` | 检查清单 | 模式 C 必读 |
| `assets/case-template.yaml` | 用例范本 | 模式 A 必读 |
| `assets/element-map-template.yaml` | 映射表范本 | 模式 A/B |
| `scripts/validate_cases.py` | 合规校验 | 三种模式都跑 |
| `scripts/convert_xlsx.py` | xlsx 机械转换 | 模式 B |

> **关键词单一事实源**：`references/spec.md` §3 是关键词白名单的唯一权威（人类可读），`scripts/validate_cases.py` 的实现与它一致。修改任一处，必须同步另一处。
