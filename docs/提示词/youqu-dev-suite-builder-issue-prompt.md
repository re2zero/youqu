# YouQu Dev Suite 构建智能体 — Multica Issue 提示词

## 标题与标签

- 标题：`[Dev自测套件构建] {应用名} suite 套件构建`
- labels：`automation`, `youqu`, `dev-suite-builder`

---

## 目标

为 **{应用名}** 创建或补全 YouQu dev-mode 自测套件（`.suite.yaml`），并推送到自动化测试分支。

本 Issue 只做一件事：**只生成 `.suite.yaml` 套件文件，不生成 `test_*.yaml` 用例，不生成 Python 用例，不修改框架源码，不批量执行测试**。

## 严格约束

- **严禁生成 `test_*.yaml` 用例**
- **严禁生成 Python 用例**
- **禁止生成 `autotest/case/`**
- **禁止生成 `autotest/widget/`**
- **禁止生成任何 `.py` 测试文件**
- **禁止使用 `ref` 字段**（suite 模式没有 `elements.yaml` 引用机制）
- **每个 suite 必须设置 `status` 字段**（`draft` 或 `ready`），禁止遗漏

> 执行 Agent 必须加载 `youqu-dev-suite-generator` 技能并遵循 agent 提示词的完整执行流程与禁止操作清单。

---

## 环境信息

| 配置项 | 值 |
|--------|-----|
| 项目路径 | `{PROJECT_ROOT}/` |
| 基础分支 | `{SOURCE_BRANCH}` |
| 自动化测试分支 | `{TARGET_BRANCH}` |
| 当前工作分支 | `{BASE_BRANCH}` |
| dev 套件目录 | `{DEV_YAML_PATH}` |
| 应用名 | `{APP_NAME}` |
| 应用二进制 | `{APP_BINARY}` |
| 桌面环境 | `{DESKTOP_ENV}` |
| Issue ID | `{ISSUE_ID}` |

---

## 职责

本 Issue 只做三件事：

1. **检查已有 `.suite.yaml` 套件完整度**
2. **只生成 `.suite.yaml` 套件文件**
3. **提交并推送到自动化测试分支**

---

## 执行参数

| 参数 | 必须 | 默认值 | 说明 |
|------|------|--------|------|
| PROJECT_ROOT | 是 | — | 项目根路径 |
| SOURCE_BRANCH | 是 | — | 自动化测试分支基于该分支创建 |
| TARGET_BRANCH | 是 | — | 自动化测试分支名称 |
| BASE_BRANCH | 是 | — | 当前工作分支 |
| DEV_YAML_PATH | 否 | `autotest/dev-yaml/` | dev 套件目录 |
| APP_NAME | 是 | — | 应用名 |
| APP_BINARY | 是 | — | 应用二进制路径 |
| DESKTOP_ENV | 否 | `yes` | 桌面环境是否可用（`yes`/`no`），影响 AT-SPI 树发现 |
| ISSUE_ID | 是 | — | multica issue ID |
| MODULE | 否 | — | 指定模块 |
| TAG | 否 | — | 指定标签 |
| BATCH_SIZE | 否 | 5 | 每批套件数 |
| SPEC_TIMEOUT | 否 | 60 | 单 spec 超时（秒） |

---

## 报告模板

Agent 完成后必须按以下格式输出报告：

```markdown
## YouQu Dev Suite 构建报告

### 1. 任务信息
- 项目: <PROJECT_ROOT>
- 应用: <APP_NAME>
- 基础分支: <SOURCE_BRANCH>
- 自动化分支: <TARGET_BRANCH>
- Issue: <ISSUE_ID>

### 2. 已有套件检查
- 是否已有 suite: 是/否
- 套件数量: <N>
- 完整性问题: <列出或缺失说明>

### 3. 新增/补全内容
- 新增模块: <module>
- 新增套件: <suite list>
- 新增 spec 数量: <N>
- 环境检查项: <env_check 摘要>

### 4. 验证结果
- `youqu dev list`: 通过/失败
- 冒烟验证（可选）: 通过/失败/跳过

### 5. 提交与推送
- 分支: <TARGET_BRANCH>
- Commit: <commit hash>
- 推送结果: 成功/失败

### 6. 结论
- 构建完成/存在阻塞
- 后续建议
```
