# YouQu 自动化测试构建智能体 — Multica Issue 提示词

## 标题与标签

- 标题：`[自动化测试构建] {应用名} YAML 用例构建`
- labels：`automation`, `youqu`, `case-builder`

---

## 目标

为 **{应用名}** 创建或补全 YouQu YAML 自动化测试，并推送到自动化测试分支。

本 Issue 只做一件事：**只生成 YAML 用例，不生成 Python 用例，不修改框架源码，不执行测试运行**。

## 严格约束

- **严禁生成 Python 用例**
- **禁止生成 `autotest/case/`**
- **禁止生成 `autotest/widget/`**
- **禁止生成任何 `.py` 测试文件**

---

## 环境信息

| 配置项 | 值 |
|--------|-----|
| 项目路径 | `{PROJECT_ROOT}/` |
| 基础分支 | `{SOURCE_BRANCH}` |
| 自动化测试分支 | `{TARGET_BRANCH}` |
| 当前工作分支 | `{BASE_BRANCH}` |
| 自动化测试目录 | `{AUTOTEST_PATH}` |
| 应用名 | `{APP_NAME}` |
| 应用二进制 | `{APP_BINARY}` |
| Issue ID | `{ISSUE_ID}` |

> 执行 Agent 必须加载 `youqu-case-generator` 技能，知晓完整生成流程和约束。

---

## 职责

本 Issue 只做三件事：

1. **检查已有 YAML 用例完整度**
2. **只生成 YAML 用例**
3. **提交并推送到自动化测试分支**

---

## 执行参数

| 参数 | 必须 | 默认值 | 说明 |
|------|------|--------|------|
| PROJECT_ROOT | 是 | — | 项目根路径 |
| SOURCE_BRANCH | 是 | — | 自动化测试分支基于该分支创建 |
| TARGET_BRANCH | 是 | — | 自动化测试分支名称 |
| BASE_BRANCH | 是 | — | 当前工作分支 |
| AUTOTEST_PATH | 是 | `autotest/` | 自动化测试目录 |
| APP_NAME | 是 | — | 应用名 |
| APP_BINARY | 是 | — | 应用二进制路径 |
| ISSUE_ID | 是 | — | multica issue ID |
| MODULE | 否 | — | 指定模块 |
| TAG | 否 | — | 指定标签 |
| BATCH_SIZE | 否 | 10 | 每批用例数 |
| CASE_TIMEOUT | 否 | 90 | 单用例超时（秒） |

---

## 执行流程

### 阶段 1：检查项目现状

1. 检查 `autotest/` 是否存在。
2. 检查 `autotest/yaml/elements.yaml` 是否存在。
3. 检查 `autotest/yaml/` 下是否已有 `test_*.yaml`。
4. 如果已有 YAML 用例，执行完整性检查：
   - 每个 YAML 是否包含完整 metadata。
   - 每个 YAML 是否引用 `elements.yaml` 中存在的元素。
   - 文件名和用例名是否一致。
   - 是否缺少 `module`、`feature`、`tags`、`vars.xlsx_id`、`vars.case_type`。
   - 是否存在无法自动化的用例未标记 skip。
5. 如果没有任何 YAML 用例，直接进入阶段 2。

---

### 阶段 2：生成 YAML 用例

1. 使用 `youqu-case-generator` 技能生成 YAML 用例。
2. 按模块分批处理，每批建议不超过 10 个用例。
3. 每个模块生成或更新：
   - `autotest/yaml/elements.yaml`
   - `autotest/yaml/<module>/test_<name>_<nnn>.yaml`
   - 必要时更新 `autotest/yaml/index.yaml`
4. 对无法自动化的用例，生成 YAML 注释或 skip 标记，并保留原因。
5. 每完成一批，向 multica 报告进度。

---

### 阶段 3：验证生成结果

1. 执行：

```bash
cd <AUTOTEST_PATH> && youqu index --rebuild
```

2. 执行：

```bash
cd <AUTOTEST_PATH> && youqu run --collect-only
```

3. 检查：
   - YAML 文件数量与预期一致。
   - 每个 YAML 都能被索引。
   - 每个 YAML 都能被 `youqu run --collect-only` 收集。
   - 没有语法错误。
   - 没有缺失元素引用。

---

### 阶段 4：提交并推送

1. 确认当前分支：

```bash
git branch --show-current
```

2. 如果 `TARGET_BRANCH` 已存在，直接切换到该分支：

```bash
git checkout <TARGET_BRANCH>
```

3. 如果 `TARGET_BRANCH` 不存在，则基于 `SOURCE_BRANCH` 创建：

```bash
git checkout -b <TARGET_BRANCH> <SOURCE_BRANCH>
```

4. 如果 `SOURCE_BRANCH` 不存在，停止并报告，不要猜测。

5. 提交测试变更：

```bash
git add <AUTOTEST_PATH>
git commit -m "chore: add youqu yaml cases"
```

6. 推送到远端：

```bash
git push -u origin <TARGET_BRANCH>
```

如果分支已存在，则不要重复创建，直接切换并继续。

### 阶段 5：输出完整报告

报告必须包含：

```markdown
## YouQu YAML 用例构建报告

### 1. 任务信息
- 项目: <PROJECT_ROOT>
- 应用: <APP_NAME>
- 基础分支: <SOURCE_BRANCH>
- 自动化分支: <TARGET_BRANCH>
- Issue: <ISSUE_ID>

### 2. 已有 YAML 检查
- 是否已有 YAML: 是/否
- 用例数量: <N>
- 元素文件: <elements.yaml 状态>
- 完整性问题: <列出或缺失说明>

### 3. 新增/补全内容
- 新增模块: <module>
- 新增用例: <case list>
- 更新元素: <elements.yaml 更新摘要>

### 4. 验证结果
- `youqu index --rebuild`: 通过/失败
- `youqu run --collect-only`: 通过/失败

### 5. 提交与推送
- 分支: <TARGET_BRANCH>
- Commit: <commit hash>
- 推送结果: 成功/失败

### 6. 结论
- 构建完成/存在阻塞
- 后续建议
```

---

## 禁止操作清单

- 修改 YouQu 框架源码
- 生成 Python 用例
- 直接执行 `pytest`
- 生成无 metadata 的 YAML
- 生成无 `ref` 的 YAML 步骤
- 跳过已有 YAML 完整性检查
- 硬编码绝对路径
- 静默删除无法自动化的用例
- 在 multica 模式下添加 `-k`、`-m` 等 pytest 过滤参数
