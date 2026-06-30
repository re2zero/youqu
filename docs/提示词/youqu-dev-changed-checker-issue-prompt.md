# YouQu Dev 自测变更检查智能体 — Multica Issue 提示词

## 标题与标签

- 标题：`[Dev自测变更检查] {应用名} {PR 或 Commit 范围}`
- labels：`automation`, `youqu`, `dev-changed-checker`

---

## 目标

对 **{应用名}** 的代码变更进行同步、rebase、影响分析、相关 Dev 自测套件查找、必要的补充套件、编译/安装验证、测试执行和结果报告。

本 Issue 只做一件事：**基于指定分支和变更范围，验证代码修改对 YouQu Dev 自测套件的影响**。

---

## 环境信息

| 配置项 | 值 |
|--------|-----|
| 项目路径 | `{PROJECT_ROOT}/` |
| 基础分支 | `{SOURCE_BRANCH}` |
| 当前自动化测试分支 | `{BASE_BRANCH}` |
| 目标同步分支 | `{TARGET_BRANCH}` |
| Dev 套件目录 | `{DEV_YAML_PATH}` |
| 应用名 | `{APP_NAME}` |
| 应用二进制 | `{APP_BINARY}` |
| 实际测试应用路径 | `{APP_PATH}` |
| 编译目录 | `{BUILD_DIR}` |
| 编译命令 | `{BUILD_COMMAND}` |
| 安装命令 | `{INSTALL_COMMAND}` |
| 安装密码环境变量 | `{INSTALL_PASSWORD_ENV}` |
| 相关 PR | `{PR_URL}` |
| Issue ID | `{ISSUE_ID}` |

> 执行 Agent 必须遵循 agent 提示词的完整执行流程与约束。
> 需要新增 Dev 套件时，调用 `youqu-dev-suite-generator` 技能。

---

## 职责

本 Issue 只做五件事：

1. **拉取并 rebase 到当前自动化测试分支**
2. **分析代码修改信息**
3. **查找或新增相关 Dev 自测套件**
4. **编译/安装后运行相关测试**
5. **输出完整变更影响检查报告**

---

## 执行参数

| 参数 | 必须 | 默认值 | 说明 |
|------|------|--------|------|
| PROJECT_ROOT | 是 | — | 项目根路径 |
| SOURCE_BRANCH | 是 | — | 自动化测试分支基于该分支创建 |
| BASE_BRANCH | 是 | — | 当前自动化测试分支 |
| TARGET_BRANCH | 是 | — | 需要同步到的上游分支 |
| DEV_YAML_PATH | 是 | `autotest/dev-yaml/` | Dev 自测套件目录 |
| APP_NAME | 是 | — | 应用名 |
| APP_BINARY | 是 | — | 应用二进制路径 |
| APP_PATH | 是 | 来自 suite `app` 字段 basename；未指定时同 `APP_BINARY` | 实际测试应用路径 |
| BUILD_DIR | 否 | `${PROJECT_ROOT}/build` | 编译目录 |
| BUILD_COMMAND | 否 | — | 用户/Issue 指定；LLM 可检查项目技术栈辅助确认，但不得自行发明 |
| INSTALL_COMMAND | 否 | — | 用户/Issue 指定；LLM 可检查项目技术栈辅助确认，但不得自行发明 |
| PR_URL | 否 | — | 相关 PR 地址 |
| ISSUE_ID | 是 | — | multica issue ID |
| MODULE | 否 | — | 指定模块 |
| TAG | 否 | — | 指定标签 |
| SPEC_TIMEOUT | 否 | 60 | 单 spec 超时（秒） |

---

## 报告模板

Agent 完成后必须按以下格式输出报告：

```markdown
## YouQu Dev 自测变更检查报告

### 1. 同步信息
- 项目: <PROJECT_ROOT>
- 基础分支: <SOURCE_BRANCH>
- 当前分支: <BASE_BRANCH>
- 目标分支: <TARGET_BRANCH>
- rebase 结果: 成功/失败

### 2. 代码修改信息
- 变更统计: <git diff --stat>
- commit 列表: <git log>
- 相关 PR: <PR_URL 或缺失说明>

### 3. 影响范围
- 影响模块: <module>
- 影响功能点: <feature>
- 变更类型: <change_type>
- 影响判断: 有影响/无影响

### 4. Dev 自测套件覆盖
- 是否已有 Dev 套件: 是/否
- 相关套件: <suite list>
- 覆盖状态: 充分/部分/缺失
- 新增套件: <suite list 或无>

### 5. 运行结果
- 运行命令: <youqu dev run 命令>
- 运行套件: <suite name>
- 运行 spec: <spec list>
- APP_PATH: <实际编译或安装后的应用路径>
- 通过: <N>
- 失败: <N>
- 跳过: <N>
- 超时: <N>
- 通过率: <rate>

### 6. 失败详情
| spec_id | spec 名 | 错误信息 |
|---------|---------|----------|
| <id> | <name> | <error> |

### 7. 结论
- 代码无影响/代码有影响
- 测试通过/测试失败
- 后续建议
- 清理结果: <测试进程/临时文件/编译目录/rebase 状态>
```
