---
name: youqu-dev-suite-generator
version: "0.1.0"
description: >
  生成 YouQu dev-mode 自测套件 YAML（.suite.yaml 格式）。从 xlsx 原始用例、需求文档、
  功能描述、或测试步骤说明生成按模块组织的 suite 文件。触发：dev YAML 套件生成,
  自测用例生成, 提测自测套件, 开发者自测, dev-mode suite.
---

# YouQu Dev Suite Generator

生成 YouQu 开发人员自测套件（`.suite.yaml` 文件），产出默认放在 `dev-yaml/` 目录
下。单个 `.suite.yaml` 文件是一个测试套件，包含多个 spec（操作），按模块组织，支持
独立执行和标签过滤。

> **与 youqu-case-generator 的区别**：
> - youqu-case-generator 生成完整 YAML 用例（`test_*.yaml`），用于 CI/测试执行
> - 本 skill 生成 dev 自测套件（`*.suite.yaml`），用于开发人员快速验证，强调
>   执行效率、连贯性、按模块聚焦

## 输入来源

支持以下输入源：

| 来源 | 说明 |
|------|------|
| **xlsx 原始用例** | 测试团队提供的 Excel 测试用例，含步骤、预期结果 |
| **需求/功能描述** | PR 描述、需求文档、功能说明中的操作路径 |
| **测试步骤** | 用户直接提供的操作步骤文本 |

## 生成原则

1. **按模块组织** — 每个 `.suite.yaml` 对应一个模块（如"键盘快捷键"），包含该模块
   所有操作。避免粒度太细（单个操作一个 suite）或太粗（所有功能一个 suite）。
2. **每个 spec 独立可执行** — spec 之间不共享状态，每个 spec 可以单独 `--spec`
   执行。公共操作（启动应用）放在 suite `setup` 中。
3. **标签分类** — 给 spec 打标签便于过滤：`shortcut`（快捷键）、`ui`（UI 操作）、
   `menu`（菜单）、`dbus`（DBus 调用）、`smoke`（冒烟场景）。
4. **环境敏感用例自动 skip** — 对硬件/配置有依赖的 spec，添加 `skip` 字段说明原因
   （如"需双屏环境"、"需登录状态"），不使用 `skip` 时 spec 默认运行。
5. **高相关性操作合并** — 同一功能路径内的相关操作放在一个 spec 内，减少应用反复
   启动关闭。执行连贯的多个键盘/鼠标操作优于每次只做一个操作然后重启。
6. **不生成不可自动化的用例** — 需要人工判断、视觉验证、模棱两可的步骤不应生成
   为 spec（或标记 skip 并注明原因）。

## 输出格式

输出为 `.suite.yaml` 文件，写入 `dev-yaml/` 目录。文件命名：`<模块名>.suite.yaml`。

完整格式示例：

```yaml
name: "键盘快捷键自测"
app: "deepin-reader"
module: "键盘"
description: "对阅读器键盘快捷键的快速自测"
tags: ["shortcut", "smoke"]

# 环境预检 (可选)
env_check:
  - type: process
    name: "deepin-reader"
    expect: "not_running"
    # spec_ids: ["s1", "s2"]  # 仅对指定 spec 生效

# 套件级 setup（在所有 spec 前执行一次）
setup:
  - action: session_start
    command: "deepin-reader"

# 套件级 teardown（在所有 spec 后执行一次）
teardown:
  - action: session_stop

# 测试操作列表
specs:
  - id: shortcut_copy
    name: "Ctrl+C 复制文字"
    tags: ["shortcut"]
    steps:
      - action: keyboard_hot_key
        keys: "Ctrl+C"
      - action: wait
        wait: 0.5

  - id: shortcut_fullscreen
    name: "F11 全屏切换"
    tags: ["shortcut"]
    skip: "全屏功能在部分窗口管理器下不可用"
    steps:
      - action: keyboard_press
        keys: "F11"
      - action: wait
        wait: 1.0

  - id: menu_about
    name: "打开关于对话框"
    tags: ["menu", "ui"]
    steps:
      - action: main_menu_comb
        selector: {name: "帮助"}
        items: ["帮助", "关于"]
```

## 字段说明

| 字段 | 必填 | 说明 |
|------|------|------|
| `name` | 是 | 套件显示名称 |
| `app` | 否 | 目标应用名 |
| `module` | 否 | 模块分类 |
| `env_check` | 否 | 环境预检列表 |
| `env_check[].type` | 是 | 检测类型：`process` (进程) / `file_exists` (文件) |
| `env_check[].name` | 是 | 进程名或文件路径 |
| `env_check[].expect` | 是 | 期望状态：`not_running` / `running` / `exists` / `not_exists` |
| `env_check[].spec_ids` | 否 | 仅对这些 spec 生效；不填则对整个套件生效 |
| `setup` | 否 | 套件级初始化步骤列表 |
| `specs` | 是 | 可独立执行的 spec 列表（至少 1 个） |
| `specs[].id` | 是 | spec 唯一标识（字母数字下划线，不能重复） |
| `specs[].name` | 否 | spec 显示名称 |
| `specs[].tags` | 否 | 标签列表，用于过滤 |
| `specs[].skip` | 否 | 跳过原因。有值时该 spec 默认跳过不执行 |
| `specs[].steps` | 是 | 操作步骤列表 |
| `teardown` | 否 | 套件级清理步骤列表 |

### 操作类型（specs[].steps[].action）

支持与 `test_*.yaml` 相同的操作类型，但 **不支持 `ref` 字段**（suite 模式没有
`elements.yaml` 引用机制）。元素定位须使用 inline `selector`，坐标须直接写 `x`/`y`。

| action | 参数 | 说明 |
|--------|------|------|
| `session_start` | `command` | 启动应用 |
| `session_stop` | — | 停止应用 |
| `keyboard_press` | `keys` | 按键 |
| `keyboard_hot_key` | `keys` | 快捷键（如 `Ctrl+C`） |
| `keyboard_type` | `text` | 输入文本 |
| `keyboard_type_text` | `text` | 输入文本（同 `keyboard_type`） |
| `mouse_click` | `x`, `y` 或 `selector` | 鼠标点击 |
| `mouse_right_click` | `x`, `y` 或 `selector` | 鼠标右击 |
| `mouse_double_click` | `x`, `y` 或 `selector` | 鼠标双击 |
| `mouse_scroll` | `amount` | 滚轮滚动（正数向下） |
| `mouse_drag` | `x`, `y` 或 `selector` | 拖拽到目标位置 |
| `element_action` | `selector`, `do` | AT-SPI 元素操作（`do`: click/right_click/double_click） |
| `element_set_value` | `selector`, `text` | 设置元素文本值 |
| `main_menu_comb` | `items` / `selector` | 主菜单导航 |
| `context_menu_comb` | `items` / `selector`, `x`, `y` | 右键菜单导航 |
| `dbus_call` | `command` | DBus 方法调用 |
| `dbus_get_property` | `command` | DBus 属性读取 |
| `wait` | `wait` | 等待（秒） |
| `screenshot` | — | 截图 |

## CLI 验证

生成后通过 `youqu dev` 系列命令验证：

```bash
# 列出所有套件
youqu dev list

# 查看具体套件详情
youqu dev list <套件名>

# 运行整个套件（子进程模式，默认）
youqu dev run <套件名>

# 仅运行指定 spec
youqu dev run <套件名> --spec s1,s3

# 按标签过滤
youqu dev run <套件名> --tag shortcut

# 跳过环境预检
youqu dev run <套件名> --skip-env-check

# 进程内模式（快速，无子进程隔离）
youqu dev run <套件名> --fast
```

## 环境检查说明

自测环境可能缺少某些条件（特定硬件、网络、登录状态等）。对存在环境依赖的 spec，
建议添加 `env_check` 项而非直接 skip，使得在环境满足条件时可以自动运行。

```yaml
env_check:
  - type: process
    name: "deepin-reader"
    expect: "not_running"
    spec_ids: ["shortcut_copy"]  # 仅对部分 spec 检查
```
