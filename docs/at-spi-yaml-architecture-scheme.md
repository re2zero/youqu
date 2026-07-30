# YouQu AT-SPI YAML 测试框架技术方案：AT-Tree + Element-Mappings 架构

## 1. 方案背景与目标

### 1.1 背景
- 现有 YAML 用例生成依赖动态 MCP 或 `youqu at record` 操作，存在不可靠性和状态依赖问题。
- 动态捕获的 AT-SPI 树包含机器特定状态（如坐标、动态内容），影响用例跨机器可移植性。
- 传统为每个 xlsx 用例生成独立 YAML 文件，导致应用启动/销毁（setup/teardown）开销巨大，且用例数量庞大难以维护。

### 1.2 目标
- 提高 YAML 用例的稳定性和准确性，通过**静态源码扫描 + 动态 AT-SPI 验证**生成结构确定的 `at-tree`。
- 通过**操作与元素映射表（element-mappings.yaml）**生成可执行的 YAML 用例，完全通过脚本/CLI 实现，无 LLM 参与。
- 引入 **Test Suite（测试套件）** 概念，将相关模块的测试聚合，减少启动/销毁开销，方便动态指定测试。
- 断言对应具体 AT 元素或 VLM 截图，确保可验证性；内置应用崩溃检测，确保异常及时反馈到测试结果。
- 统一 CLI 命令入口为 `youqu at`，对应 `tests/at/` 目录结构。

---

## 2. 核心概念定义

1. **`at-tree.yaml`（应用结构树）**：
   - 由 `youqu at dump dtk` 生成，包含应用的稳定 UI 结构（窗口、菜单、按钮等元素的层级和 AT-SPI 属性 `name`, `role`, `accessible_id`）。
   - 去除动态内容噪音（如具体文件名、临时窗口、机器特定坐标）。

2. **`cases.yaml`（结构化测试用例）**：
   - 由 `youqu at parse` 从 xlsx/需求文档生成。
   - 包含固定的业务操作步骤和期望结果，**不包含具体元素选择器**。

3. **`element-mappings.yaml`（操作与元素映射表）**：
   - 由 `youqu at map` 生成。
   - 将 `cases.yaml` 中的抽象操作关键词映射到 `at-tree.yaml` 中的具体元素引用（`ref`）和 AT-SPI 选择器。

4. **Test Suite YAML（测试套件文件）**：
   - 由 `youqu at generate` 生成。
   - 将相关模块的测试（如菜单下的"主题"、"新窗口"、"保存"）整理为一个 Test Suite 文件，共享同一个应用会话（一次 `session_start` 和 `session_stop`），减少准备和销毁时间。

---

## 3. 目录结构设计

`youqu at ...` 命令的实现是在 `youqu` 框架项目下（如 `cli/at_dump.py`, `cli/at_parse.py`, `cli/at_map.py`, `cli/at_generate.py`, `cli/at_run.py`），而具体应用项目的 `tests/at/` 目录结构如下：

```
<app_project>/
├── tests/
│   └── at/
│       ├── at-tree.yaml                  # 结构化 AT-SPI 树（中间产物）
│       ├── element-mappings.yaml         # 操作与元素映射表（中间产物）
│       ├── cases.yaml                    # 结构化测试用例：固定步骤与期望（中间产物）
│       └── yaml/                         # 最终生成的可执行 YAML 测试用例
│           ├── elements.yaml             # 元素注册表
│           ├── 播放/
│           │   └── test_music_001.yaml
│           └── 菜单/
│               └── menu_test_suite.yaml  # 测试套件文件
```

---

## 4. CLI 命令结构设计：`youqu at`

新增 `youqu at` 命令空间，专门用于 `tests/at/` 目录下的 AT-SPI YAML 测试框架全生命周期操作：

### 4.1 `youqu at dump <type>` —— AT-Tree 导出
用于启动应用并导出结构化的 AT-SPI 树。
- **命令示例**：`youqu at dump dtk --app <app_id> --src <src_dir> --output tests/at/`
- **说明**：`dtk` 标识基于 DTK 开发的 Qt 应用。后续可扩展 `qml`、`web` 等类型。
- **输出**：`tests/at/at-tree.yaml`

### 4.2 `youqu at parse` —— 结构化用例解析
从 xlsx 或需求文档中解析并整理测试用例。
- **命令示例**：`youqu at parse --input <xlsx_or_req_file> --output tests/at/cases.yaml`
- **说明**：生成包含固定操作步骤和期望的 `cases.yaml`。

### 4.3 `youqu at map` —— 生成元素映射表
将 `cases.yaml` 中的操作关键词与 `at-tree.yaml` 中的元素进行映射，生成 `element-mappings.yaml`。
- **命令示例**：`youqu at map --at-tree tests/at/at-tree.yaml --cases tests/at/cases.yaml --output tests/at/element-mappings.yaml`
- **输出**：`tests/at/element-mappings.yaml`

### 4.4 `youqu at generate` —— 生成 YAML 测试用例
根据 `cases.yaml` 和 `element-mappings.yaml` 填充替换步骤，生成可执行的 YAML 用例文件（支持生成独立用例或 Test Suite 批次文件）。
- **命令示例**：`youqu at generate --cases tests/at/cases.yaml --mappings tests/at/element-mappings.yaml --output tests/at/yaml/`
- **输出**：`tests/at/yaml/<module>/test_*.yaml` 或 `tests/at/yaml/<module>/menu_test_suite.yaml`

### 4.5 `youqu at run` —— 执行 YAML 测试用例
解析并运行 `tests/at/yaml/` 下的 YAML 测试用例，支持按 Test Suite 动态指定测试。
- **命令示例**：`youqu at run [--testdir tests/at/yaml] [--suite <suite_name>]`
- **说明**：使用 `youqu at run --testdir <dir>` 执行引擎，执行 `tests/at/yaml/` 目录的 AT-SPI YAML 测试。支持通过 `--suite` 参数运行特定的 Test Suite 批次测试。

---

## 5. 工作流 Phase 设计

- **Phase 1: AT-Tree 导出**：执行 `youqu at dump dtk ...`，输出 `tests/at/at-tree.yaml`。
- **Phase 2: 结构化用例生成**：执行 `youqu at parse ...`，输出 `tests/at/cases.yaml`。
- **Phase 3: 元素映射生成**：执行 `youqu at map ...`，输出 `tests/at/element-mappings.yaml`。
- **Phase 4: YAML 用例生成**：执行 `youqu at generate ...`，生成 `tests/at/yaml/<module>/test_*.yaml` 或 `menu_test_suite.yaml`。
- **Phase 5: YAML 用例执行**：执行 `youqu at run ...`。

---

## 6. 核心文件格式示例

### 6.1 `at-tree.yaml`（应用结构树）
```yaml
app: dde-file-manager
structure:
  windows:
    - role: window
      object_name: mainWindow
      children:
        - role: menu_bar
          children:
            - role: menu
              name: "文件"
              accessible_id: file-menu
        - role: toolbar
          children:
            - role: push button
              name: "播放/暂停"
              accessible_id: play-pause-btn
```

### 6.2 `cases.yaml`（结构化测试用例）
```yaml
cases:
  - id: "test_music_001"
    module: "播放"
    title: "播放/暂停功能测试"
    steps:
      - "启动音乐应用"
      - "点击播放/暂停按钮"
      - "验证播放状态改变"
    expectations:
      - "应用成功启动"
      - "播放/暂停按钮状态切换"
      - "音乐开始/暂停播放"
```

### 6.3 `element-mappings.yaml`（操作与元素映射表）
```yaml
mappings:
  - operation_keyword: "启动音乐应用"
    operation_type: "session_start"
    element_ref: "app_process"
    command: "deepin-music"

  - operation_keyword: "点击播放/暂停按钮"
    operation_type: "element_action"
    element_ref: "play_pause_btn"
    selector:
      name: "播放/暂停"
      role: "push button"
    do: "click"

  - operation_keyword: "验证播放状态改变"
    operation_type: "assert_state"
    element_ref: "play_pause_btn"
    selector:
      name: "播放/暂停"
      role: "push button"
    assert_type: "state"
```

### 6.4 `menu_test_suite.yaml`（Test Suite 批次文件示例）
```yaml
# tests/at/yaml/菜单/menu_test_suite.yaml
name: menu_test_suite
app: dde-file-manager
description: "菜单相关功能测试套件（主题、新窗口、保存）"
module: "菜单"
setup:
  - action: session_start
    command: "dde-file-manager"
suites: # 测试套件列表，共享同一个应用会话
  - id: "menu_theme_001"
    steps:
      - action: element_action
        ref: file_menu
        do: click
      - action: element_action
        ref: theme_menu_item
        do: click
    assert_steps:
      - action: assert_element_exists
        ref: theme_settings_panel
        role: window
  - id: "menu_new_window_002"
    steps:
      - action: element_action
        ref: file_menu
        do: click
      - action: element_action
        ref: new_window_menu_item
        do: click
    assert_steps:
      - action: assert_window_exists
        selector:
          role: window
          name_pattern: ".*新窗口.*"
teardown:
  - action: session_stop
```

---

## 7. 断言与异常检测设计

### 7.1 断言对应具体 AT 元素
断言不应是"新窗口打开"这种无法自动验证的文本，而应对应具体的 AT 元素状态或动作，让 `youqu` 检测：

**标准 AT 元素断言示例**：
```yaml
    assert_steps:
      - action: assert_element_exists
        ref: theme_settings_panel
        role: window
      # 或
      - action: assert_window_exists
        selector:
          role: window
          name_pattern: ".*新窗口.*"
```

### 7.2 视觉效果断言（截图 + VLM）
如果是视觉效果或状态无法通过 AT-SPI 表达，使用截图并保存，后台通过 VLM 实现断言：
```yaml
    assert_steps:
      - action: screenshot_save
        path: "vlm_evidence/theme_change.png"
      - action: assert_vlm
        prompt: "检查界面主题是否已更改为深色模式"
        evidence: "vlm_evidence/theme_change.png"
```

### 7.3 应用闪退/崩溃检测
执行过程中若出现应用闪退、崩溃等，需要重点检测并反应到结果中。
- **执行引擎监控**：`youqu at run` 的 executor 应监控应用进程状态。在 `session_start` 后，若应用非正常退出（进程死亡、非零退出码），executor 应捕获该异常，标记测试为 **Failed (Crash)**，并记录崩溃日志或核心转储信息。
- **YAML 中的体现**：无需在 YAML 中显式写崩溃检测，executor 在 `steps` 或 `assert_steps` 执行期间若检测到进程异常终止，自动中断并报告失败。

---

## 8. 方案优势总结

1. **解耦设计**：`at-tree.yaml`（结构）、`element-mappings.yaml`（映射）、`cases.yaml`（业务步骤）三者分离，互不干扰。修改 UI 结构只需更新 `at-tree.yaml` 和 `element-mappings.yaml`，无需修改业务 `cases.yaml`。
2. **高可维护性**：所有中间步骤输出为脚本和文档（YAML 文件），方便后期维护和新增用例。
3. **高准确性与稳定性**：断言对应具体 AT 元素或 VLM 截图，避免模糊文本导致的验证失败；通过 `element-mappings.yaml` 的映射表确保操作步骤与实际元素精确对应。
4. **跨机器可移植性**：生成的 YAML 用例基于 AT-SPI 选择器（`name`, `role`），不依赖机器特定坐标，可在不同环境下执行。
5. **性能优化与健壮性**：Test Suite 聚合相关测试，应用只启动和关闭一次，大幅减少 setup/teardown 时间消耗；内置应用崩溃检测，确保异常及时反馈到测试结果。