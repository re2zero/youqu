---
name: at-case-generator
version: "2.0.0"
description: >
  Use when generating AT-SPI test suites from xlsx/csv test case documents
  or from feature requirements for a Linux desktop application. Generates
  executable YAML suite files ready for `youqu at run`. Supports three modes:
  standard (xlsx + scan + dump), auto/headless (no DISPLAY), and
  feature-driven (no xlsx, from PR/issue). Triggers: AT用例生成, at-case
  generation, AT suite generation, AT-SPI suite YAML, at-tree用例,
  桌面应用AT测试, AT自动化用例, youqu at parse, youqu at generate,
  youqu at tree-info, 自动生成, 无record, multica.
---
# AT Case Generator v2.0

## Overview

**输入**: xlsx/csv 测试用例文档（或 feature 需求）+ 源代码 + 应用二进制
**处理**: 确定性管线（pipeline_run.py）→ AI 子 agent 池（context-bundle + 每模块并行映射）→ 确定性验证（pipeline_assemble.py + Gate 3/4/5）
**输出**: 可执行的 AT-SPI `*.suite.yaml` + `elements.yaml` + `cases_mapped.yaml`

**关键约束**:
- 脚本做确定性操作，AI 只做语义理解。每阶段 AI 工作由独立的子 agent 执行，上下文零混杂。
- 模块是语义映射的单位。每个模块 15-30 条用例，子 agent 独立映射，互不干扰。

## 用法

```bash
# 标准模式（xlsx + 有 DISPLAY）
python3 skills/at-case-generator/scripts/pipeline_run.py \
    --app deepin-reader --src /path/to/source \
    --xlsx tests/at/casefile/用例.xlsx \
    --binary /usr/bin/deepin-reader \
    --output tests/at/

# headless 模式（无 DISPLAY）
python3 skills/at-case-generator/scripts/pipeline_run.py \
    --app deepin-reader --src /path/to/source \
    --xlsx tests/at/casefile/用例.xlsx \
    --output tests/at/ --headless

# 复用已有 at-tree（跳过 scan/dump/merge）
python3 skills/at-case-generator/scripts/pipeline_run.py \
    --app deepin-reader --xlsx tests/at/casefile/用例.xlsx \
    --at-tree tests/at/at-tree.yaml \
    --output tests/at/

# 仅 feature-driven（无 xlsx）
python3 skills/at-case-generator/scripts/pipeline_run.py \
    --app deepin-terminal --src /path/to/source \
    --output tests/at/ --headless
```

## 模式判定

| 条件 | 模式 | 跳过阶段 | 子 agent 数 |
|------|------|----------|-------------|
| 有 xlsx + 有 DISPLAY + 有 --binary | 标准 | 无 | 0-1 (UI图谱) + 1 (context) + N (模块数) |
| 有 xlsx + 无 DISPLAY | auto / headless | dump | 0-1 (UI图谱) + 1 (context) + N (模块数) |
| 无 xlsx | feature-driven | parse, docs, plan | 0-1 (UI图谱) + 1 (context) + 1 (合成) |
| 有 --at-tree | 复用 AT 树 | scan, dump, merge | 0-1 (UI图谱) + 1 (context) + N (模块数) |

## 主流程

### 前置阶段: UI 图谱推导（可选，子 agent 执行）

在管线启动前，可先执行 UI 图谱推导。启动一个 **子 agent** 执行 `at-spi-ui-map` 技能，通过 codebase MCP 从源码推导 UI 结构，产出三件套到 `tests/at/`：
- `ui-map.md` — 组件 mermaid 图 + 控件表 + 菜单/对话框/快捷键索引
- `expected-at-spi-elements.md` — 完整预期元素清单 + 推导链
- `at-spi-implementation-checklist.md` — 缺口明细 + 修复代码模板

三件套在 Stage 2 被 context-bundle 子 agent 读取，用于增强断言质量。
MCP 不可用时跳过，不影响管线执行。

子 agent 任务模板见 `at-spi-ui-map` 技能。本技能不重复其内容。

### 阶段 0: 模式判定（主 agent 执行）

读取 `--at-tree`、`--xlsx`、`--binary`、`DISPLAY` 环境变量，判断当前模式。模式判定一次，贯穿全流程。

### 阶段 1: 数据准备 — 确定性操作（由 `pipeline_run.py` 自动执行）

见 `references/stage-1-prep.md`

执行内容：
- parse → cases_raw.yaml
- docs → 帮助文档分章
- scan → 静态源码扫描
- dump → 运行时 AT-SPI 抓取（有 DISPLAY 时）
- merge → at-tree.yaml
- tree-info → at-tree-annotated.yaml
- pipeline_prep.py → per-module input.json

### 阶段 2: 上下文包生成 — AI 子 agent（1 个子 agent）

见 `references/stage-2-context.md`

启动一个子 agent，读取 `at-tree-annotated.yaml` + `ui-map.md` + `expected-at-spi-elements.md` + `docs/`，生成 `context-bundle.md`（三张表）。

### 阶段 3: 语义映射 — AI 子 agent 池（N 个子 agent，并行）

见 `references/stage-3-mapping.md` + `templates/at-case-mapping-prompt-template.md`

对于 `modules/` 目录下的每个 `*.input.json`，启动一个子 agent 执行语义映射。子 agent 读取：
- `modules/<module_short>.input.json`（该模块的 cases，如 `交互_键盘.input.json`）
- `context-bundle.md`（上下文包）
- `at-tree-annotated.yaml`（AT 树）

输出 `modules/<module_short>.output.json`。

**feature-driven 模式**：只有一个模块，子 agent 读取 `cases_raw.yaml` 替代 `input.json`。

### 阶段 4: 组装 + 校验 — 确定性操作（由 `pipeline_assemble.py` 自动执行）

见 `references/stage-4-assemble.md`

```bash
python3 skills/at-case-generator/scripts/pipeline_assemble.py \
    --modules tests/at/modules/ \
    --output tests/at/ \
    --at-tree tests/at/at-tree.yaml \
    --generate-mapped tests/at/cases_mapped.yaml
```

### 阶段 5: 验证 + 交付

见 `references/stage-5-verify.md`

执行 Gate 3/5/4 校验 → 运行时验证（有 DISPLAY 时）→ 覆盖率报告 → 交付


## 管线纲领

### 设计哲学

**脚本做确定性操作，AI 只做语义理解。** 凡可脚本化的动作（抓取/校验/推送/状态）写成脚本，AI 不手做。
AI 的职责仅限于：理解上下文、做语义映射、生成结构化输出。脚本的职责是：抓取数据、校验格式、组装产物、运行测试。

### 上下文隔离原则

每阶段 AI 工作由独立子 agent 执行，上下文零混杂：
- 原始信息源（ui-map.md、docs/*.md、expected-at-spi-elements.md）**只在 Stage 2 读取一次**，蒸馏为 context-bundle.md
- Stage 3 投入 context-bundle.md + at-tree-annotated.yaml 作为参考，LLM 自选相关行
- context-bundle.md 格式以表格为主（token 效率高、歧义低），禁止大段 prose
- 各模块间互不影响，一条映射错误不扩散
- Stage 2 子 agent 不读 Stage 3 的映射规则，Stage 3 子 agent 不读 Stage 2 的上下文包生成规则

### 可追溯性链

```
at-tree.comment ↔ context-bundle.元素-功能对照表 ↔ output.json.suite.annotation.AT元素引用 ↔ suite.yaml.suites[].steps[].selector.name
```

每个环节的引用关系可双向回溯：从最终 suite.yaml 的 selector.name 可追溯到 at-tree 中的原始元素定义。

### 质量保障链

四层防御：
1. **语义层** — context-bundle 的元素-功能映射表确保断言有具体目标
2. **规范层** — at-mapping-rules 确保四字段拆解、selector 优先级、菜单二分等规则被遵守
3. **门禁层** — Gate 5 语义安全阀检测描述文本当输入、缺前置触发、缺 selector 等常见错误
4. **代码层** — pipeline_assemble.py JSON Schema 校验 + 执行器 fail-fast

### 通过率标准

运行时验证通过率 ≥80% 确认可执行；<80% 标注失败原因不阻塞。

## 产物清单

| 产物 | 路径 | 生成者 | 谁读 | 命名策略 |
|------|------|--------|------|----------|
| ui-map.md | `tests/at/ui-map.md` | 前置阶段子 agent | Stage 2 子 agent | 固定名覆盖 |
| expected-at-spi-elements.md | `tests/at/expected-at-spi-elements.md` | 前置阶段子 agent | Stage 2 子 agent | 固定名覆盖 |
| at-spi-implementation-checklist.md | `tests/at/at-spi-implementation-checklist.md` | 前置阶段子 agent | 报告摘要输出（主 agent） | 固定名覆盖 |
| cases_raw.yaml | `tests/at/cases_raw.yaml` | `pipeline_run.py` | Stage 3（子 agent） | 固定名覆盖 |
| plan.yaml | `tests/at/plan.yaml` | `pipeline_run.py` | pipeline_prep.py | 固定名覆盖 |
| at-tree.yaml | `tests/at/at-tree.yaml` | `pipeline_run.py` | Stage 2/3（子 agent） | 固定名覆盖 |
| at-tree-annotated.yaml | `tests/at/at-tree-annotated.yaml` | `pipeline_run.py` | Stage 2/3（子 agent） | 固定名覆盖 |
| context-bundle.md | `tests/at/context-bundle.md` | Stage 2 子 agent | Stage 3 子 agent | 固定名覆盖 |
| modules/*.input.json | `tests/at/modules/*.input.json` | `pipeline_run.py` | Stage 3 子 agent | 每次重生成 |
| modules/*.output.json | `tests/at/modules/*.output.json` | Stage 3 子 agent | pipeline_assemble.py | 每次重生成 |
| yaml/elements.yaml | `tests/at/yaml/elements.yaml` | `pipeline_assemble.py` | AT-SPI 执行器 | 固定名覆盖 |
| yaml/<module>/*.suite.yaml | `tests/at/yaml/<module>/*.suite.yaml` | `pipeline_assemble.py` | AT-SPI 执行器 | 固定名覆盖 |
| cases_mapped.yaml | `tests/at/cases_mapped.yaml` | `pipeline_assemble.py` | Gate 3/5 校验 | 固定名覆盖 |

| 阶段 | 文件 | 用途 |
|------|------|------|
| 前置 | `at-spi-ui-map` 技能 | UI 图谱推导（可选，子 agent 执行） |
| 前置 | `tests/at/ui-map.md` | 组件图 + 控件表（前置阶段子 agent 产出） |
| 前置 | `tests/at/expected-at-spi-elements.md` | 预期元素清单（前置阶段子 agent 产出） |
| 前置 | `tests/at/at-spi-implementation-checklist.md` | 缺口清单（前置阶段子 agent 产出） |
| 0 | 模式判定（主 agent 内置） | 读取 CLI args + DISPLAY 判断模式 |
| 1 | `references/stage-1-prep.md` | 数据准备：脚本执行 + 手动 CLI 参考 |
| 1 | `scripts/pipeline_run.py` | 确定性管线主脚本 |
| 1 | `scripts/pipeline_prep.py` | 模块切分 |
| 1 | `scripts/scan_to_atree.py` | headless 时静态合成 at-tree.yaml |
| 2 | `references/stage-2-context.md` | 子 agent 任务模板 + 执行规则 |
| 2 | `templates/context-bundle-prompt-template.md` | 子 agent 详细 prompt |
| 3 | `references/stage-3-mapping.md` | 子 agent 任务模板 + 动作类型表 + 禁止清单 |
| 3 | `templates/at-case-mapping-prompt-template.md` | 子 agent 详细 prompt |
| 3 | `templates/at-case-mapping-output-schema.json` | 输出 JSON Schema |
| 4 | `references/stage-4-assemble.md` | 组装 + 校验规则 |
| 4 | `scripts/pipeline_assemble.py` | 组装主脚本 |
| 5 | `references/stage-5-verify.md` | 验证 + 交付流程 |
| 5 | `scripts/coverage_report.py` | 覆盖率报告 |

| 动作 | 工具 | 说明 |
|------|------|------|
| 运行 `pipeline_run.py` | `bash` | 确定性操作，子进程执行 |
| 运行 `pipeline_assemble.py` | `bash` | 确定性操作，子进程执行 |
| 运行 `youqu at validate` | `bash` | 确定性校验，子进程执行 |
| 运行 `youqu at smoke/run` | `bash` | 运行时验证，子进程执行 |
| 运行 `youqu at generate` | `bash` | 已废弃，仅作参考 |
| 读文件 | `read` | 所有阶段 |
| 写文件 | `write` | 仅子 agent 写 output.json |
| 启动子 agent | `eval().agent()` | 前置阶段（UI 图谱）、Stage 2 和 Stage 3 |

### 禁止清单

| 禁止动作 | 理由 |
|----------|------|
| 主 agent 直接读 `input.json` 做映射 | 上下文混杂，降低映射质量。必须用子 agent |
| 跳过 `pipeline_run.py` 手动执行分段 CLI | 脚本确保确定性，手动执行易遗漏步骤 |
| 在映射阶段写 Python 脚本做模式匹配 | 已知失败模式：7% selector 覆盖率、0% 断言覆盖率 |
| 将 `modules/` 目录纳入交付物 | 中间产物，可重生成，不应包含在最终交付物中 |
| 合并多个阶段的子 agent 到同一个 | 上下文混杂，Stage 2 和 Stage 3 的规则互相干扰 |
| 在 `keyboard_type` 中使用描述文本 | 如 `text: "任意长度字符"` 应改为 `text: "test_input_123"` |
| 使用 `element_action` 点击菜单项 | 菜单项瞬态弹出，运行时找不到 |
| 修改 `pipeline_assemble.py` 的校验规则绕过 Gate 5 | 安全阀，不能绕过 |

## 错误处理表

| 失败点 | 行为 |
|--------|------|
| 前置阶段 UI 图谱子 agent 失败 | 不阻塞：跳过图谱，Stage 2 不使用 ui-map.md/expected-at-spi-elements.md |
| MCP 不可用 | 不阻塞：跳过图谱，报告中标注 |
| `pipeline_run.py` 执行失败 | 停止，检查错误输出 |
| 无 xlsx 且无 plan.yaml | 降级为 feature-driven 模式 |
| 无 DISPLAY 且无 at-tree.yaml | 降级：使用 `scan_to_atree.py` 静态合成 |
| 无 at-tree-annotated.yaml | 降级：跳过 Stage 2，不使用 context-bundle |
| 子 agent 映射失败（某模块） | 不阻塞：跳过该模块，标记为 `status: skipped` |
| 某模块 output.json 校验失败 | 不阻塞：跳过该模块，打印错误 |
| 某模块 0 条用例通过校验 | 停止：整模块映射失败，需要重试 |
| Gate 3 校验失败 | 停止，修复 cases_mapped.yaml |
| Gate 5 校验失败 | 停止，修复语义映射问题 |
| Gate 4 校验失败 | 停止，检查生成产物 |
| 运行时验证失败 | 降级：标记为 `status: unstable`，说明原因 |
| 覆盖率报告异常 | 不阻塞，继续 |
| 无 DISPLAY 无法运行 | 降级：跳过运行时验证，后续通知人工验证 |

## 前置依赖

| 依赖 | 安装命令 | 可选 |
|------|----------|------|
| Python >= 3.10 | 系统自带 | 必选 |
| `youqu` CLI | `pip install youqu-ai` | 必选 |
| PyYAML | `pip install pyyaml` | 必选 |
| libclang Python 绑定 | `sudo apt install python3-clang-18 libclang-18-dev` | 可选（静态扫描用） |
| python-xlib | `pip install python-xlib` | 可选（X11 录制用） |
| evdev | `pip install evdev` | 可选（Wayland 录制用） |
| xdotool | `sudo apt install xdotool` | 可选（X11 键鼠用） |
| ydotool | `sudo apt install ydotool` | 可选（Wayland 键鼠用） |

## Verification Checklist

- [ ] frontmatter 合规（name/description/触发词位置）
- [ ] 所有引用的 references/templates/scripts 存在且可读
- [ ] 主文件无阶段细节，无模糊词（grep "尽量|适当|建议" 应为零命中）
- [ ] 模拟正常路径走一遍：标准模式 → auto 模式 → feature-driven 模式
- [ ] 错误处理表中无"提交"相关动作（git 操作不在技能范围内）
- [ ] 核心原则、禁止清单、错误处理表三者无矛盾
- [ ] 产物清单与 stages 中实际写入动作一一对应