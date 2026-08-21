# Stage 2: Pipeline B — 代码图谱推导

## 用途
在子 agent 中通过 codebase MCP 服务推导 AT-SPI 元素覆盖率。

## 前置条件

1. 目标项目必须在 codebase MCP 中已索引
2. 先调 `list_projects` 确认 project 名
3. 再调 `index_status` 确认 head_sha 未过期

## 认证回退策略

MCP 服务提供固定 HTTP 端点（`/projects`、`/index`、`/mcp`、`/health`），不支持 OAuth 动态客户端注册。

| 步骤 | 动作 | 失败处理 |
|------|------|---------|
| 1 | 尝试 OAuth 注册（`/register`） | 404 → 跳过，直接调固定端点 |
| 2 | 调 `list_projects`（`/projects`） | 失败 → 报错退出 |
| 3 | 调 `index_status`（`/index`） | 失败 → 报错退出 |
| 4 | 调 `get_architecture`（`/mcp`） | 失败 → 报错退出 |

**关键规则：** 认证方式失败（404）不降级到 grep。直接调固定端点。端点调用失败才报错退出。

## 执行步骤

### 1. 获取项目结构 + 索引 commit hash
```
index_status(project="<name>")  → 记录 head_sha 作为 MCP 索引 commit hash
get_architecture(project="<name>")
```

### 2. 查可交互控件类
```
query_graph(project="<name>", query="
  MATCH (c:Class)
  WHERE c.file_path STARTS WITH '<gui_dir>'
    AND c.base_classes CONTAINS 'QWidget'
    OR c.base_classes CONTAINS 'DWidget'
  RETURN c.name, c.file_path, c.base_classes
  LIMIT 500
")
```

### 3. 查已有 AT-SPI 名称
```
search_code(project="<name>", pattern="setAccessibleName", path_filter="<gui_dir>", limit=500)
search_code(project="<name>", pattern="setObjectName", path_filter="<gui_dir>", limit=500)
```

### 4. 分类判定

对每个控件类，问三个问题：
1. 是否可交互类型（用 classify.py 的分类表判断）
2. 是否有 setAccessibleName 调用
3. 是否有 setObjectName 调用

### 5. 计算覆盖率

```
覆盖率 = 有名称的类数 / 可交互类总数 * 100
```

## 产出

子 agent 将报告写入 `local://b_report.md`，必须包含 MCP 索引 commit hash，格式：

```markdown
# Pipeline B Report

## 项目
- 名称: {project_name}
- MCP 索引 Commit: {mcp_commit_hash}

## 覆盖率
- 元素 A（可交互控件类）: {total}
- 元素 B（已有名称）: {ok}
- 覆盖率: {coverage}%

## 按模块覆盖率
| 模块 | A | B | 覆盖率 | Gap 数 |
|------|---|---|--------|--------|
| ... | ... | ... | ... | ... |

## Gap 列表
| 类名 | 类型 | 文件 | 推断原因 |
|------|------|------|---------|
| ... | ... | ... | ... |
```