---
name: autogen-at-suites
version: "1.2.0"
description: >
  Use when generating AT-SPI YAML test suites automatically in Multica,
  headless, CI, or any environment where `youqu at record` is unavailable or
  the request contains auto/自动/无record. This is a thin alias for
  at-case-generator's auto mode.
  Triggers: multica, auto, 自动, 无record, 自动生成, AT自动化生成, AT-SPI YAML,
  桌面应用AT, 无显示环境AT
---

# Autogen AT Suites（auto / 自动 / 无 record 场景别名）

本技能是 `at-case-generator` 的 **auto / 自动 / 无 record 通用场景** 别名，不再维护独立管线。

## 使用方法

直接加载 `at-case-generator`，按其中的 **“场景变体：auto / 自动 / 无 record 模式（通用）”** 执行。

触发条件（满足任一即可）：

- 用户/任务中出现 `auto`、`自动`、`自动生成`、`无 record`、`不需要录制`、`跳过 record`
- 调用方是 Multica
- 环境是 headless / CI / 无人工操作条件

```
at-case-generator 标准管线
  parse → scan → record → merge → tree-info → AI标注 → AI规范化 → AI映射 → generate → validate
                     ↓
  auto 模式只替换这一段：scan + dump + merge（或 scan → scan_to_atree.py），不需要人工 record
```

## 核心约定

- **自动化只替代 AT 元树获取**，其余步骤与 `at-case-generator` 完全一致。
- AI 元素标注（P2.5）、AI 用例规范化（P2.7）、AI 语义映射（P3）必须由 AI 完成。
- **禁止** `ai_mapper.py`、正则脚本、脚本后处理代替 AI 映射。
- 参考文件全部沿用 `at-case-generator/references/`：
  - `pipeline-reference.md`
  - `suite-format.md`
  - `pitfalls.md`

## 常用命令

```bash
# 有 DISPLAY / 可启动应用时
youqu at scan --src <src_dir> --app <app> --output scan_output/
youqu at dump dtk --app <app> --launch <binary> --output dump_output/
youqu at merge --scan scan_output/ --record dump_output/ --output .

# 无 DISPLAY / headless 时
youqu at scan --src <src_dir> --app <app> --output scan_output/
python3 skills/autogen-at-suites/scripts/scan_to_atree.py scan_output/ <app> at-tree.yaml
```

之后按 `at-case-generator` 继续：`tree-info → AI 标注 → AI 规范化 → AI 映射 → generate → validate → run`。
