# Web Spec 执行能力接入 YouQu 架构决策

## 背景

YouQu 当前支持 AT-SPI YAML 测试用例：通过 `youqu at` 管道 (scan → record → merge → parse → tree-info → split → docs → precandidate → validate → generate → run) 生成并执行 YAML 用例。该链路面向 Linux 桌面自动化，核心依赖 AT-SPI、Dogtail、MouseKey、OCR、DBus、`at-tree.yaml` 等能力。

另一个本地仓库 `uos-ai-test` 提供了一套面向 Web 项目的结构化 spec 执行能力，核心是 Playwright 确定性 runner：加载 YAML spec，解析 DOM locator，执行 Web action/assertion，并输出 JSON/HTML 报告和截图。

本方案只讨论把 `uos-ai-test` 的 **spec 确定性执行部分** 接入 YouQu。`uos-ai-test` 中的 PMS 导入、自然语言用例执行、AI ReAct、批量 PMS 用例运行、模型配置等非 spec 链路不纳入本次整合范围。

本方案目标是从整体架构上定义如何把 `uos-ai-test` 的 Web spec 执行能力接入 YouQu，保证可落地、边界清晰，并避免污染现有桌面 YAML 用例体系。

## 决策

采用 **新增 Web spec engine，并复用 YouQu 外壳** 的方案。

也就是说：

- 当前 `src/yaml_test` 保持为桌面 YAML engine。
- 新增 `src/web_spec` 作为 Web spec engine。
- Web spec engine 只参考并吸收 `uos-ai-test` 的 spec model、loader、locator resolver、action executor、assertion executor、deterministic runner、reporter。
- 不迁移 `uos-ai-test` 的 PMS、AI ReAct、模型调用、自然语言用例执行、导入命令等非 spec 能力。
- CLI、MCP、JobManager、配置和报告目录尽量复用 YouQu 现有体系。
- 第一阶段不强行抽象统一 `SpecEngine`，但按未来可抽象的边界设计模块。

整体关系：

```text
YouQu
├── 统一外壳
│   ├── CLI
│   ├── MCP
│   ├── JobManager
│   ├── config
│   └── report/artifact
│
├── desktop_yaml engine
│   └── 当前 src/yaml_test
│
└── web_spec engine
    └── 新增 src/web_spec
```

## 当前桌面 YAML 集成方式

当前 AT-SPI YAML 链路如下：

```text
youqu at scan/record/merge/generate
  -> 生成 tests/at/yaml/*.suite.yaml

youqu at run
  -> 执行 AT-SPI YAML 测试

parser + executor
  -> 解析 SuiteSpec / ActionStep
  -> 加载 at-tree.yaml

executor
  -> setup / steps / teardown
  -> Dogtail / MouseKey / DBus / OCR / image / process

MCP tools
  -> atspi_find_element
  -> atspi_get_children_text
  -> execute_yaml_suite
```

这个链路可以视为 YouQu 的第一个 spec engine：`atspi_yaml engine`。

它适合桌面自动化，但不适合直接承载 Web spec，原因是：

- 桌面 selector 是 AT-SPI 语义，Web locator 是 DOM/ARIA/CSS 语义。
- 桌面 action 依赖 Dogtail/MouseKey，Web action 应依赖 Playwright Page。
- `elements.yaml` 是桌面元素注册表，不应强行表达 Web locator。
- 当前 MCP YAML batch 通过 pytest subprocess 执行，不适合直接复用为 Web spec runner。

因此 Web spec 应作为并列 engine 接入，而不是作为 `src/yaml_test/executor.py` 的特殊 action。

## 推荐模块划分

新增目录：

```text
src/web_spec/
├── models.py              # Web spec 数据模型
├── loader.py              # 加载和校验 spec 文件/目录
├── locator_resolver.py    # Web locator -> Playwright locator
├── action_executor.py     # Web action 执行
├── assertion_executor.py  # Web assertion 执行
├── runner.py              # 确定性执行主流程
├── index.py               # Web spec 索引和查询
├── config.py              # Web spec 运行配置适配
└── reporter.py            # JSON/HTML/摘要报告
```

建议从 `uos-ai-test` 吸收以下设计：

```text
src/web_at/spec/models.py                  -> src/web_spec/models.py
src/web_at/spec/loader.py                  -> src/web_spec/loader.py
src/web_at/engine/locator_resolver.py      -> src/web_spec/locator_resolver.py
src/web_at/engine/action_executor.py       -> src/web_spec/action_executor.py
src/web_at/engine/assertion_executor.py    -> src/web_spec/assertion_executor.py
src/web_at/engine/deterministic_runner.py  -> src/web_spec/runner.py
src/web_at/tui/spec_reporter.py            -> src/web_spec/reporter.py
```

明确不迁移以下内容：

```text
src/web_at/commands/import_cases.py
src/web_at/commands/run.py
src/web_at/commands/run_all.py
src/web_at/engine/react_loop.py
src/web_at/engine/playwright_mgr.py        # AI ReAct 链路使用的 async 封装，spec runner 不依赖
src/web_at/ai/*
src/web_at/cases/*                         # PMS/自然语言用例模型与存储
AI model 配置与 tool-calling 配置
```

迁移时不是整仓搬运，而是保留 spec 确定性执行思想，并适配 YouQu 的包结构、配置、报告目录和 MCP/job 约定。

## Web spec 执行流

目标执行流：

```text
youqu web-spec run specs/
  -> 加载 Web spec 配置
  -> 加载 spec 文件或目录
  -> 校验 spec 结构
  -> 启动 Playwright browser/context/page
  -> 导航 entry page
  -> 按 step 执行 actions
  -> 按 step 执行 assertions
  -> 失败早停并截图
  -> 输出 report.json / report.html / summary
  -> 返回进程退出码
```

Web spec runner 只做确定性执行，不依赖 LLM 决定 PASS/FAIL。本次整合不接入 `uos-ai-test` 的 AI ReAct 或模型调用链路。

## CLI 接入

第一阶段新增独立命令，避免改变现有 `youqu at run` 行为：

```bash
youqu web-spec run <spec_path>
youqu web-spec list <spec_dir>
youqu web-spec index <spec_dir>
```

推荐参数：

```bash
--config <path>        # 指定 Web spec 配置
--headed               # 有头模式运行浏览器
--report-dir <path>    # 指定报告目录
--dry-run              # 只加载和校验，不执行
--no-screenshot        # 关闭步骤截图
```

现有命令保持不变：

```bash
youqu at run           # 执行 AT-SPI YAML 测试项目
```

后续如果需要统一入口，可以演进为：

```bash
youqu spec run --engine web <spec_path>
youqu spec run --engine desktop <yaml_path>
```

但这不作为第一阶段目标。

## MCP 和 Job 接入

第一阶段新增独立 MCP 工具族：

```text
web_spec_list
web_spec_run_batch
web_spec_get_status
web_spec_cancel
```

复用现有 `src/mcp/jobs.py` 的 `JobManager`：

- 复用 job 状态管理。
- 复用串行执行约束。
- 复用取消和状态查询机制。

但不复用当前 YAML 的 `execute_batches()`，因为它以 pytest subprocess 为中心。Web spec 应新增执行函数，例如：

```text
execute_web_specs(spec_paths, config_path, report_dir, batch_size, cancel_event)
```

该函数直接调用 `src/web_spec/runner.py`，返回结构化结果。

## 报告与结果

Web spec 第一阶段报告产物建议保持简单：

```text
report/web_spec/<timestamp>/
├── summary.json
├── summary.html
├── <spec_id>/
│   ├── report.json
│   ├── report.html
│   └── step_<n>.png
```

状态建议保留以下分类：

```text
passed
failed_product
failed_script
blocked_env
cancelled
```

这样可以区分产品缺陷、脚本问题和环境阻塞，方便后续 PMS/平台化接入。

## 配置策略

Web spec 不应依赖当前工作目录隐式查找 `config.yaml`。第一阶段采用明确配置优先级：

```text
CLI --config
  > 环境变量 YOUQU_WEB_SPEC_CONFIG
  > 项目默认配置 setting/globalconfig.ini 中的 web_spec 段
  > 内置默认值
```

只保留 spec 确定性执行需要的配置，不迁移 `uos-ai-test` 原有 AI/PMS/自然语言用例相关配置。

建议保留的配置项：

```text
base_url                 # 被测 Web 项目地址
entry_route              # spec 默认入口路由
headless                 # 浏览器是否无头运行
viewport                 # 浏览器视口
browser                  # chromium/firefox/webkit，第一阶段可只支持 chromium
assertion_timeout_ms     # 断言超时
retry_interval_ms        # 断言重试间隔
screenshot_on_step       # 是否按步骤截图
report_dir               # Web spec 报告目录
```

明确不保留的原 uos-ai-test 配置：

```text
ai / model / api_key
backend_health 中与 PMS/AI 用例链路强绑定的配置
cases_dir
proj_description
自然语言 ReAct loop 相关配置
PMS import/run-all 相关配置
```

## 已知风险与处理

| 风险 | 处理方式 |
| --- | --- |
| Web locator 多匹配导致误点 | 交互 action 默认要求唯一匹配，允许显式声明取第一个 |
| `networkidle` 对 WebSocket/SSE 不稳定 | 默认不强依赖 networkidle，允许 step 级 wait 策略 |
| uos-ai-test 中 ORDER 断言未实现 | 第一阶段不暴露 ORDER，或实现后再加入 schema |
| teardown 仅有模型但未执行 | 第一阶段明确实现 teardown，至少支持关闭页面、清理 storage、执行自定义步骤 |
| AI ReAct 不属于本次范围 | 不迁移 AI ReAct、模型调用和自然语言用例执行链路 |
| 报告产物本地化 | 先落地本地 report 目录，后续抽象 artifact sink |

## 分阶段计划

### 第一阶段：最小可用接入

- 新增 `src/web_spec` 模块。
- 只迁移 spec 确定性执行相关模型、loader、locator、action、assertion、runner、reporter。
- 支持加载和执行 Web spec 文件/目录。
- 新增 `youqu web-spec run/list/index`。
- 输出 JSON/HTML/screenshot 报告。
- 只保留 spec runner 必需配置。
- 不影响现有桌面 YAML 链路。

### 第二阶段：MCP/job 接入

- 新增 `web_spec_*` MCP 工具。
- 复用 `JobManager`。
- 支持异步批量执行、状态查询和取消。

### 第三阶段：平台化和统一抽象

- 抽象通用 spec 生命周期：discover、load、validate、index、run、report。
- 引入 `SpecEngine` registry。
- 将 `desktop_yaml` 和 `web_spec` 收敛到统一入口。
- 视需要统一 CLI/MCP 工具命名。

## 结论

Web spec 应成为 YouQu 的第二个 spec engine，而不是当前桌面 YAML executor 的扩展动作。

本次整合只接入 `uos-ai-test` 的 spec 确定性执行部分，并将原配置收敛为 spec runner 必需配置。第一阶段采用“并列 Web spec engine + 复用 YouQu 外壳”的方式，能够在不破坏现有桌面自动化能力的前提下，快速接入 Web 项目测试能力。长期再通过 `SpecEngine` 抽象统一桌面、Web、API、DBus 等不同类型的 spec 生命周期。
