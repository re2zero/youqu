<p align="center">
  <a href="https://linuxdeepin.github.io/youqu">
    <img src="./docs/assets/logo.png" width="100" alt="YouQu">
  </a>
</p>
<p align="center">
    <em>YouQu（有趣），一个使用简单且功能强大的自动化测试框架。</em>
</p>

[![GitHub issues](https://img.shields.io/github/issues/linuxdeepin/youqu?color=%23F79431)](https://github.com/linuxdeepin/youqu/issues)
[![PyPI](https://img.shields.io/pypi/v/youqu?style=flat&logo=github&link=https%3A%2F%2Fpypi.org%2Fproject%2Fyouqu%2F&color=%23F79431)](https://pypi.org/project/youqu/)
![Static Badge](https://img.shields.io/badge/UOS%2FDeepin/openEuler/openAnolis-Platform?style=flat&label=OS&color=%23F79431)

[![Downloads](https://static.pepy.tech/badge/youqu)](https://pepy.tech/project/youqu)
[![Hits](https://hits.sh/github.com/linuxdeepin/youqu.svg?style=flat&label=visitors&color=blue)](https://github.com/linuxdeepin/youqu)

---

**深度社区：<a href="https://github.com/linuxdeepin/youqu" target="_blank">linuxdeepin</a> | <a href="https://gitee.com/deepin-community/youqu" target="_blank">deepin-community</a>**

**欧拉社区：<a href="https://gitee.com/src-openeuler/youqu" target="_blank">openEuler</a>**

**龙晰社区：<a href="https://gitee.com/anolis/youqu" target="_blank">openAnolis</a>**

**官方文档：<a href="https://youqu.uniontech.com" target="_blank">https://youqu.uniontech.com</a>**

**欢迎加入 [YouQu官方兴趣小组](https://youqu.uniontech.com/SIG.html)**

---

YouQu（有趣）是统信公司（Deepin/UOS）开源的一个 Linux 操作系统的自动化测试框架，支持多元化元素定位和断言、用例标签化管理和执行、强大的日志和报告输出等特色功能，同时完美兼容 X11、Wayland 显示协议，环境部署简单，操作易上手。🔥

## YouQu 能做什么

- [X]  💻 Linux 桌面应用 UI 自动化测试
- [X]  🌏 Web UI 自动化测试
- [X]  🚌 Linux DBus 接口自动化测试
- [X]  🚀 命令行自动化测试
- [X]  🕷️ HTTP 接口自动化测试

## 快速开始

### 安装

从 PyPI 安装:

```shell
$ sudo pip3 install youqu-ai
```

> 验证安装：`youqu --help` 列出所有子命令，`youqu --version` 显示版本号。
> 如果遇到 `error: externally-managed-environment`，加上 `--break-system-packages`（虚拟环境则无需）。
> 升级或重装时需加 `--force-reinstall`，否则同版本号会被 pip 跳过。

<details>
    <summary><b>不加 sudo ?</b></summary>

---

不加 sudo 也可以：

```shell
pip3 install youqu-ai
```

但可能出现 `youqu-startproject` 命令无法使用；

这是因为不加 `sudo` 时，`youqu-startproject` 命令会生成在 `$HOME/.local/bin` 下，

而此路径可能不在环境变量（`PATH`）中，因此您需要添加环境变量：

```shell
export PATH=$PATH:$HOME/.local/bin
```

---

</details>

使用 pipx 安装（推荐，自动隔离环境）:

```shell
$ sudo apt install pipx
$ pipx ensurepath
# 安装或升级已有的 youqu-ai whl 包
$ pipx install --system-site-packages --force youqu-ai
# 安装本地 whl 文件
$ pipx install --system-site-packages --force /path/to/youqu_ai-*.whl
```

> **为什么需要 `--system-site-packages`？**
> pipx 默认创建一个完全隔离的虚拟环境，而 youqu 依赖的部分系统包（`python3-pyatspi`、`python3-opencv`、`python3-clang` 等）只通过 `apt` 安装到 `/usr/lib/python3/dist-packages/`，PyPI 上没有。
> 加上此参数后，pipx 虚拟环境会继承系统安装的 Python 包，`import pyatspi`、`import cv2`、`import clang.cindex` 等在运行时都能正常引入。
>
> 如果用 `pip install youqu-ai` 安装，则默认能访问系统包，无需此参数。
>
> 验证：`youqu doctor` 应全部显示 `[OK]`。


### 创建项目

您可以在任意目录下，使用 `youqu-startproject` 命令创建一个项目：

```shell
$ youqu-startproject my_project
```

注意：所有命令不要以 `root` 用户执行！

如果 `youqu-startproject` 后面不加参数，默认的项目名称为：`youqu` ；

![](./docs/assets/install.gif)

### 编写测试用例

YouQu 支持 **YAML** 和 **Python** 两种方式编写测试用例，同一个 `run` 命令统一执行：

```
youqu-startproject my_project
           |
    cd my_project
           |
    +------+-------+
    |              |
 YAML 路径      Python 路径
 声明式/AI友好   传统PO模式
    |              |
 youqu at      youqu manage.py
 生成/执行      startapp
    |              |
 tests/at/yaml/ apps/autotest_xxx/
 ├── cases      ├── widget/
 │   .yaml      ├── case/
 └── at-tree    └── ui.ini
     .yaml
    |              |
    +------+-------+
           |
 youqu at run
```

#### YAML 路径（推荐 AI 用户）

声明式、无需编写 Python 代码，AI 客户端可直接通过 MCP 工具获取 AT-SPI 元素树并生成 YAML 用例：

使用 `youqu at` 管道生成并执行 YAML 用例：
```shell
youqu at scan --src <dir> --app <id> --output <dir>
youqu at record --app <id> [--launch <cmd>] [--gui]
youqu at merge --record <dir> [--scan <dir>] --output <dir>
youqu at parse --input <xlsx> --output <yaml>
youqu at tree-info --at-tree <yaml> --output <yaml> --format yaml
youqu at generate --cases <mapped> --output <dir> --app <app> --at-tree <tree>
youqu at run --testdir <dir>
```

YAML 用例将所有 UI 元素集中注册在 `at-tree.yaml` 及生成的 suite YAML 中，测试用例通过 `selector` 引用元素，使用 `action` 声明操作、`assert` 声明断言。

#### Python 路径（传统 PO 模式）

适合需要复杂逻辑、自定义断言的场景，遵循 Page Object 设计模式：

```shell
$ youqu manage.py startapp autotest_deepin_some      # 创建 APP 工程（Python）
```

自动创建的 APP 工程：

```shell
my_project
├── apps
│   ├── autotest_deepin_some
│   │   ├── widget/          # 元素操作层
│   │   ├── case/            # 测试用例层
│   │   ├── ui.ini           # 控件坐标配置
│   │   └── xxx.csv          # 标签管理
```

继承链：`Src → BaseWidget → XxxWidget`（方法层），`AssertCommon → XxxAssert → BaseCase → TestXxx`（用例层）。

> **在你的远程 Git 仓库中，只需要保存 APP 工程这部分代码即可。** `apps` 目录下可以存在任意多个 APP 工程。

### 系统依赖

YouQu 需要以下系统包：

| 包名 (Debian/Ubuntu) | 用途 |
|----------------------|------|
| `python3-pip` | Python 包管理 |
| `python3-tk` | Tkinter GUI |
| `scrot` | 屏幕截图 |
| `python3-opencv` | 图像识别 |
| `python3-pyatspi` | AT-SPI 辅助功能 Python 绑定 |
| `gir1.2-atspi-2.0` | AT-SPI GObject 内省 |
| `libatk-adaptor` | AT 适配器 |
| `at-spi2-core` | AT-SPI 核心 |
| `openjdk-11-jdk-headless` | Java（Allure 报告生成必需） |

> **RHEL/openEuler**: 使用对应的包名，如 `java-11-openjdk-headless`、`python3-tkinter`、`opencv` 等。

一键部署脚本：

```shell
$ cd my_project
$ bash env.sh
# 默认密码: 1；
# 指定密码: bash env.sh -p ${my_password}；
# 或修改 setting/globalconfig.ini 中 PASSWORD 配置项。
```

`env.sh` 会自动安装系统依赖、pip 包、配置 SSH 和辅助功能。

> **桌面环境要求**: 需要运行中的 X11 或 Wayland 桌面会话（`DISPLAY=:0`），`~/.Xauthority` 文件存在，辅助功能已开启。

可选功能依赖：

| 功能 | 安装方式 |
|------|----------|
| Web UI 自动化 | `pip install youqu-ai[webui]` + `playwright install chromium` |
| 远程执行 | `pip install youqu-ai[remote]`，需 `sshpass` |
| MCP Server | 随 `pip install youqu-ai` 自动安装 |
| Wayland 支持 | 额外需要 `g++ cmake qt5-default libkf5wayland-dev wl-clipboard` 等编译依赖 |

### Web Spec 自动化测试

Web Spec 是基于 Playwright 的确定性 Web UI 测试能力，使用 YAML 描述页面入口、操作步骤和断言，不依赖 AI 推理执行。它适合把稳定的 Web 页面流程沉淀为可重复运行的自动化用例。

#### 安装依赖

源码开发环境可安装 Web UI 额外依赖并安装浏览器：

```shell
pip install -e ".[webui]"
playwright install chromium
```

已安装 wheel 的环境可使用：

```shell
pip install "youqu-ai[webui]"
playwright install chromium
```

#### 配置文件

可以先初始化一份默认配置：

```shell
youqu web-spec init web_spec.yaml
# 如需覆盖已有文件：youqu web-spec init web_spec.yaml --force
```

Web Spec 配置可写成扁平结构，也兼容 `target`、`engine`、`paths` 分组。示例见 `examples/web_spec/web_spec.yaml`：

```yaml
base_url: http://localhost:5173
entry_route: /
headless: true
viewport:
  width: 1280
  height: 720
report_dir: report/web_spec
```

常用字段：

| 字段 | 含义 |
|------|------|
| `base_url` | 被测 Web 服务地址 |
| `entry_route` | 默认入口路由 |
| `headless` | 是否使用无头浏览器 |
| `viewport` | 浏览器视口大小 |
| `assertion_timeout_ms` | 断言默认超时时间 |
| `retry_interval_ms` | 断言重试间隔 |
| `navigation_wait_after_ms` | 每次路由导航后的短暂等待时间，默认 300ms |
| `screenshot_on_step` | 每个 step 后是否截图 |
| `report_dir` | 报告输出目录 |

#### Spec 文件结构

一个最小 Web Spec YAML：

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

常用顶层字段：

| 字段 | 含义 |
|------|------|
| `id` | 用例 ID；缺省时使用文件名 |
| `title` / `name` | 用例标题；`name` 会兼容映射为 `title` |
| `module` / `feature` / `tags` | 分类和筛选信息 |
| `entry_page` | 相对 `base_url` 的入口路径 |
| `entry_url` | 完整入口 URL，优先级高于 `base_url + entry_page` |
| `setup` | 用例步骤前执行的 action 列表 |
| `steps` | 用例主体步骤，必须非空 |
| `teardown` | 用例结束后的清理策略和 action 列表 |
| `execution` | 用例级执行参数覆盖 |

`steps` 的执行顺序以 YAML 列表顺序为准，报告中的 Step order 会自动从 1 开始生成；编写用例时不需要维护 `order` 字段。

#### Locator

当前支持的 locator 策略：

| strategy | Playwright 映射 | 示例 |
|----------|-----------------|------|
| `role` | `page.get_by_role()` | `{strategy: role, value: button, name: 登录}` |
| `text` | `page.get_by_text()` | `{strategy: text, value: 登录, exact: true}` |
| `test_id` | `page.get_by_test_id()` | `{strategy: test_id, value: submit}` |
| `bem_css` | `page.locator()` | `{strategy: bem_css, value: .login-form__submit}` |
| `css` | `page.locator()` | `{strategy: css, value: button[type=submit]}` |

交互动作默认要求 locator 唯一匹配。确实需要取第一个匹配元素时，可以显式设置：

```yaml
locator:
  strategy: text
  value: 删除
  exact: true
  first: true
```

#### Action

当前支持的 action：

| type | 含义 | 主要字段 |
|------|------|----------|
| `click` | 点击元素 | `locator` |
| `fill` | 填充 input/textarea | `locator`, `value` |
| `input_text` | 点击聚焦后通过键盘输入文本 | `locator`, `value` |
| `keyboard_type` | 直接键盘输入文本 | `value` |
| `press_key` | 按键或快捷键 | `key` |
| `hover` | 悬停元素 | `locator` |
| `select_option` | 选择下拉选项 | `locator`, `value` |
| `wait_for` | 等待元素可见；无 locator 时按 timeout 睡眠 | `locator`, `timeout_ms` |
| `scroll` | 滚动到元素或按方向滚动页面 | `locator` 或 `direction` |
| `right_click` | 右键点击元素 | `locator` |
| `dblclick` | 双击元素 | `locator` |
| `drag_to` | 将源元素拖拽到目标元素 | `locator`, `target` |
| `upload_file` | 给文件输入框设置上传文件 | `locator`, `value` |

Action 可通过 `settle_after` 声明操作后的稳定等待：

```yaml
- type: click
  locator: {strategy: text, value: 提交, exact: true}
  settle_after:
    wait_for_text: 提交成功
    settle_ms: 300
```

#### Assertion

当前支持的 assertion：

| type | 含义 |
|------|------|
| `visible` | 元素可见 |
| `not_visible` | 元素不存在或不可见 |
| `text_contains` | 元素文本包含期望字符串；`expected` 可为字符串列表 |
| `text_equals` | 元素文本等于期望字符串 |
| `html_contains` | 元素 HTML 包含期望字符串 |
| `html_equals` | 元素 HTML 等于期望字符串 |
| `enabled` | 元素可用 |
| `disabled` | 元素不可用 |
| `count` | 匹配元素数量等于 `expected` |
| `input_value_equals` | 输入控件当前值等于 `expected` |
| `input_value_contains` | 输入控件当前值包含 `expected` |
| `attribute_equals` | 指定属性值等于 `expected`，需提供 `attribute` |
| `attribute_contains` | 指定属性值包含 `expected`，需提供 `attribute` |
| `class_contains` | 元素 `class` 属性包含 `expected` |
| `url_equals` | 当前页面 URL 等于 `expected` |
| `url_contains` | 当前页面 URL 包含 `expected` |
| `text_sequence` | 多元素文本序列等于 `expected` 列表；`mode: contains_order` 表示按顺序包含 |

示例：

```yaml
assertions:
  - type: text_contains
    locator: {strategy: bem_css, value: .message:last-child}
    expected:
      - 你好
      - 欢迎
```

属性断言和文本序列断言示例：

```yaml
assertions:
  - type: attribute_contains
    locator: {strategy: css, value: button.submit}
    attribute: aria-label
    expected: 提交
  - type: text_sequence
    locator: {strategy: css, value: .assistant-item}
    expected: [写作, 翻译, 总结]
    mode: contains_order
```

#### CLI 使用

初始化配置文件：

```shell
youqu web-spec init web_spec.yaml
youqu web-spec init path/to/web_spec.yaml --force
```

运行单个文件或目录：

```shell
youqu web-spec run examples/web_spec/specs --config examples/web_spec/web_spec.yaml
```

只加载校验并输出用例统计，不启动浏览器：

```shell
youqu web-spec run examples/web_spec/specs --config examples/web_spec/web_spec.yaml --dry-run
```

常用运行参数：

```shell
youqu web-spec run path/to/spec_or_dir --headed --verbose
youqu web-spec run path/to/spec_or_dir --report-dir report/web_spec/manual
youqu web-spec run path/to/spec_or_dir --no-screenshot
```

列举和筛选用例：

```shell
youqu web-spec list examples/web_spec/specs
youqu web-spec list examples/web_spec/specs --module 聊天区
youqu web-spec list examples/web_spec/specs --tag smoke
```

重建索引：

```shell
youqu web-spec index examples/web_spec/specs
```

运行 suite 目录，按 `suite.yaml` 声明顺序执行多个 case：

```shell
youqu web-spec suite examples/web_spec/smoke --config examples/web_spec/web_spec.yaml --dry-run
youqu web-spec suite examples/web_spec/smoke --config examples/web_spec/web_spec.yaml
```

suite 必须以文件夹组织，文件夹内必须包含 `suite.yaml` 或 `suite.yml`，顶层使用 `specs` 声明 case 列表；普通 case 顶层使用 `steps`。外部 `*.suite.yaml` / `*.suite.yml` 不再作为 suite 入口。`run` 执行当前路径下的 suite 和未被 suite 引用的独立 case，避免重复执行；`list/index` 会同时展示 case 和 suite；`suite` 命令用于只执行单个 suite 目录或目录内的 `suite.yaml`。

suite 用于把一个大流程拆成多个小 case，执行时会在同一个浏览器上下文、同一个 page 上按 `specs` 顺序接续运行。suite setup 会在共享 page 上执行；suite 开始时默认进入第一个 spec 的 `entry_url` / `entry_page`，后续 spec 不会在 case 边界自动重新导航。每个 spec 的入口字段仍用于单独运行该 spec，若 suite 中间需要跳转，请在 spec setup 或 steps 中显式声明。suite 内默认跳过单个 spec 的 teardown，最终清理由 suite-level `teardown` 负责，避免中间 case 清理 cookie 或恢复入口导致状态断裂。报告会按 suite 下的具体子用例分别生成，`single_case: true` 也只影响执行接续语义，不会把多个子用例揉成一个报告记录，方便定位到底是哪个子用例失败；汇总报告会记录 suite 元数据、case 顺序、source、fast_fail、timeout 和 suite 错误。

```yaml
id: web-spec-smoke
name: Web Spec 示例冒烟套件
fast_fail: true
specs:
  - specs/01.侧边栏布局验证.yaml
  - specs/02.标题栏主菜单验证.yaml
```

静态检查 spec 和 suite 质量，不启动浏览器：

```shell
youqu web-spec check examples/web_spec/specs
youqu web-spec check path/to/spec_or_dir
```

`check` 会检查 YAML/schema、suite 命名、兼容字段、脆弱 selector、过宽 text/css locator、长固定等待、URL 断言冗余 locator 等问题；存在 `ERROR` 时命令返回非 0，只有 `WARN` 时仍返回 0。

#### 报告输出

执行后会在 `report_dir` 下生成：

```text
report/web_spec/<timestamp>/
├── summary.json
├── summary.html
└── <spec-id>/
    ├── report.json
    ├── report.html
    └── step_<order>.png
```

`summary.*` 是批量运行汇总，单个 spec 目录下保存步骤、action、assertion、截图和错误信息。suite 运行时，每个子用例都会生成独立的 `<spec-id>/report.*`，汇总表的 `Suite` 列用于标识其所属 suite。

#### 索引行为

`youqu web-spec list <spec_dir>` 会读取 `<spec_dir>/index.yaml`。如果索引不存在，或索引版本低于当前 `WebSpecIndex.INDEX_VERSION`，命令会自动重建并写回 `index.yaml`。

如果希望显式刷新索引，可执行：

```shell
youqu web-spec index <spec_dir>
```

#### 常见错误

| 现象 | 处理方式 |
|------|----------|
| `Web spec 需要安装 Playwright` | 安装 `youqu-ai[webui]` 或源码环境执行 `pip install -e ".[webui]"` |
| 浏览器启动失败 | 执行 `playwright install chromium`，或检查系统依赖 |
| locator 匹配 0 个元素 | 检查页面是否进入正确状态，或调整 selector/text/test_id |
| locator 匹配多个元素 | 使用更精确 locator，或显式设置 `first: true` |
| `list` 后 `index.yaml` 变化 | 这是索引缺失或版本过旧触发的自动重建；确认后提交新索引即可 |
| `web-spec check` 报 `ERROR` | 修复对应 YAML/schema 问题后再运行；`WARN` 是质量建议，可按项目情况逐步处理 |

### 运行测试

在项目根目录下有一个 `manage.py` ，它是执行器入口，提供了本地执行、远程执行等的功能。

#### 本地执行

```shell
$ youqu manage.py run
```

在一些 CI 环境下使用命令行参数会更加方便：

```shell
$ youqu manage.py run -a apps/autotest_deepin_some -k "xxx" -t "yyy"
```

更多用法可以使用 `-h` 或 `--help` 查看。

通过配置文件 [setting/globalconfig.ini](https://github.com/linuxdeepin/youqu/blob/master/setting/globalconfig.ini) 也可以配置执行的各项参数。

#### 远程执行

远程执行就是用本地作为服务端控制远程机器执行，远程机器执行的用例相同。

使用 `remote` 命令：

```shell
$ youqu manage.py remote
```

#### 生成报告

测试执行后会生成 Allure 原始数据（`report/`），使用 Allure CLI 转为 HTML：

```shell
allure generate report/allure_results -o report/allure_html --clean
allure open report/allure_html
```

> 需要 Java 运行环境（`openjdk-11-jdk-headless`），`youqu doctor` 可自动安装。

---

## AI 集成

### MCP Server

YouQu 内置 MCP (Model Context Protocol) Server，将桌面 UI 自动化能力暴露为 MCP 工具，
使 AI 客户端（Claude、OpenCode 等）能够直接操控测试机上的桌面应用。

#### 功能概览

| 工具组 | 能力 | 示例 |
|--------|------|------|
| **AT-SPI 操作** | 元素查找、点击、输入、滚动、悬停 | 点击按钮、输入文本、展开菜单 |
| **键盘鼠标** | 按键、快捷键、点击、移动 | Enter、Ctrl+C、鼠标左键 |
| **窗口管理** | 窗口列表、激活、关闭、最大化/最小化 | 切换窗口、关闭弹窗 |
| **截图** | 全屏截图并保存 | 保存当前屏幕到证据目录 |
| **进程管理** | 查询进程、终止进程（保护关键进程） | 关闭应用进程 |
| **系统命令** | 执行只读命令（ps、gsettings 等） | 查询系统设置 |
| **VLM 视觉** | 视觉定位元素、视觉断言、自主测试 | "点击桌面左下角的终端图标" |
| **YAML 测试执行** | 用例查询、异步批量执行、进度轮询 | 按模块/标签筛选用例，分批执行 |

#### 启动 MCP Server

YouQu 安装后 MCP Server 即刻用：

#### VLM 配置

编辑 `setting/globalconfig.ini`，启用 VLM 并配置后端 API：

```ini
[vlm]
VLM_ENABLED = true
VLM_BASE_URL = https://api-inference.modelscope.cn/v1/
VLM_MODEL = Qwen/Qwen3-VL-8B-Instruct
VLM_API_KEY = your-api-key
```

VLM 需要 OpenAI 兼容的视觉语言模型 API（Ollama、ModelScope、vLLM 等），框架不内置模型。

#### 启动 MCP Server

**stdio 模式**（本地子进程）：

```shell
youqu mcp
```

适用于本地 AI 客户端通过 stdio 管道连接。

**Streamable HTTP 模式**（远程连接）：

```shell
youqu mcp --transport http --host 0.0.0.0 --port 8000
```

CLI 参数说明：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--transport` | `stdio` | `stdio`（本地子进程）/ `sse`（HTTP+SSE）/ `http`（Streamable HTTP，推荐远程） |
| `--host` | `127.0.0.1` | 监听地址，远程连接需设为 `0.0.0.0` |
| `--port` | `8000` | 监听端口 |

#### 客户端连接配置

**Claude**（原生支持 HTTP）：

```bash
claude mcp add --transport http youqu http://192.168.1.100:8000/mcp
```

**OpenCode** — 在项目 `opencode.json` 中配置 MCP server：

```json
{
  "mcp": {
    "youqu-mcp": {
      "enabled": true,
      "type": "remote",
      "url": "http://127.0.0.1:8066/mcp"
    }
  }
}
```

连接远程测试机时改为对应的 IP 和端口。

**SSH 隧道**（安全内网连接）：

无需在测试机暴露端口，通过 SSH 隧道转发：

```shell
ssh -L 8000:localhost:8000 user@test-machine
```

然后本地客户端连接 `http://127.0.0.1:8000/mcp`。

#### 客户端兼容矩阵

| AI 客户端 | stdio | Streamable HTTP |
|-----------|:-----:|:---------------:|
| Claude | ✅ | ✅ |
| OpenCode | ✅ | ✅ |

#### YAML 批量执行

MCP Server 支持异步批量执行 YAML 用例，AI 客户端无需等待全部完成：

| MCP 工具 | 用途 |
|----------|------|
| `yaml_list_tests` | 按应用/模块/标签查询用例列表 |
| `yaml_run_batch` | 提交批量执行任务，返回 `job_id`，立即返回 |
| `yaml_get_status` | 轮询任务进度（queued → running → completed/failed） |
| `yaml_cancel` | 取消任务（完成当前批次后停止） |

典型流程：

```
yaml_list_tests(app="deepin-music", module="播放")
    → 筛选需要执行的用例
yaml_run_batch(test_ids="test_001,test_002", batch_size=5)
    → job_id: "a1b2c3d4"
yaml_get_status(job_id="a1b2c3d4")  # 每 5s 轮询
    → {status: "running", progress: "batch 2/3"}
    → {status: "completed", result: {passed: 10, failed: 1}}
```

### 安装技能

YouQu 内置 AI 技能文件，供 Claude、OpenCode 等 AI 客户端使用。

安装方式一：通过 `youqu doctor` 交互式安装：

```shell
$ youqu doctor
```

doctor 会在所有检查完成后，检测到内置技能文件并提示您选择 AI 客户端，
自动将技能安装到对应目录：

| AI 客户端 | 安装目录 |
|-----------|----------|
| Claude | `~/.claude/skills/` |
| OpenCode | `~/.config/opencode/skills/` |

安装方式二：手动复制：

```shell
# 查找技能文件路径
python3 -c "import youqu; from pathlib import Path; print(Path(youqu.__file__).parent / 'skills')"

# 复制到对应客户端目录
cp -r $(python3 -c "import youqu; from pathlib import Path; print(Path(youqu.__file__).parent / 'skills')")/* ~/.claude/skills/
```

安装后重启 AI 客户端即可加载技能。

### 常用命令

供 AI 客户端和 CI 环境使用的 CLI 命令：

| 命令 | 用途 |
|------|------|
| `youqu at <subcommand>` | AT-SPI YAML 测试管道 (scan/record/merge/parse/tree-info/split/docs/precandidate/validate/generate/run/smoke/verify) |
| `youqu mcp` | 启动 MCP server (stdio/http) |
| `youqu doctor` | 检查并自动修复环境依赖（pydantic、pyatspi、Java、AT-SPI、辅助功能等） |
| `youqu startproject <name>` | 复制框架创建项目 |

---

## 开发者指南

### 编译安装

从源码构建和安装：

```shell
$ git clone https://github.com/linuxdeepin/youqu.git
$ cd youqu
$ python3 -m build
$ pip3 install dist/youqu_ai-*.whl
```

> 需要 `python3 -m pip install build` 安装构建工具。

### 发布到 PyPI

发布需要 `build` 和 `twine` 工具：

```shell
$ pip3 install --upgrade build twine
```

`~/.pypirc` 配置文件示例：

```ini
[pypi]
  username = __token__
  password = pypi-你的-PyPI-Token

[testpypi]
  username = __token__
  password = pypi-你的-TestPyPI-Token
```

> Token 在 https://pypi.org/manage/account/token/ 和 https://test.pypi.org/manage/account/token/ 生成。

发布流程（推荐先发到 TestPyPI 验证）：

```shell
# 1. 清理旧构建产物
$ rm -rf dist/ build/ *.egg-info

# 2. 构建
$ python3 -m build

# 3. 检查包质量
$ twine check dist/*

# 4. 先发到 TestPyPI 验证
$ twine upload --repository testpypi dist/*

# 5. 验证安装
$ pip install --index-url https://test.pypi.org/simple/ --no-deps youqu-ai

# 6. 确认无误后，发布到正式 PyPI
$ twine upload dist/*
```

### 开发环境

使用开发模式部署，直接 pip 安装依赖（不使用虚拟环境）：

```shell
$ bash env.sh -D
```

### 代码检查

```shell
$ ruff check .     # lint
$ ruff format .    # format
$ src/utils/pylint.sh apps/autotest_xxx   # pylint HTML 报告
```

### 单元测试

```shell
$ python -m pytest -c pytest-tests.ini tests/
```

### 贡献

[贡献文档](https://youqu.uniontech.com/CONTRIBUTING.html)

---

## 开源许可证

YouQu 在 [GPL-2.0](https://github.com/linuxdeepin/youqu/blob/master/LICENSE) 下发布。
