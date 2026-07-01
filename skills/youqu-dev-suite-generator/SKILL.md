---
name: youqu-dev-suite-generator
version: "0.1.0"
description: >
  生成 YouQu dev-mode 自测套件 YAML（.suite.yaml 格式）。从 xlsx 原始用例、需求文档、
  功能描述、或测试步骤说明生成按模块组织的 suite 文件。触发：dev YAML 套件生成,
  自测用例生成, 提测自测套件, 开发者自测, dev-mode suite.
---

# YouQu Dev Suite Generator

生成 YouQu 开发人员自测套件（`.suite.yaml` 文件），产出 **必须** 放在 `autotest/dev-yaml/`
目录下。单个 `.suite.yaml` 文件是一个测试套件，包含多个 spec（操作），按模块组织，支持
独立执行和标签过滤。

> **路径约束（MUST）**：所有 `.suite.yaml` 文件必须写入 `autotest/dev-yaml/<模块名>/`
> 目录下，**按模块创建子目录**。子目录名 = 模块名，suite 文件 stem = 操作组名。
> 一个模块子目录可以包含多个 suite 文件（按操作组拆分）。
> 禁止在项目根目录创建 `dev-yaml/`，禁止将 `.suite.yaml` 直接平铺在 `autotest/dev-yaml/`
> 根层——必须放在模块子目录内。CLI 递归扫描 `autotest/dev-yaml/**/*.suite.yaml`，
> `youqu dev run <操作组名>` 通过 stem 匹配定位 suite 文件。
>
> 目录结构示例：
> ```
> autotest/dev-yaml/
> ├── 文件操作/
> │   └── 文件操作.suite.yaml
> ├── 菜单/
> │   ├── 主菜单.suite.yaml
> │   └── 右键菜单.suite.yaml
> └── 搜索/
>     └── 搜索.suite.yaml
> ```
>
> **匹配规则**：`youqu dev run <name>` 按以下顺序匹配 suite 文件：
> 1. suite 文件 stem 精确等于 `name`
> 2. suite 文件名前缀匹配 `name` 或 `name-*`
> 3. 父目录名等于 `name` 且文件 stem 也等于 `name`
>
> 当模块包含多个操作组时，按操作组名运行（如 `youqu dev run 主菜单`），
> 不按模块名运行（`youqu dev run 菜单` 无法定位到具体文件）。

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

## xlsx 智能过滤

原始 xlsx 用例中包含大量不可自动化的用例。生成 suite 前必须逐条分析，仅将可自动化的用例转为 spec。

### 判断原则

对每条用例，判断其**操作步骤**和**预期结果**是否可通过以下手段自动化完成：

- AT-SPI 元素操作（点击、输入、读取属性）
- 键盘/鼠标模拟（按键、快捷键、点击、拖拽）
- DBus 接口调用
- 命令行执行
- 文件系统检查

满足以下任一条件的用例**不可自动化**，不生成 spec：

- 需要人工视觉主观判断（颜色对比、布局美观度、动画流畅度、主观体验评价）
- 需要物理设备插拔（U 盘、打印机、扫描仪、外部存储）
- 需要跨设备协同（手机联动、蓝牙传输、投屏）
- 需要触摸屏/多点触控/手势操作（当前框架不支持触摸事件模拟）
- 需要系统级权限（root/sudo 操作、系统级配置修改）
- 需要电源状态变更（断电、强制重启、休眠/唤醒）
- 需要多屏/显示模式切换（双屏、分辨率切换、投影）
- 需要系统升级/版本迁移
- 性能/压力/负载测试（不属于功能验证范畴）

**边界情况**：如果某用例的部分步骤可自动化但预期结果需要人工确认，将可自动化的步骤生成 spec，预期结果用 `screenshot` 动作截图辅助人工确认，并添加 `skip` 字段说明不可全自动验证的部分。

### spec 选取

每个模块按优先级选取可自动化用例转为 spec：核心功能 > 高频操作 > 边界场景。spec 数量取决于模块复杂度和用例质量，不设固定上限或下限——宁可少而精，不可多而空。

### 过滤报告

生成 suite 后**必须**输出过滤统计，包含以下信息（格式自定）：

- 原始用例总数、可自动化数及占比、不可自动化数及占比
- 不可自动化用例按原因归类统计（类别由 LLM 根据实际数据自行归纳）
- 生成的模块套件清单：模块名、spec 数量

## 生成原则

1. **按模块组织** — 每个模块对应 `autotest/dev-yaml/` 下的一个子目录（子目录名 = 模块名）。
   模块内按**操作组**拆分 suite 文件，每个 `.suite.yaml` 对应一个操作组（如"主菜单"、
   "右键菜单"、"快捷键"）。操作组少时一个 suite 即可；操作组多时拆成多个 suite 放在
   同一模块子目录下。避免粒度太细（单个操作一个 suite）或太粗（所有模块一个 suite）。
2. **每个 spec 独立可执行** — spec 之间不共享状态，每个 spec 可以单独 `--spec`
   执行。公共操作（启动应用）放在 suite `setup` 中。
3. **标签分类** — 给 spec 打标签便于过滤：`shortcut`（快捷键）、`ui`（UI 操作）、
   `menu`（菜单）、`dbus`（DBus 调用）、`smoke`（冒烟场景）。
4. **环境敏感用例自动 skip** — 对硬件/配置有依赖的 spec，添加 `skip` 字段说明原因
   （如"需双屏环境"、"需登录状态"），不使用 `skip` 时 spec 默认运行。
5. **高相关性操作合并** — 同一功能路径内的相关操作放在一个 spec 内，减少应用反复
   启动关闭。执行连贯的多个键盘/鼠标操作优于每次只做一个操作然后重启。
6. **不生成不可自动化的用例** — 按「xlsx 智能过滤」判断原则逐条过滤，不可自动化的
   用例不生成 spec。过滤统计报告必须随 suite 一起输出。

## 输出格式

输出为 `.suite.yaml` 文件，写入 `autotest/dev-yaml/` 目录。

**文件命名（MUST）**：`<操作简称>.suite.yaml`。`<操作简称>` 是该套件所测操作的简短
描述名（2-4 个中文字符或对应英文），**不得使用应用名**。

| 正确 | 错误 |
|------|------|
| `右键.suite.yaml` | `deepin-reader.suite.yaml` |
| `快捷键.suite.yaml` | `reader.suite.yaml` |
| `文件打开.suite.yaml` | `文件管理器.suite.yaml` |

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

支持与 `test_*.yaml` 相同的操作类型。

> **元素定位约束（MUST）**：suite 模式 **不使用 `elements.yaml`**，所有元素定位
> **必须** 使用 inline `selector` 字段写在每个 step 内。**禁止使用 `ref` 字段**。
> 坐标须直接写 `x`/`y`。
>
> ```yaml
> # ✅ 正确 — inline selector
> - action: mouse_click
>   selector: {name: "确定"}
>
> # ❌ 禁止 — ref 引用 elements.yaml
> - action: mouse_click
>   ref: "confirm_button"
> ```

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
