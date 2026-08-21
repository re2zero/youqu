# Stage 3: 汇总对比

## 用途
收集两条线的报告，对比覆盖率，分析差异原因，生成最终报告。

## 执行

1. 读取 `local://a_report.md` 和 `local://b_report.md`
2. 提取两条线的 commit hash
3. 对比覆盖率数据
4. 分析差异原因
5. 调用 `assets/scripts/generate_report.py` 生成最终报告

## 差异分析要点

| 差异类型 | 原因 | 说明 |
|---------|------|------|
| A 覆盖率 < B | Pipeline A 实例级，发现更多 gap | 正常，A 更严格 |
| B 覆盖率 < A | MCP 索引过期或 grep 漏报 | 检查索引新鲜度 |
| A 有 B 没有的 gap | 实例级 vs 类级差异 | 标注"实例级特有" |
| B 有 A 没有的 gap | 头文件声明未实例化 | 标注"类级推导" |
| 两条线 commit hash 不一致 | 源码已变更，MCP 索引未同步 | 标注"MCP 索引落后于当前源码" |

## 产出

| 文件 | 生成者 | 谁读 | 命名策略 |
|------|--------|------|---------|
| `coverage-report.md` | generate_report.py | 开发者 | 固定名覆盖 |
| `coverage-data.json` | generate_report.py | 脚本/工具 | 固定名覆盖 |
| `stage-1-scan-report.md` | 子 agent（Pipeline A） | 主 agent | 固定名覆盖 |
| `stage-2-graph-report.md` | 子 agent（Pipeline B） | 主 agent | 固定名覆盖 |