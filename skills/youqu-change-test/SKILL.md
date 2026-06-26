---
name: youqu-change-test
version: "0.1.0"
description: >
  Git diff 智能测试：拉取代码变更，LLM 分析影响范围，查找或生成对应 YAML
  用例，执行测试并报告结果。
  Use whenever: 拉取代码测试, 覆盖测试, 增量测试, 代码变更验证,
  pull代码测试, diff测试, 同步测试, 变更测试, baseline test,
  regression test, pull latest code and test, 拉取最新代码覆盖测试,
  代码提交后验证, 提交后跑测试, 同步最新代码测试.
---

# YouQu Change Test

Git 代码变更 → LLM 智能分析影响范围 → 查找/生成对应 YAML 用例 → 执行测试 → 报告结果。

本 skill 是一个**编排 skill**，不重复实现已有能力，而是组合 git、YamlIndex、
`youqu-case-generator`、`youqu-case-runner` 完成端到端流程。

## 依赖的 Skills

| Skill | 用途 | 调用时机 |
|-------|------|----------|
| `youqu-case-runner` | 执行选定的 YAML 用例 | Step 5 |
| `youqu-case-generator` | 生成新用例（按需） | Step 4 |

---

## 意图路由（Step 0 之前）

用户触发 skill 后，先判断真实意图：

| 用户意图 | 路由 | 判断依据 |
|----------|------|----------|
| 同步代码 + 测试验证 | 本 skill 完整流程 | 用户提到"拉取代码"/"pull"/"同步"/"变更"等 |
| 为功能/需求生成用例 | **直接调用 `youqu-case-generator`** | 用户明确说"生成用例"/"创建case"，无"同步"/"验证"语义 |
| 仅执行现有用例 | **直接调用 `youqu-case-runner`** | 用户明确说"跑测试"/"执行用例"，不涉及代码变更 |

**不要把"生成用例"意图拉入完整流程** — 用户的需求已经很明确，走 git diff 是浪费。

---

## Step 0: 环境探测

Agent 先自动探测，**只对探测失败或不确定的项向用户提问**：

| 信息 | 探测方式 | 提问条件 |
|------|----------|----------|
| git repo 路径 | `git rev-parse --show-toplevel` | 命令失败时 |
| 当前分支 | `git branch --show-current` | 命令失败时 |
| 上游分支 | `git remote show origin` 或默认 `origin/<current>` | 非 git 仓库或无 remote 时 |
| 对比起点 | 用户指定或默认 `HEAD` | — |
| autotest 路径 | 检查 `autotest/` 或 `apps/autotest_*/` 存在性 | 无 autotest 目录时 |
| 应用二进制 | `which <app-name>` 或用户指定 | 未找到时 |
| 构建命令 | 用户指定 | —（无默认值，不探测） |

探测完成后，**一次性确认**探测到的信息：

```
确认以下信息:
- Git repo: /home/dev/deepin-music (分支: master → 对比 origin/master)
- autotest 路径: apps/autotest_music/
- 应用二进制: /usr/bin/deepin-music
- 构建命令: 无 (使用系统已安装版本)
```

用户确认后进入 Step 1。有多次运行记录时，尝试从上次结果恢复配置。

---

## Step 1: Git 变更采集

**纯确定性操作，无 LLM 参与。**

```bash
# 1. 拉取远程最新（不自动 merge）
git fetch origin <branch>

# 2. 变更文件列表（统计概览）
git diff --stat <since>..origin/<branch>

# 3. 变更内容（给 LLM 阅读）
git diff <since>..origin/<branch>

# 4. Commit 列表（辅助理解变更意图）
git log --oneline <since>..origin/<branch>
```

**输出保存**: 将 `git diff` 和 `git log` 输出保存到临时文件，供 Step 2 使用。

如果 `git diff` 无输出（无变更），直接报告"无变更"并结束。

**用户指定了分支且要同步**时：
```bash
git reset --hard origin/<branch>
```

---

## Step 2: LLM 分析变更（核心步骤）

**这是本 skill 的核心价值。Agent 自身就是 LLM，直接阅读 diff 输出做分析。**

### 分析输入

- Step 1 采集的 `git diff` 完整内容
- `git log --oneline` commit 列表
- autotest 目录下的 module/feature 列表（从 `youqu index --list` 或 `elements.yaml` 获取）

### 分析要求

Agent 阅读上述输入后，输出结构化分析结果：

```yaml
# Agent 内部推理输出（不写入文件，传给 Step 3）
analysis:
  modules:                          # 变更影响的模块
    - name: "播放"
      confidence: high              # high/medium/low
      evidence: "修改了 src/player/playlist.cpp"
  change_type: bug_fix               # 主要变更类型（见下表）
  mixed_changes: false               # 是否包含多种变更类型
  other_changes: []                  # mixed=true 时的其他变更类型
  affected_features:                 # 受影响的功能点
    - "拖拽排序"
    - "播放控制"
  needs_new_cases: false             # 是否需要生成新用例
  recommended_scope:                 # 推荐执行范围
    module: "播放"
    features: ["拖拽排序", "播放控制"]
  reasoning: |
    修改了 playlist.cpp 的拖拽排序逻辑 (bug fix)，
    影响范围限于播放列表的排序功能。
    现有用例应已覆盖此场景，建议执行相关用例验证修复。
```

### `change_type` 判断

| 变更类型 | 何时选择 | 是否需要新用例 |
|----------|----------|---------------|
| `bug_fix` | 修复已有功能的 bug | 通常 false |
| `new_feature` | 新增功能 | true |
| `refactor` | 重构（不改变行为） | 通常 false |
| `config` | 配置变更 | 通常 false |
| `mixed` | 同一 diff 包含多种类型 | **逐个判断** |
| `unknown` | 无法确定 | **询问用户** |

### 混合变更处理

当 `mixed_changes: true` 时，`change_type` 填主要类型，`other_changes` 填次要类型。
对 `other_changes` 中的 `new_feature` 项，即使主要类型是 `bug_fix`，也设置
`needs_new_cases: true`。

### 交互要求

分析完成后，**必须向用户展示分析结果并请求确认**：

```
## 变更分析

**变更类型**: bug_fix
**影响模块**: 播放 (high), 播放列表 (high)
**影响功能点**: 拖拽排序, 播放控制
**是否需要新用例**: 否

**推理**: 修改了 playlist.cpp 的拖拽排序逻辑，影响范围限于播放列表的排序功能。

确认分析结果？如有修正请说明。
```

用户确认后进入 Step 3。

---

## Step 3: 用例查找

### 3.1 查找现有用例

```bash
# 通过 YamlIndex 查找
youqu index --list --module <module>

# 或通过 MCP 工具
yaml_list_tests(app="deepin-music", module="播放")
```

### 3.2 覆盖判断

将 Step 2 的 `affected_features` 与查到的用例做简单匹配：

- **所有功能点都有匹配用例** 且 `needs_new_cases=false` → 直接进入 Step 5 执行
- **部分或无匹配**，或 `needs_new_cases=true` → 进入 Step 4 生成新用例
- **匹配但不充分**（某功能点仅 1 个用例） → 报告给用户，询问是否补充

```
## 用例覆盖分析

| 功能点 | 现有用例 | 覆盖状态 |
|--------|----------|----------|
| 拖拽排序 | test_play_005, test_play_012, test_play_018 | ✅ |
| 播放控制 | test_play_030 | ⚠️ 仅 1 个用例，是否补充？
```

---

## Step 4: 用例生成（按需）

**仅在 Step 3 判断为需要生成或用户确认补充时触发。**

调用 `youqu-case-generator` skill，输入不是 xlsx/csv，而是 Step 2 的分析结果：

```
调用 youqu-case-generator skill，上下文:

source_type: git_diff
app_name: <app-name>
module: <module>
change_type: <change_type>
change_description: |
  <Step 2 reasoning 的精简版>
affected_features:
  - <feature1>
  - <feature2>
diff_summary: |
  <git diff --stat 输出>
```

生成完成后，**展示新增用例列表并请求用户确认**：

```
## 新增用例

| 用例 ID | 标题 | 模块 |
|---------|------|------|
| test_lyrics_highlight_001 | 歌词逐字高亮-默认显示 | 播放 |
| test_lyrics_highlight_002 | 歌词逐字高亮-Karaoke模式 | 播放 |

确认新增用例？如有调整请说明。
```

用户确认后，重建索引：
```bash
youqu index --rebuild
```

---

## Step 5: 构建验证（按需）

**仅在用户提供了构建命令时执行。**

```bash
# 执行用户提供的构建命令
cd <build_dir> && <build_cmd>

# 验证二进制存在
ls -la <app_binary_path>
```

构建失败时 → 向用户报告，询问下一步（跳过构建直接用现有二进制 / 重试 / 停止）。

未配置构建命令时 → 直接验证应用二进制路径存在即可。

---

## Step 6: 执行测试

调用 `youqu-case-runner` skill 执行 Step 3/4 选定的用例。

### 6.1 传递给 runner 的参数

将 Step 3 的覆盖分析结果转换为 runner 所需参数：

```
调用 youqu-case-runner skill，上下文:

autotest_path: <autotest_path>
test_filter: "test_play_005 or test_play_012 or test_play_018"
mode: incremental
```

| 场景 | test_filter |
|------|-------------|
| 指定用例列表 | `"test_play_005 or test_play_012 or ..."` |
| 按模块 | `--module <module>` |
| 全量（增量失败或用户选择） | 空（全量） |

### 6.2 优先使用 MCP 异步执行

MCP 连接时，使用 `yaml_run_batch` + `yaml_get_status` 轮询（参见 `youqu-case-runner` skill）。

### 6.3 Bash fallback

```bash
youqu run -a <autotest_path> -k "<test_ids>"
```

---

## Step 7: 结果报告

### 7.1 基本报告

```
## 测试结果

| 指标 | 值 |
|------|-----|
| 总数 | 15 |
| 通过 | 13 |
| 失败 | 1 |
| 超时 | 1 |
| 跳过 | 0 |
| 通过率 | 86.7% |
| 耗时 | 3m 25s |

### 失败用例
- test_play_005: AssertionError — 拖拽排序后 index 越界

### 超时用例
- test_play_012: timeout (90s exceeded)
```

### 7.2 基线对比（可选）

如果 `autotest/report/baseline/` 下存在历史 baseline JSON，可做对比报告。
格式和逻辑参见 `@references/baseline-format.md`。

本次结果也可持久化为新的 baseline JSON，供后续对比使用：

```bash
mkdir -p autotest/report/baseline
# 保存为 autotest/report/baseline/<timestamp>.json
```

### 7.3 报告查看

询问用户是否查看 Allure 报告：

```bash
youqu report --clean --serve
```

---

## 用户交互节点汇总

| Step | 交互内容 | 条件 |
|------|----------|------|
| 0 | 确认探测到的环境信息 | 首次运行 |
| 2 | 展示变更分析结果，请求确认 | **总是** |
| 3 | 报告覆盖不充分，询问是否补充 | 仅在匹配不充分时 |
| 4 | 展示新增用例列表，确认 | 生成完成后 |
| 5 | 构建失败时，询问下一步 | 构建失败时 |
| 7 | 展示最终报告 | **总是** |

---

## 完整流程示例

### 场景 1A: 用户说「拉取最新代码，覆盖测试」

```
用户: "拉取最新代码，覆盖测试"

Agent (Step 0): 自动探测 repo=/home/dev/deepin-music, branch=master
                → 确认信息给用户
用户: "确认"
Agent (Step 1): git fetch origin master
                git diff HEAD..origin/master → 修改了 3 个文件
                git log --oneline HEAD..origin/master → 5 commits
Agent (Step 2): 阅读 diff → 分析结果: bug_fix, 播放模块, 拖拽排序
                → 展示给用户确认
用户: "确认"
Agent (Step 3): youqu index --list --module 播放 → 15 个用例
                "拖拽排序" 有 3 个用例 → 充分覆盖
Agent (Step 5): 验证 /usr/bin/deepin-music 存在
Agent (Step 6): 调用 youqu-case-runner 执行 15 个用例
Agent (Step 7): 报告: 14 passed, 1 failed
                → 询问是否查看 Allure
```

### 场景 1B: 用户说「为播放模块新增歌词逐字高亮功能生成用例」

```
用户: "为播放模块新增歌词逐字高亮功能生成用例"

Agent (意图路由): 用户明确说"生成用例"，无"同步/验证"语义
                → 直接调用 youqu-case-generator skill
                → 不走 Step 1-7 完整流程
```

### 场景 2: 外部调度器触发增量测试

```
外部调度器 (cron / CI) → 触发 Agent session
  → Agent 加载 youqu-change-test skill
  → Step 0: 自动探测（无用户交互）
  → Step 1: git sync + diff
  → Step 2: LLM 分析
  → Step 3: 查找/生成用例
  → Step 6: 执行
  → Step 7: 报告 + baseline 对比 + 保存
```

---

## Pitfalls

1. **git diff 输出可能很大**: 大范围重构时 diff 可能有数万行。先用 `git diff --stat` 确认规模，超过 500 行变更文件时提醒用户。

2. **LLM 分析可能误判**: 始终让用户确认 Step 2 的分析结果。特别是 `change_type` 和 `needs_new_cases`，误判会导致执行错误范围或漏生成用例。

3. **无 autotest 目录**: 如果目标项目没有 YouQu autotest 工程，本 skill 无法执行用例。应提示用户先用 `youqu make` 创建骨架，或改用 `youqu-case-generator` 从零生成。

4. **构建命令因项目而异**: Step 0 不猜测构建命令，必须由用户提供。如果用户提供的是 CMake 项目，不要假设 Makefile。

5. **MCP 工具优先于 bash**: Step 3 查找用例、Step 6 执行用例，优先使用 MCP 异步工具（`yaml_list_tests`、`yaml_run_batch`），bash 作为 fallback。

6. **不要重复 git 操作**: Step 1 采集完 diff 后不要再 git pull/reset，除非用户明确要求同步。

7. **意图路由要果断**: 用户明确要求"生成用例"时直接调 generator，不要绕路走 git diff → 分析 → 判断 needs_new_cases。多此一举浪费用户时间。

---

## Reference Files

| File | Purpose |
|------|---------|
| `@references/baseline-format.md` | Baseline JSON 持久化格式与对比逻辑（可选功能） |
