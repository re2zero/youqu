# Multica 自动化测试 — Issue 提示词

> 执行 Agent 必须遵循 multica agent 提示词的完整执行流程、参数说明、报告模板与禁止操作清单。

---

## 1. 代码增量测试

### 标题与标签

- 标题：`[增量测试] {应用名} {日期}`
- labels：`automation`, `multica`, `incremental-test`

### 目标

对 **{应用名}** 的代码变更进行同步、分析、编译 deb 安装并运行相关模块的 YAML 用例测试。

### 环境信息

| 配置项 | 值 |
|--------|-----|
| 项目路径 | `{PROJECT_ROOT}/` |
| AT 测试目录 | `{AT_PATH}` (默认 `tests/at/yaml/`) |
| 测试文件目录 | `{TEST_FILES_DIR}` (默认 `tests/at/files/`，供 YAML 变量替换) |
| 应用名 | `{APP_NAME}` |
| apt 包名 | `{APP_PACKAGE}` |
| 应用二进制 | `{APP_BINARY}` |
| 分支 | `{BRANCH}` (默认 `master`) |
| 安装密码 | 环境变量 `INSTALL_PASSWORD` |
| Issue ID | `{ISSUE_ID}` |
| 测试模式 | `incremental` |

---

## 2. 自测智能体

### 标题与标签

- 标题：`[自测] {应用名} {PR 或 Commit 范围}`
- labels：`automation`, `multica`, `self-test`

### 目标

研发触发对 **{应用名}** 的代码变更进行同步、分析、编译 deb 安装并运行相关模块的 YAML 用例测试。

### 环境信息

| 配置项 | 值 |
|--------|-----|
| 项目路径 | `{PROJECT_ROOT}/` |
| AT 测试目录 | `{AT_PATH}` (默认 `tests/at/yaml/`) |
| 测试文件目录 | `{TEST_FILES_DIR}` (默认 `tests/at/files/`，供 YAML 变量替换) |
| 应用名 | `{APP_NAME}` |
| apt 包名 | `{APP_PACKAGE}` |
| 应用二进制 | `{APP_BINARY}` |
| 分支 | `{BRANCH}` (默认 `master`) |
| 安装密码 | 环境变量 `INSTALL_PASSWORD` |
| 相关 PR | `{PR_URL}` |
| Issue ID | `{ISSUE_ID}` |
| 测试模式 | `self-test` |

---

## 3. 全量测试

### 标题与标签

- 标题：`[全量测试] {应用名} {日期}`
- labels：`automation`, `multica`, `full-test`

### 目标

对 **{应用名}** 使用 apt 安装仓库最新版应用并运行全量 YAML 用例测试。

### 环境信息

| 配置项 | 值 |
|--------|-----|
| 项目路径 | `{PROJECT_ROOT}/` |
| AT 测试目录 | `{AT_PATH}` (默认 `tests/at/yaml/`) |
| 测试文件目录 | `{TEST_FILES_DIR}` (默认 `tests/at/files/`，供 YAML 变量替换) |
| 应用名 | `{APP_NAME}` |
| apt 包名 | `{APP_PACKAGE}` |
| 应用二进制 | `{APP_BINARY}` |
| 安装密码 | 环境变量 `INSTALL_PASSWORD` |
| Issue ID | `{ISSUE_ID}` |
| 测试模式 | `full-test` |
