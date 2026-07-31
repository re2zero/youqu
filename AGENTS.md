# YouQu (有趣) — AGENTS.md

Linux 桌面自动化测试框架，统信 Deepin/UOS 开源，GPL-2.0。
PyPI 包名: `youqu-ai`。

## 技术特点

**六大测试能力**: 桌面 UI (AT-SPI+Dogtail)、Web UI (Playwright)、DBus 接口、命令行、HTTP 接口、AI/MCP/VLM 自动化。

**X11 + Wayland 双协议支持** — 框架核心差异点。键鼠操作在 X11 用 xdotool/pyautogui，Wayland 用 ydotool/D-Bus Autotool；窗口信息在 X11 用 xdotool+xwininfo，Wayland 用 libdtkwmjack (CTypes FFI)。`GlobalConfig.IS_WAYLAND` 是关键开关。

**CSV 驱动的标签管理系统** — 每个 APP 工程有一个 CSV 文件管理用例标签 (skip/fixed/removed/自定义标签/PMS用例ID)。`conftest.py` 在用例收集阶段自动解析 CSV 并应用标记。

**PMS 测试管理平台集成** — 测试结果可自动回填到 PMS (pms.uniontech.com)，支持从测试单/测试套件拉取关联用例执行。

**远程分布式执行** — 通过 SSH/SCP 分发代码到多台测试机，支持并行或分布式模式。

## 解决的问题

1. Linux 桌面应用缺乏统一自动化测试框架 — YouQu 提供了 AT-SPI 坐标/图像/OCR/DBus 多种定位方式
2. X11 向 Wayland 迁移期的兼容性 — 双协议支持避免测试框架需要重写
3. 大规模用例管理 — CSV 标签系统 + PMS 集成实现用例的精细化管理
4. 多机器执行 — 远程执行器支持分布式测试
5. 测试报告与数据回填 — Allure 报告 + JSON 报告 + PMS 自动回填

## AI / MCP / VLM 集成

框架已内置 AI 相关能力，不是仅停留在规划阶段:

- **VLM 模块**: `src/vlm/` 提供视觉定位、VLM 断言、VLM Agent 执行能力。VLM 需要外部 OpenAI-compatible API server，例如 Ollama + Qwen2.5-VL；框架没有内置模型。
- **MCP Server**: `src/mcp/` 暴露桌面自动化、YAML 用例、VLM/截图、命令查询等工具。MCP HTTP transport 依赖 `fastmcp-slim[server]`。
- **AT-SPI YAML 用例生成**: `skills/at-case-generator/SKILL.md` 提供完整的 AT-SPI YAML 测试自动化管道 (scan → record → merge → parse → tree-info → split → docs → precandidate → validate → generate → run → smoke/verify)。
- **AT-SPI 步骤语义解析**: `skills/at-mapping-rules/SKILL.md` 提供步骤语义解析协议。
- **设计文档**: `docs/prd/multica-integration.md` 记录 Multica 集成设计；`docs/youqu-mcp-vlm-evaluation.md` 记录 MCP/VLM 集成与评估。
- **关键结合点**: `Src` 多继承基类、`DogtailUtils` 的 AT-SPI 树 API、`ButtonCenter` 坐标系统、`src/vlm/vlm_agent.py` 的 VLM 执行循环、`src/mcp/server.py` 的工具入口。

## 项目结构

```
youqu/
├── manage.py           # 主入口 CLI，子命令: run/remote/startapp/pmsctl/csvctl/git
├── conftest.py         # pytest 根配置 (钩子、fixture、CSV标签解析、执行后PMS回填)
├── apps/               # 测试用例目录 (pytest testpaths)，每个子目录是一个 APP 工程
├── src/                # 核心框架
│   ├── __init__.py     # Src 多继承基类；VLM 可选导入 lazy fallback
│   ├── dogtail_utils.py    # AT-SPI 元素定位 (X11/Wayland)
│   ├── button_center.py    # 埐标定位系统 (基于 ui.ini 配置)
│   ├── mouse_key.py        # 键鼠操作 (xdotool/ydotool)
│   ├── image_utils.py      # 图像识别 (OpenCV，支持 RPC)
│   ├── ocr_utils.py        # OCR 文字识别 (PaddleOCR RPC，链式调用)
│   ├── assert_common.py    # 统一断言 (图像/OCR/元素/文件/进程)
│   ├── dbus_utils.py       # DBus 接口测试
│   ├── webui.py            # Web UI 自动化 (Playwright)
│   ├── cmdctl.py           # 命令执行控制
│   ├── requestx.py          # HTTP 请求
│   ├── rtk/                # 运行时: local_runner, remote_runner
│   ├── pms/                # PMS 集成: send2pms, suite, task, pms2csv, csv2pms
│   ├── plugins/            # 空目录；pytest 插件不在 src/plugins/
│   ├── remotectl/          # SSH 远程控制
│   ├── git/                # Git 子命令 (clone/commit统计/健康检查)
│   ├── depends/            # 内嵌第三方库 (dogtail, sniff, wayland_autotool 等)
│   └── utils/              # 环境部署脚本
├── cli/                  # CLI 命令 (youqu console_scripts)
│   ├── main.py            # argparse 路由入口
│   ├── at.py              # youqu at AT-SPI YAML 测试管道
│   ├── report.py          # youqu report 生成/查看 Allure 报告
│   ├── index.py           # YAML 用例索引查询/重建
│   └── doctor.py          # 环境检查与修复
├── plugin/               # pytest 插件 (entry_points.pytest11)
│   ├── __init__.py        # sys.path 注入 + 环境变量 + YAML collector
│   └── entry_points.pytest11
├── setting/            # 配置
│   ├── globalconfig.py  # 全局配置加载器 (读取 globalconfig.ini)
│   ├── globalconfig.ini  # 主配置文件 (12 个 section)
│   ├── skipif.py         # 条件跳过逻辑
│   ├── pylintrc.cfg      # pylint 配置
│   └── template/app_template/  # APP 工程脚手架模板 (PO 设计)
├── docs/               # VitePress 文档站点
├── env.sh              # 环境部署脚本 (安装系统依赖 + Python 包)
├── publish.sh          # PyPI 发布脚本
├── pytest.ini          # pytest 配置: testpaths=apps, 隐含参数
├── ruff.toml           # Ruff lint 配置
└── pyproject.toml      # 包元数据 (hatchling 构建)
```

## 命令

### CLI 命令 (pip install youqu-ai 后可用)
```bash
youqu mcp                                       # 启动 MCP server (stdio)
youqu mcp --transport http --host 0.0.0.0 --port 8066  # HTTP 模式
youqu doctor                                    # 环境检查与 skill 安装
youqu startproject <name>                       # 复制框架创建项目
```

### AT-SPI YAML 测试管道 (youqu at)
```bash
youqu manage.py run                           # 本地执行 (读取 globalconfig.ini 配置)
youqu manage.py run -a apps/autotest_xxx       # 指定 APP 工程
youqu manage.py run -k "keyword"               # 按关键词过滤
youqu manage.py run -t "L1 or smoke"           # 按标签过滤 (支持 and/or/not)
youqu manage.py remote                        # 远程分布式执行
youqu manage.py run --noskip                   # 忽略所有 skip 标记
youqu manage.py run --ifixed yes              # 忽略 fixed 标记 (fixed-不生效)
```

### 工程管理
```bash
youqu manage.py startapp autotest_deepin_xxx   # 复制框架创建 APP 工程
youqu manage.py pmsctl                         # PMS 数据管理
youqu manage.py csvctl                         # CSV 标签管理
youqu manage.py git                            # Git 子项目操作
```

### 环境与代码检查
```bash
bash env.sh                                    # 部署环境 (pipenv 虚拟环境)
bash env.sh -p PASSWORD                        # 指定 sudo 密码
bash env.sh -D                                 # 开发模式 (直接 pip install)
ruff check .                                   # lint
ruff format .                                  # format
src/utils/pylint.sh apps/autotest_xxx          # pylint HTML 报告
```

### 构建/发布
```bash
python3 -m build                              # 构建 wheel
twine upload dist/*                            # 发布到 PyPI
```

### 单元测试
```bash
python -m pytest -c pytest-tests.ini tests/   # 运行单元测试 (tests/ 目录)
```

## 关键约定

### 用例命名 (强制)
函数名和文件名必须遵循 `test_<功能名>_<3位ID>` 格式，且两者 ID 必须一致。
不一致的用例会被框架自动 skip。例如: `test_music_001` 对应 `test_music_001.py`。

### APP 工程 PO 模式
`youqu startproject <name>` 会复制整个框架创建项目。

Python 用例工程遵循 Page Object 设计:
```
autotest_xxx/
├── config.ini            # 应用配置
├── xxx.csv               # CSV 标签管理
├── xxx_assert.py         # 自定义断言 (继承 AssertCommon)
├── conftest.py           # 应用级 fixture
├── case/
│   ├── base_case.py      # 用例基类 (继承 AssertCommon)
│   └── test_xxx_001.py  # 具体用例
└── widget/
    ├── base_widget.py    # Widget 基类 (继承 Src)
    ├── xxx_widget.py     # 应用 Widget (封装 dog/button_center 操作)
    ├── ui.ini            # 控件坐标配置
    └── pic_res/          # 模板图片
```

YAML 用例工程使用 `yaml/elements.yaml` 作为元素引用单点，并通过 `src/yaml_test/` 的 pytest collector 与 executor 执行。

继承链: `Src → BaseWidget → XxxWidget` (方法层)，`AssertCommon → XxxAssert → BaseCase → TestXxx` (用例层)。

### CSV 标签格式
CSV 文件与 APP 工程同名 (去掉前缀)。列: `ID, skip_reason, fixed, removed, PMS用例ID, 自定义标签...`。
- `skip-原因`: 跳过用例
- `fixed-版本`: 标记已修复 (默认会覆盖 skip)
- `removed-原因`: 从执行列表移除
- `skipif_<方法>-<参数>`: 条件跳过 (定义在 `setting/skipif.py`)

### 框架 API 导入
```python
from src import Src, OCR, MouseKey, DbusUtils, AssertCommon, CmdCtl, log
from setting import conf  # GlobalConfig 短别名
```

### pytest 隐含配置 (pytest.ini)
根 pytest 自动生效: `-s -vv --no-header --show-capture=no --tb=auto -r fEs --continue-on-collection-errors --ignore=src,setting,public`。测试路径: `apps/`。最低 pytest 版本: 6.2.5。
YAML APP 工程的 `autotest/pytest.ini` 使用 `testpaths = yaml` / `testpaths = case` / `testpaths = case yaml`，并设置 `yaml_files = yaml`。

### 代码风格
Ruff: line-length=100, 4-space indent, Python 3.10+。仅启用 E4/E7/E9/F 规则 (大量 F 规则被 ignore)。
注意: 框架核心代码 (`src/`, `conftest.py`) 在文件头大量使用 `# pylint: disable`。

### 环境要求
- Python >= 3.10
- 需要桌面环境 (X11 或 Wayland)，不能在 headless 下运行 UI 测试
- DISPLAY=:0 在 `conftest.py` 中硬编码
- 依赖通过 `env.sh` 安装 (无 requirements.txt / Pipfile / poetry.lock)
- 可选依赖: letmego (重启类场景)，playwright (Web UI)，zerorpc (远程执行)，fastmcp-slim[server] (MCP HTTP transport)
- libclang Python 绑定 (用于 `youqu at dump` 静态源码扫描): `python3-clang-18` + `libclang-18-dev` (或 17/19 版本)

### AT-SPI YAML 测试管道 (youqu at)

`youqu at` 命令族提供完整的 AT-SPI YAML 测试自动化管道: scan → record → merge → parse → tree-info → split → docs → precandidate → validate → generate → run → smoke/verify。

**管道命令一览**:
- `youqu at scan --src <dir> --app <id> --output <dir>` — 源码扫描 (libclang，headless 可用)
- `youqu at record --app <id> [--launch <cmd>] [--gui]` — 事件驱动录制 (X11 XRecord / Wayland evdev)
- `youqu at merge --record <dir> [--scan <dir>] --output <dir>` — 分层合并 (持久层 + 瞬态层)
- `youqu at parse --input <xlsx> --output <yaml>` — xlsx/csv → cases_raw.yaml (格式转换)
- `youqu at tree-info --at-tree <yaml> --output <yaml> --format yaml` — 生成 AI 标注用结构化 YAML
- `youqu at split --cases <raw> --at-tree <annotated> --output <dir>` — 按模块分片 cases + at-tree 子集
- `youqu at docs <app> --output <dir>` — 导入帮助手册章节 (按 `##` 切分)
- `youqu at precandidate --cases <raw> --at-tree <annotated> --output <yaml>` — 约束式选择器预筛选
- `youqu at validate --gate <1|2|3|4|5|all>` — 分层验证 (5 个 gate)
- `youqu at generate --cases <mapped> --output <dir> --app <app> --at-tree <tree>` — 生成 suite YAML
- `youqu at run --testdir <dir>` — 执行 AT-SPI YAML 测试
- `youqu at smoke --modules-dir <dir>` — L2 模块烟雾测试 (每模块 1 个代表 case)
- `youqu at verify --suite <yaml> --spec-id <id>` — L3 单 case 深度验证

**at-tree.yaml v2.0 格式** (scan+record+merge 产出):
- `tree`: 持久层 — 始终可见的元素 (base dump + window:activate 合并，states 最后观测值覆盖)
- `transient_contexts`: 瞬态层 — 右键菜单、对话框、子窗口 (不混入主树，标注触发条件)

**静态扫描依赖**：
- 需要 libclang Python 绑定以提取 DTK/Qt 控件声明骨架
- 安装命令: `sudo apt install python3-clang-18 libclang-18-dev` (或 17/19 版本)
- 若未安装，静态扫描将跳过，仅保留运行时 AT-SPI 树抓取

**录制依赖**:
- X11: python-xlib (XRecord 被动监听，不干扰用户操作)
- Wayland: evdev (低精度模式，需 root 或 input 组)
- 未安装时降级为纯 AT-SPI focus 事件模式

**命令示例**：
```bash
youqu at scan --src /path/to/source --app dde-file-manager --output /tmp/at-scan
youqu at record --app dde-file-manager --launch /usr/bin/dde-file-manager --output /tmp/at-record
youqu at merge --scan /tmp/at-scan --record /tmp/at-record --output /tmp/at-merge
youqu at tree-info --at-tree /tmp/at-merge/at-tree.yaml --output at-tree-annotated.yaml
youqu at split --cases cases_raw.yaml --at-tree at-tree-annotated.yaml --output /tmp/modules/
youqu at precandidate --module-dir /tmp/modules/find/
youqu at validate --gate 5 --cases-mapped cases_mapped.yaml
youqu at smoke --modules-dir /tmp/modules/
youqu at verify --suite find/find.suite.yaml --spec-id find_s0
```

**技能文件**: `skills/at-case-generator/SKILL.md` (主管道 + CLI 参考) 和 `skills/at-mapping-rules/SKILL.md` (步骤语义解析协议)。

### 远程执行
`manage.py remote` 通过 SSH 分发代码，`--slaves` 参数格式: `user@ip:password`，多台用 `/` 分隔。

### MCP / VLM 约束
- `src/mcp/server.py` 暴露桌面自动化、YAML 用例、VLM/截图、命令查询等工具。
- MCP `system_run_command` 使用只读命令白名单，且采用精确匹配，不做前缀匹配。
- MCP `keyboard_press_key` / `keyboard_hot_key` 会拦截危险快捷键组合。
- MCP `screenshot_save` 固定输出到 `_PROJECT_ROOT / "report" / "vlm_evidence"`，不接受调用方传任意输出路径；`VLM_EVIDENCE_DIR` 只影响 VLM 内部配置，不控制 MCP 工具输出。
- `src/__init__.py` 对 VLM 模块做可选导入 fallback；`Src.vlm` / `Src.vlm_agent` 是 lazy property，会检查 `VLMConfig().is_available()`。

## Web Spec 自动化测试

Web Spec 是基于 Playwright 的确定性 Web UI 测试能力，使用 YAML 描述页面入口、操作步骤和断言，不依赖 AI 推理执行。适合把稳定的 Web 页面流程沉淀为可重复运行的自动化用例。

### 安装依赖

```bash
pip install -e ".[webui]"                     # 源码开发环境
# 或
pip install "youqu-ai[webui]"                 # 已安装 wheel 的环境
playwright install chromium
```

### CLI 命令

```bash
youqu web-spec init web_spec.yaml             # 初始化配置文件
youqu web-spec run examples/web_spec/specs    # 运行 spec 文件或目录
youqu web-spec run examples/web_spec/specs --dry-run   # 只加载校验，不启动浏览器
youqu web-spec list examples/web_spec/specs   # 列举用例
youqu web-spec index examples/web_spec/specs  # 重建索引
youqu web-spec suite examples/web_spec/smoke  # 运行 suite 目录
youqu web-spec check examples/web_spec/specs  # 静态检查 spec 和 suite 质量
```

### Spec 文件结构

最小 Web Spec YAML 示例：
```yaml
id: login-smoke
title: 登录页冒烟测试
module: 认证
tags: [smoke]
entry_page: /login
steps:
  - description: 检查登录按钮
    assertions:
      - type: visible
        locator:
          strategy: text
          value: 登录
          exact: true
```

支持的 locator 策略：`role`, `text`, `test_id`, `bem_css`, `css`。
支持的 action：`click`, `fill`, `input_text`, `keyboard_type`, `press_key`, `hover`, `select_option`, `wait_for`, `scroll`, `right_click`, `dblclick`, `drag_to`, `upload_file`。
支持的 assertion：`visible`, `not_visible`, `text_contains`, `text_equals`, `html_contains`, `html_equals`, `enabled`, `disabled`, `count`, `input_value_equals`, `input_value_contains`, `attribute_equals`, `attribute_contains`, `class_contains`, `url_equals`, `url_contains`, `text_sequence`。

<!-- TRELLIS:START -->
# Trellis Instructions

These instructions are for AI assistants working in this project.

This project is managed by Trellis. The working knowledge you need lives under `.trellis/`:

- `.trellis/workflow.md` — development phases, when to create tasks, skill routing
- `.trellis/spec/` — package- and layer-scoped coding guidelines (read before writing code in a given layer)
- `.trellis/workspace/` — per-developer journals and session traces
- `.trellis/tasks/` — active and archived tasks (PRDs, research, jsonl context)

If a Trellis command is available on your platform (e.g. `/trellis:finish-work`, `/trellis:continue`), prefer it over manual steps. Not every platform exposes every command.

If you're using Codex or another agent-capable tool, additional project-scoped helpers may live in:
- `.agents/skills/` — reusable Trellis skills
- `.codex/agents/` — optional custom subagents

Managed by Trellis. Edits outside this block are preserved; edits inside may be overwritten by a future `trellis update`.

<!-- TRELLIS:END -->
