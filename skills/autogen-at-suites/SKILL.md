---
name: autogen-at-suites
description: "Use when you need to generate AT-SPI YAML test suites for a desktop Linux application on the Multica automation platform. Triggers: multica, AT用例生成, 自动化测试用例, 桌面应用自动化, AT-SPI YAML, scan dump merge"
---

# Multica 智能体 — AT-SPI YAML 测试套件生成

## 概述

一条命令完成源码扫描、运行时 dump、合并、用例解析、YAML 套件生成和执行的全流程，替代需要人工交互的录制方式。

**核心命令只有一种形式**（见下文）。不需要也不应该手动链式调用多个子命令。

## 何时使用

- 需要为 Deepin/UOS 桌面应用生成 AT-SPI YAML 测试套件
- 已有应用的 xlsx/csv 测试用例文档，需要转为可执行 YAML
- 有源码目录（可做 Clang 静态扫描）和桌面环境（可做运行时 dump）

**何时不用：**
- 没有桌面环境（无法 dump AT-SPI 树）→ 用 `at-spi-ui-map` 技能做源码分析
- 没有 xlsx/csv 用例文档 → 先补充用例设计

## 核心命令

```bash
cd /path/to/project

# 完整管线：扫描 + dump + 合并 + 解析 + 生成 + 执行
youqu multica-agent pipeline \
  --app <app-name> \
  --src <src-dir> \          # 可选，有此参数则做 Clang 静态扫描
  --cases <xlsx/csv-path>    # 可选，无此参数则管线到 generate 阶段前停止
```

`youqu multica-agent` 是 `youqu` 框架的 CLI 子命令。验证方式：

```bash
youqu multica-agent --help
```

| 参数 | 必须 | 说明 | 示例 |
|------|------|------|------|
| `--app` | 是 | AT-SPI 中的应用名 | `deepin-reader`, `deepin-music` |
| `--src` | 否 | 源码目录（Clang 扫描） | `/path/to/src` |
| `--cases` | 否 | 测试用例文档路径 | `tests/testcases.xlsx` |
| `--skip-scan` | 否 | 跳过源码扫描 | — |
| `--skip-run` | 否 | 跳过测试执行 | — |
| `--issue-id` | 否 | Multica issue ID（启用进度报告） | `MUL-123` |
| `--report-interval` | 否 | 心跳间隔秒数（默认 300） | `300` |

### 输出产物

```
tests/at/                              # 所有产物
├── at-tree.yaml                       # 合并后的 AT-SPI 树
├── cases_raw.yaml                     # 解析后的用例（仅当提供 --cases）
├── scanned_classes.yaml               # 扫描结果（仅当提供 --src）
├── element_gaps.yaml                  # 缺口报告（仅当提供 --src，框架内部使用）
├── runtime_dump.yaml                  # 运行时 dump
├── suite-cases.yaml                   # 预选候选结果
├── at-tree-compact.yaml               # 精简 at-tree
├── agent.log                          # 日志
└── yaml/                              # 可执行 YAML 套件
    ├── elements.yaml                  # 运行时元素查询表，用例执行依赖此文件
    └── <module>/<module>.suite.yaml   # 各模块的测试套件
```

**输出路径固定为 `tests/at/` 和 `tests/at/yaml/`**，不接受 `--output` 参数。

`elements.yaml` 由 `generate` 阶段自动生成，是 AT-SPI 元素的定位锚点表。`yaml/` 下的每个 `.suite.yaml` 在运行时通过向上搜索找到它，所有步骤的 `ref` 解析都依赖此文件。没有它用例无法执行。

`element_gaps.yaml` 记录静态扫描发现的缺 `setAccessibleName()` 的控件类，供框架内部使用，LLM 不需要处理。

## 管线阶段

| 阶段 | 说明 |
|------|------|
| scan | Clang 解析 C++ 源码，提取全部 UI 控件类。无 `--src` 或 libclang 不可用时自动跳过 |
| dump | 启动应用，pyatspi 遍历运行时 AT-SPI 树 |
| merge | 静态+运行时合并。未渲染控件也作为占位节点加入，保证 100% 覆盖 |
| parse | xlsx/csv → cases_raw.yaml 格式转换 |
| generate | 候选匹配 + YAML 生成，输出到 `tests/at/yaml/` |
| run | 执行 `.suite.yaml` 测试 |

所有阶段均为确定性工具，不依赖 AI 推理。

## 常见错误

| 错误 | 正确做法 |
|------|---------|
| 手动链式调用 `youqu at scan` + `youqu at merge` + ... | **只用一条命令**：`youqu multica-agent pipeline` |
| 创建中间目录如 `tests/at/yaml/scan/` | **不用创建目录**，`pipeline` 自动输出到 `tests/at/` |
| 加 `--output` 参数 | **没有 `--output`** 参数，路径固定为 `tests/at/` |
| 认为需要先 `youqu doctor` 检查环境 | 不需要，`pipeline` 内部处理错误并跳过不可用阶段 |
| libclang 未安装时担心管线中断 | scan 自动跳过（返回 `status: skipped`），不影响后续 |

## 红线

- 执行 `youqu at` 的任何子命令（scan/dump/merge/parse/generate/plan/run/verify/smoke）单独调用
- 添加 `--output` 参数
- 手动创建 `tests/at/` 下的目录结构
- 手动链式调用多个 CLI 命令
- 执行 `youqu doctor` 或 `pip install` 做环境准备
- 拼接 `PYTHONPATH` 或 `sys.path` 来"确保 CLI 可用"

**全部违反即失败。回到上面"核心命令"部分，只执行那一条命令。**

## 边界情况

| 情况 | 处理 |
|------|------|
| 没有源码（`--src` 未提供） | `--skip-scan` 自动生效，只做运行时 dump |
| 没有用例文档（`--cases` 未提供） | 运行到 generate 阶段前停止 |
| libclang 未安装 | scan 阶段返回 `status: skipped`，管线继续 |
| 应用启动超时 | dump_and_merge 返回失败，管线中止 |
| at-tree 生成后要手动编辑 | 编辑 `tests/at/at-tree.yaml`，然后带 `--skip-scan` 重新 pipeline |
| `youqu multica-agent` 命令不存在 | 框架版本过低，需要先更新框架再执行本技能 |