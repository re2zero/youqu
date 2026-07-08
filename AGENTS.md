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
- **多模态用例执行**: `cli/multica_report.py` 与 `skills/youqu-case-runner/SKILL.md` 支持从 issue/PR/Multica 上下文生成并执行 YAML 用例。
- **用例生成 Skill**: `skills/youqu-case-generator/SKILL.md` 支持从需求/PR/问题描述生成可执行 YAML 用例。
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
│   ├── make.py            # youqu make 生成 autotest/ 骨架 (py/yaml/all)
│   ├── run.py             # youqu run 执行逻辑
│   ├── report.py          # youqu report 生成/查看 Allure 报告
│   ├── index.py           # YAML 用例索引查询/重建
│   └── multica_report.py # Multica 上下文生成并执行用例
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
youqu make <name> <fmt>                         # 生成 autotest/ 骨架 (py/yaml/all)
youqu run                                       # 执行 autotest/ 下测试
youqu run -k "keyword"                          # 关键词过滤 (透传 pytest)
youqu run --alluredir=./report                  # 覆盖报告路径
youqu mcp                                       # 启动 MCP server (stdio)
youqu mcp --transport http --host 0.0.0.0 --port 8066  # HTTP 模式
youqu report                                    # 生成/查看 Allure 报告
youqu index                                     # YAML 用例索引查询/重建
youqu doctor                                    # 环境检查与 skill 安装
youqu startproject <name>                       # 复制框架创建项目；骨架生成用 youqu make
```

### 测试执行 (manage.py，传统流程)
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

## 关键约定

### 用例命名 (强制)
函数名和文件名必须遵循 `test_<功能名>_<3位ID>` 格式，且两者 ID 必须一致。
不一致的用例会被框架自动 skip。例如: `test_music_001` 对应 `test_music_001.py`。

### APP 工程 PO 模式
`youqu make <name> <py|yaml|all>` 会生成 `autotest/` 骨架；`youqu startproject <name>` 会复制整个框架创建项目。

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

`youqu at dump <type> --app <app_id> --src <src_dir> --output <output_dir>` 用于生成 AT-SPI YAML 测试树。

**静态扫描依赖**：
- 需要 libclang Python 绑定以提取 DTK/Qt 控件声明骨架
- 安装命令: `sudo apt install python3-clang-18 libclang-18-dev` (或 17/19 版本)
- 若未安装，静态扫描将跳过，仅保留运行时 AT-SPI 树抓取

**命令示例**：
```bash
youqu at dump dtk --app dde-file-manager --src /path/to/source --output /path/to/output
```

### 远程执行
`manage.py remote` 通过 SSH 分发代码，`--slaves` 参数格式: `user@ip:password`，多台用 `/` 分隔。

### MCP / VLM 约束
- `src/mcp/server.py` 暴露桌面自动化、YAML 用例、VLM/截图、命令查询等工具。
- MCP `system_run_command` 使用只读命令白名单，且采用精确匹配，不做前缀匹配。
- MCP `keyboard_press_key` / `keyboard_hot_key` 会拦截危险快捷键组合。
- MCP `screenshot_save` 固定输出到 `_PROJECT_ROOT / "report" / "vlm_evidence"`，不接受调用方传任意输出路径；`VLM_EVIDENCE_DIR` 只影响 VLM 内部配置，不控制 MCP 工具输出。
- `src/__init__.py` 对 VLM 模块做可选导入 fallback；`Src.vlm` / `Src.vlm_agent` 是 lazy property，会检查 `VLMConfig().is_available()`。

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
