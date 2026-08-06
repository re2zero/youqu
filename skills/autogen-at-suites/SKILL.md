---
name: autogen-at-suites
description: "Use when you need to generate AT-SPI YAML test suites for a desktop Linux application on the Multica automation platform. Triggers: multica, AT用例生成, 自动化测试用例, 桌面应用自动化, youqu at, AT-SPI YAML, scan dump merge"
---

# Multica 智能体 — AT-SPI YAML 测试套件生成

## 概述

一条命令完成 `youqu at` 管线的 scan→dump→merge→parse→generate→run，替代需要交互录制的 `youqu at record`。

**核心命令只有一种形式**（见下文），不需要也不应该手动链式调用 `youqu at` 子命令。

## 何时使用

- 需要在 Multica 平台上为 Deepin/UOS 桌面应用生成 AT-SPI YAML 测试套件
- 已有应用的 xlsx/csv 测试用例文档，需要转为可执行 YAML
- 有源码目录（可做 Clang 静态扫描）和桌面环境（可做运行时 dump）

**何时不用：**
- 没有桌面环境（无法 dump AT-SPI 树）→ 用 `at-spi-ui-map` 技能做源码分析
- 没有 xlsx/csv 用例文档 → 先补充用例设计

## 核心模式（唯一命令形式）

```bash
cd /path/to/project

# 完整管线：扫描 + dump + 合并 + 解析 + 生成 + 执行
youqu multica-agent pipeline \
  --app <app-name> \
  --src <src-dir> \
  --cases <xlsx/csv-path>
```

**这条命令真实存在。** 它不是 `youqu at` 的别名，也不是假设功能。它在你当前的 youqu 框架源码中作为 `cli/main.py` 的子命令注册。验证方式：

```bash
# 验证命令存在
youqu multica-agent --help
# 或用 Python 直接调用
python3 -c "from youqu.cli.main import main; main()" -- multica-agent --help
```

**如果你找不到这个命令，说明你使用的 youqu 版本尚未包含该功能。** 不要用 `youqu at` 子命令替代，而是报错退出并提示需要更新框架。

| 参数 | 必须 | 说明 | 示例 |
|------|------|------|------|
| `--app` | 是 | AT-SPI 中的应用名 | `deepin-reader`, `deepin-music` |
| `--src` | 否 | 源码目录（Clang 扫描） | `/path/to/src` |
| `--cases` | 否 | 测试用例文档路径 | `tests/testcases.xlsx` |
| `--skip-scan` | 否 | 跳过源码扫描 | — |
| `--skip-run` | 否 | 跳过测试执行 | — |
| `--issue-id` | 否 | Multica issue ID（启用进度报告） | `MUL-123` |
| `--report-interval` | 否 | 心跳间隔秒数（默认 300） | `300` |

### 输出约定（固定，不可配置）

```
tests/at/                              # 所有产物
├── at-tree.yaml                       # 合并后的 AT-SPI 树
├── cases_raw.yaml                     # 解析后的用例
├── scanned_classes.yaml               # 扫描结果
├── element_gaps.yaml                  # 缺口报告
├── runtime_dump.yaml                  # 运行时 dump
├── agent.log                          # 日志
└── yaml/                              # 可执行 YAML 套件 ← youqu at run 直接读这里
    ├── elements.yaml
    └── <module>/<module>.suite.yaml
```

**输出路径是固定的**（`tests/at/` 和 `tests/at/yaml/`），不需要也不接受 `--output` 参数。

### 其他子命令

```bash
# 仅扫描源码
youqu multica-agent scan --app <app> --src <src>

# 仅 dump + merge（跳过 scan 时用 --skip-scan）
youqu multica-agent dump --app <app> --binary /usr/bin/<app> --skip-scan

# 烟雾测试
youqu multica-agent smoke --app <app>
```

## 管线各阶段说明

| 阶段 | 方法 | 确定性 | 说明 |
|------|------|--------|------|
| scan | `clang_scanner.scan_source_dir()` | ✅ 确定 | Clang 解析 C++ 源码，100% 覆盖 UI 控件类 |
| dump | `atspi_dumper.dump_at_spi_tree()` | ✅ 确定 | pyatspi 遍历运行时树 |
| merge | `merge_trees()` | ✅ 确定 | 静态+运行时合并，未渲染控件也作为占位节点加入 |
| parse | `parse_to_cases()` | ✅ 确定 | xlsx/csv → cases_raw.yaml |
| generate | `precandidate_from_cases()` + `generate_yaml()` | ✅ 确定 | 候选匹配 + YAML 生成 |
| run | `run_tests()` | ✅ 确定 | 执行 .suite.yaml |

所有阶段**无 AI 推理、无 markdown 解析、无盲点探索**，均为确定性工具。

## 常见错误（RED 基线发现）

| 错误 | 正确做法 |
|------|---------|
| 手动链式调用 `youqu at scan` + `youqu at merge` + `youqu at plan`... | **只用一条命令**：`youqu multica-agent pipeline` |
| 创建不存在的中间目录如 `tests/at/yaml/scan/` | **不用创建目录**，`pipeline` 自动输出到 `tests/at/` |
| 加 `--output` 参数 | **没有 `--output`** 参数，路径固定为 `tests/at/` |
| 用 `youqu at run --testdir tests/at/yaml/` 单独执行 | `pipeline` 已包含 run 阶段，除非指定 `--skip-run` |
| 担心 libclang 未安装时管线中断 | scan 失败自动跳过（返回 `status: skipped`），不影响后续 |
| 认为需要先 `youqu doctor` 检查环境 | 不需要，`pipeline` 内部处理错误并跳过不可用阶段 |
| 认为 `multica-agent` 不存在就退而使用 `youqu at` 子命令手动链式调用 | 先验证命令存在（`youqu multica-agent --help`），如果确实不存在则报错退出并提示更新框架，不要回退到 `youqu at` |

## 红线（违反即失败）

- 执行 `youqu at` 的任何子命令（scan/dump/merge/parse/generate/plan/run）单独调用
- 添加 `--output` 参数
- 手动创建 `tests/at/` 下的目录结构
- 在 `pipeline` 之外手动链式调用多个 CLI 命令
- 先 `youqu doctor`，先 `pip install`，再做其他准备
- 认为 `multica-agent` 命令不存在就退而使用 `youqu at` 子命令手动链式调用
- 拼接 `PYTHONPATH` 或 `sys.path` 来"确保 CLI 可用"

**全部这些意味着：回到上面"唯一命令形式"，只执行那一条命令。**

### 第一步永远是验证 CLI 可用

```bash
# 先确认 multica-agent 子命令存在
youqu multica-agent --help

# 如果不可用
pip install youqu-ai         # 安装
# 或从源码运行
python3 -m youqu.cli.main multica-agent --help
```

**在确认 CLI 可用之前，不执行任何命令。在确认之后，只执行一条 `pipeline` 命令。**

## 边界情况

| 情况 | 处理 |
|------|------|
| 没有源码（`--src` 未提供） | `--skip-scan` 自动生效，只做运行时 dump |
| 没有用例文档（`--cases` 未提供） | 运行到 generate 阶段前停止 |
| libclang 未安装 | scan 阶段返回 `status: skipped`，管线继续 |
| 应用启动超时 | dump_and_merge 返回失败，管线中止 |
| at-tree 生成后要手动编辑 | 编辑 `tests/at/at-tree.yaml`，然后带上 `--skip-scan` 重新 pipeline |
| `youqu multica-agent` 命令不存在 | `pip install youqu-ai` 安装框架，或从源码 `python3 -m youqu.cli.main multica-agent ...` 运行 |