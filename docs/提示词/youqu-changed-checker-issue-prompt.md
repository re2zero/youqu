# YouQu 变更影响检查智能体 — Multica Issue 提示词

## 标题与标签

- 标题：`[变更影响检查] {应用名} {PR 或 Commit 范围}`
- labels：`automation`, `youqu`, `changed-checker`

---

## 目标

对 **{应用名}** 的代码变更进行同步、rebase、影响分析、相关 YAML 用例查找、必要的新增用例、编译/安装验证、测试执行和结果报告。

本 Issue 只做一件事：**基于指定分支和变更范围，验证代码修改对 YouQu YAML 自动化测试的影响**。

---

## 环境信息

| 配置项 | 值 |
|--------|-----|
| 项目路径 | `{PROJECT_ROOT}/` |
| 基础分支 | `{SOURCE_BRANCH}` |
| 当前自动化测试分支 | `{BASE_BRANCH}` |
| 目标同步分支 | `{TARGET_BRANCH}` |
| 自动化测试目录 | `{AUTOTEST_PATH}` |
| 应用名 | `{APP_NAME}` |
| 应用二进制 | `{APP_BINARY}` |
| 实际测试应用路径 | `{APP_PATH}` |
| 编译目录 | `{BUILD_DIR}` |
| 编译命令 | `{BUILD_COMMAND}` |
| 安装命令 | `{INSTALL_COMMAND}` |
| 安装密码（环境变量） | 已设为环境变量 `INSTALL_PASSWORD` |
| 相关 PR | `{PR_URL}` |
| Issue ID | `{ISSUE_ID}` |

> 执行 Agent 必须加载 `youqu-change-test` 技能，知晓完整变更检查流程和约束。

---

## 职责

本 Issue 只做五件事：

1. **拉取并 rebase 到当前自动化测试分支**
2. **分析代码修改信息**
3. **查找或新增相关 YAML 用例**
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
| AUTOTEST_PATH | 是 | `autotest/` | 自动化测试目录 |
| APP_NAME | 是 | — | 应用名 |
| APP_BINARY | 是 | — | 应用二进制路径 |
| APP_PATH | 是 | 来自 YAML `app` 字段 basename；未指定时同 `APP_BINARY` | 实际测试应用路径 |
| BUILD_DIR | 否 | `${PROJECT_ROOT}/build` | 编译目录 |
| BUILD_DEP_COMMAND | 否 | — | 安装构建依赖命令，如 `sudo apt-get build-dep -y dde-file-manager` |
| BUILD_COMMAND | 否 | — | 用户/Issue 指定；LLM 可检查项目技术栈辅助确认，但不得自行发明 |
| INSTALL_COMMAND | 否 | — | 用户/Issue 指定；LLM 可检查项目技术栈辅助确认，但不得自行发明 |
| PR_URL | 否 | — | 相关 PR 地址 |
| ISSUE_ID | 是 | — | multica issue ID |
| MODULE | 否 | — | 指定模块 |
| TAG | 否 | — | 指定标签 |
| BATCH_SIZE | 否 | 20 | 每批用例数 |
| CASE_TIMEOUT | 否 | 90 | 单用例超时（秒） |

---

## 执行流程

### 阶段 1：同步并 rebase

1. 确认当前分支：

```bash
git branch --show-current
```

2. 拉取目标分支最新代码：

```bash
git fetch origin <TARGET_BRANCH>
```

3. 切换到当前自动化测试分支：

```bash
git checkout <BASE_BRANCH>
```

4. rebase 到目标分支：

```bash
git rebase origin/<TARGET_BRANCH>
```

5. 如果 rebase 冲突，停止并报告冲突文件，不要继续。

---

### 阶段 2：分析代码修改

1. 获取变更统计：

```bash
git diff --stat origin/<TARGET_BRANCH>..HEAD
```

2. 获取完整 diff：

```bash
git diff origin/<TARGET_BRANCH>..HEAD
```

3. 获取 commit 列表：

```bash
git log --oneline origin/<TARGET_BRANCH>..HEAD
```

4. 分析输出：
   - 修改了哪些模块。
   - 变更类型：`bug_fix` / `new_feature` / `refactor` / `config` / `unknown`。
   - 影响范围：模块、功能点、相关 PR。
   - 是否可能影响任何模块功能。

5. 如果没有任何无关修改（代码无修改或代码修改不影响任何模块功能），直接报告“代码无影响”，并给出理由。

6. 如果存在影响，记录是否需要编译、是否需要安装，并设置 `APP_PATH` 为后续测试使用的实际应用路径。

---

### 阶段 3：查找相关 YAML 用例

1. 如果 `autotest/yaml/` 不存在，报告“项目还没有自动测试的 YAML”，并说明需要使用 `youqu-cases-builder` 智能体构建项目的 YAML 用例。
2. 如果存在 YAML，执行：

```bash
cd <AUTOTEST_PATH> && youqu index --rebuild
```

3. 使用 `youqu index --list` 或 `YamlIndex` 查询相关模块/功能点。
4. 将变更影响范围与现有 YAML 用例做覆盖对比：
   - 充分覆盖：进入阶段 5 前执行阶段 5A。
   - 部分覆盖：报告缺口，并说明是否需要补充。
   - 无覆盖：进入阶段 4 新增用例，新增后进入阶段 5A。

---

### 阶段 4：新增缺失 YAML 用例

当新增功能或无覆盖功能点需要新用例时：

1. 调用 `youqu-case-generator` 技能，输入：

```yaml
source_type: git_diff
app_name: <APP_NAME>
module: <module>
change_type: <change_type>
change_description: |
  <变更说明>
affected_features:
  - <feature1>
  - <feature2>
diff_summary: |
  <git diff --stat 输出>
```

2. 生成 YAML 用例。
3. 重建索引：

```bash
cd <AUTOTEST_PATH> && youqu index --rebuild
```

4. 验证新增用例可被收集：

```bash
cd <AUTOTEST_PATH> && youqu run --collect-only
```

---

### 阶段 5A：编译和安装验证产物

只有当阶段 2 判断存在功能影响时，才执行本阶段。

1. 如果 `BUILD_COMMAND` 缺失，先检查项目是否已有可执行编译产物：
   - 优先使用 `APP_PATH`。
   - 其次使用 `APP_BINARY`。
   - 如果两者都不是编译产物，必须向用户确认构建命令或停止测试。
   `BUILD_COMMAND` 必须由 Issue 或用户明确提供；LLM 只能检查项目技术栈辅助确认，不得自行发明。

```bash
cd <PROJECT_ROOT> && <BUILD_COMMAND>
```

3. 验证编译产物存在且可执行：

```bash
test -x <APP_PATH>
```

4. 如果应用需要系统安装后才能验证，执行安装：

```bash
cd <PROJECT_ROOT> && <INSTALL_COMMAND>
```

5. 安装密码从环境变量 `$INSTALL_PASSWORD` 读取。例如：

```bash
echo "$INSTALL_PASSWORD" | sudo -S sh -c "<INSTALL_COMMAND>"
```

   如果 `$INSTALL_PASSWORD` 为空，提示错误并中止：
   ```
   错误：INSTALL_PASSWORD 环境变量为空，无法执行需要 sudo 权限的操作。
   请确保在执行环境中设置了 INSTALL_PASSWORD。
   ```
   `INSTALL_COMMAND` 必须由 Issue 或用户明确提供；LLM 只能检查项目技术栈辅助确认，不得自行发明。

6. **禁止操作**：
   - 严禁输出或打印 `$INSTALL_PASSWORD` 的值。
   - 严禁将密码写入文件、日志或提交到仓库。
   - 严禁硬编码密码。

7. 安装完成后，将 `APP_PATH` 更新为安装后的实际可执行路径。
8. 如果编译或安装失败，停止测试并报告失败原因。

---

### 阶段 5：运行相关测试

运行测试前必须确认：

- 如果存在功能影响，`APP_PATH` 已指向编译产物或安装产物。
- 如果应用需要安装后验证，安装已完成。
- 如果 `APP_PATH` 与 `APP_BINARY` 不同，报告中必须说明原因。

   - 指定用例列表（非 multica 模式）：`youqu run -a <AUTOTEST_PATH> -k "<test_ids>"`
   - 按模块：`youqu run -a <AUTOTEST_PATH> --module <module>`
   - 全量：`youqu run -a <AUTOTEST_PATH>`
   - 带 multica 报告：`youqu run -a <AUTOTEST_PATH> --multica-report --issue-id <ISSUE_ID>`

2. 优先使用 multica 报告模式。
3. 如果 multica CLI 不可用，仍执行测试，但报告进度降级。
4. 测试命令中必须使用实际应用路径：

```bash
APP_PATH=<实际编译或安装后的应用路径> youqu run ...
```

---

### 阶段 5B：测试后清理环境

测试完成后必须执行清理，不能留下测试进程、临时文件、安装/编译临时状态或 rebase 临时修改。

1. 清理测试进程：
   - 优先清理测试拉取的进程，避免误杀其他用户进程。
   - 仅在确认进程属于本次测试后，才执行：

```bash
pkill -f "<APP_NAME>"
```

2. 清理测试临时文件：

```bash
rm -rf <TEMP_DIR>
```

3. 清理编译临时目录：

```bash
rm -rf <BUILD_DIR>
```

4. 如果 rebase 产生临时修改，先保存必要测试报告，再恢复干净工作区：

```bash
git status --short
git restore --staged .
git restore .
```

5. 如果安装过程修改了系统环境，必须记录安装路径和清理方式；无法安全清理时，在报告中明确说明。

---

### 阶段 6：输出完整报告

报告必须包含：

```markdown
## YouQu 变更影响检查报告

### 1. 同步信息
- 项目: <PROJECT_ROOT>
- 当前分支: <BASE_BRANCH>
- 基础分支: <SOURCE_BRANCH>
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

### 4. YAML 用例覆盖
- 是否已有 YAML: 是/否
- 相关用例: <case list>
- 覆盖状态: 充分/部分/缺失
- 新增用例: <case list 或无>

### 5. 运行结果
- 运行命令: <youqu run 命令>
- 运行 case: <case list>
- APP_PATH: <实际编译或安装后的应用路径>
- 通过: <N>
- 失败: <N>
- 跳过: <N>
- 超时: <N>
- 通过率: <rate>

### 6. 结论
- 代码无影响/代码有影响
- 测试通过/测试失败
- 后续建议
- 清理结果: <测试进程/临时文件/编译目录/rebase 状态>
```

---

## 禁止操作清单

- 跳过 rebase
- 存在影响时未编译直接运行测试
- 未安装直接测试系统级应用
- 输出安装密码
- 不清理环境
- 直接执行 `pytest`
- 修改框架源码
- 修改非测试分支文件
- 生成无 metadata 的 YAML
- 生成无 `ref` 的 YAML 步骤
- 在未确认影响范围时直接跑全量测试
- 在 multica 模式下添加 `-k`、`-m` 等 pytest 过滤参数
