---
name: at-spi-ui-map
description: "Use when deriving AT-SPI UI structure or expected element names for desktop apps (Qt/DTK/GTK) from source via a remote-codebase MCP server, to produce a UI map, expected element list, and source-code implementation checklist for AT test baselines. Triggers: UI图谱, AT-SPI, 预期AT元素, 控件缺口, setAccessibleName 缺口, ui map, AT测试基线."
---

# AT-SPI UI Map (via Codebase MCP)

## Overview

纯静态推导：仅用 remote-codebase MCP 服务的图结构（节点/边）与文本检索，从源码推导桌面应用的 UI 图谱与 AT-SPI 元素契约，产出 AT 用例定位基线文档与源码补全实施清单。**不运行被测程序、不做运行时探测**。

## When to Use

- 需为 Qt/DTK/GTK 桌面应用建立 AT 自动化测试的"预期元素清单"，但环境无法运行 GUI。
- 需回答"哪些控件缺 AT-SPI 名称、缺在哪、怎么补"。
- 需把 UI 结构（组件树/菜单/对话框/快捷键/触发条件）变为可回溯文档。

**When NOT to use:** 需要运行时行为（坐标、可见性、实例数、`_N` 去重编号）——那是运行时探测技能的范畴。

## 前置条件（硬性：工具不可用即报错退出）

1. **MCP 可用性检查必须先做，失败即停**：
   - `list_projects` 找不到目标仓库索引 → **直接报错退出**，不得猜测 project 名、不得改用本地工具替代、不得编造结果。
   - `index_status` 调用失败或 head_sha 过期 → **直接报错退出**并提示重建索引。
   - 任一工具 schema 变更导致调用失败 → **直接报错退出**，先 `read xd://mcp__…` 核实 schema，不猜参数。
2. 记录工具契约（下节）与图结构：节点 Class/Method/Function/Field/Enum；边 INHERITS/CALLS/USAGE/IMPORTS/DEFINES_METHOD。

## Quick Reference

| 工具 | 用途 | 关键参数 |
|---|---|---|
| `get_graph_schema` | 节点/边类型 | — |
| `index_status` | 索引新鲜度 | — |
| `list_projects` | 找 project 名 | — |
| `get_architecture` | 组件/目录总览 | — |
| `query_graph` | 结构查询 | `query`（Cypher） |
| `search_code` | 文本/正则检索 | `pattern`, `path_filter`, `mode`, `limit`, `regex` |
| `explore` | 符号探测（blast radius+邻居+源码） | `query`, `max_files`, `depth`, `expand` |
| `get_code_snippet` | 指定符号源码 | `qualified_name` |

调用方式：写 JSON 到 `xd://mcp__remote_codebase_<tool>`，`project` 必填。**动态设备摘要不可信**，首次用某工具先 `read xd://…` 看 schema。

## Workflow

1. **组件边界**：`get_architecture` / `list_projects` 确认组件（主程序/插件/弹窗等）与各自 `gui/` 目录、入口；记录目录名前缀。
2. **控件类清单**：`query_graph` 查 `gui/` 下 Class + `base_classes`，过滤真实控件（QWidget/DWidget/DMainWindow/DDialog/DListView 等）。**100k 行硬上限、无分页** → 按 `file_path STARTS WITH` 收窄、按子目录分查。
3. **AT 基础设施**：`explore` 搜 `accessible` / `accessibledefine`，找 `SET_*_ACCESSIBLE` 注册表、`accessibleFactory`、`installFactory`（常在 main.cpp）、`getAccessibleName` 命名算法（如 `RolePrefix_<名称>`、同名 `_N`）。**这些文件是 AT 名的静态契约**，推导规则以实际实现为准。
4. **显式 AT 名称**：`search_code` 分别查 `setAccessibleName` 与 `setObjectName`（objectName 是 fallback 关键输入）。**必须与源码对账**——grep 层有漏报。
5. **交互结构**：菜单 `contextMenuEvent|Qt::CustomContextMenu|DMenu|addAction`；对话框 `new (D|Q)\w*Dialog|\.exec\(\)`；快捷键 `QShortcut|setShortcut`；逐菜单读 `aboutToShow` lambda 拿使能/显隐条件。
6. **缺口判定**（对每个控件类问三个问题）：①有类级 AT 注册吗？②有显式 setAccessibleName/objectName 吗？③无 → fallback 是文本（翻译易碎）还是类型名？输出分三类：**必做**（无任何锚点，AT 名=泛称）、**建议**（fallback 易碎）、**无需修改**（已有注册/显式名）。**可做可不做 = 必做**，不设可选档。
7. **产出三件套**（write 落盘 `tests/at/`，文件名固定如下，勿改名）：
   - `ui-map.md`：组件树 mermaid + 控件表 + 菜单/对话框/快捷键 + 文件:行号索引。
   - `expected-at-spi-elements.md`：预期名表（名称/Role/触发/使能条件/推导链）。
   - `at-spi-implementation-checklist.md`：**唯一缺口明细 + 可执行实施清单**（见下节）。缺口明细只存在于 checklist 一处，其它文档不重复列出，只引用其条目号。

## 实施清单硬性要求

- 每个缺口条目：**目标名称**（命名前缀约定如 `<App>.<Widget>`）→ **插入位置**（文件+方法+行号区间）→ **修改模板**（可粘贴代码）→ **验证断言**（AT 用例如何用新名定位）。全部用 `setAccessibleName`（直接作用于 AT-SPI Name），英文稳定不含翻译文本。
- 命名规则、显式名对账（全部 setAccessibleName/objectName 调用点+文件:行号）、覆盖统计、动态风险，一并并入 checklist 头部或"无需修改"表（**不单独建 gap 文件**）。
- 无 installFactory 的组件（插件/弹窗）：`setAccessibleName` 仍生效，但 `setObjectName` 不影响 AT 名 → 只能直补 accessibleName。
- **验证 = 本地编译通过**（远程 MCP 索引不可重建）：构建命令退出码 0 + 全部产物生成 + 无新增 warning；每插入点先做编译前提检查（QWidget 派生、模板在 `new` 后、不动声明）；失败回滚该条目重编。实施后顺序：①编译 ②冒烟 ③运行期 dump 对账 ④静态计数勾对。
- 完成后预期 AT-SPI 树 + 断言模板一并落盘，保证 AT 每步执行与断言精准对位。

## Common Mistakes

| 坑 | 规避 |
|---|---|
| search_code 漏报（grep 层不可靠） | 提高 limit、换 pattern、按组件分查、与 query_graph 类清单交叉验证、关键点回源码 |
| query_graph 查 Qt 外部符号 USAGE 边返回空 | 这类调用用 search_code，别用图查 |
| query_graph 静默截断（无分页 100k 上限） | 按路径收窄，注意 `total` 提示 |
| explore query 是空格分词 bag（前 16 词） | 符号多拆多次；`expand:false` 省 token |
| search_code `regex` 默认 false（`\|` 模式 0 命中） | 多模式加 regex:true 或分开查 |
| 动态 AT 名（`_N` 去重、坐标、可见性）当静态事实 | 标注"[INFERENCE] 需运行时验证" |
| 同名控件（同 objectName/fallback 多实例） | 预期清单给"名+角色"组合或正则 |
| 索引过期（head_sha 不一致） | 以 index_status 为准，提示重建 |
| MCP 工具不可用/找不到项目 | **直接报错退出**，不猜不降级不编造 |
| 分析期做运行时探测 | 只读纪律：分析只用 MCP；写文件用 write/edit |
| 缺口明细散落多文件（gaps/checklist 双份） | 缺口明细只存在于 checklist，其它文档只引用条目号 |

## 验收标准

- 三件套落盘，每条断言带文件:行号；预期名推导链可回溯（`名称 = 规则(注册表|显式名|fallback)`）。
- 缺口区分"静态可确认"与"[INFERENCE] 需运行时验证"；实施清单可直接执行且验证=本地编译通过。
- 无虚构：拿不到的动态值明确标注，不编造 AT-SPI 树；工具不可用时报错退出。
