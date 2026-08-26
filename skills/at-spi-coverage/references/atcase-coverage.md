# coverage_atcase.py — AT 用例覆盖率

统计应用项目的 AT 用例对 UI 元素的覆盖情况。使用 `scripts/coverage_atcase.py`, 只依赖 `pyyaml`, 不需要 libclang / 源码扫描。

这是对 `coverage_stats.py` 的**接力**:

- **scan_total (分母)** — 由 `coverage_stats.py` 扫描出的交互控件总数 (源码扫描结果), 本脚本不计算, 只从扫描产物读取
- **covered_refs (分子)** — 本脚本计算: suite 引用全集 = `selector.name` ∪ `items:` 菜单项 (两者均去重去噪)。瞬态菜单项 (主菜单/右键菜单) 也算覆盖。
- **覆盖率** — `min(covered_refs, scan_total) / scan_total × 100%`, 封顶 100%

若项目不存在 AT 用例 (`tests/at/yaml/` 下无 `*.suite.yaml`), 覆盖率记为 0。

## total 来源 (coverage_stats.py 扫描产物)

`coverage_stats.py` 扫描完成后, 产物写在 `<output 目录>/coverage_scan/` 下。`coverage_atcase.py` 按以下顺序取 total:

1. `--total <N>` 直接传入
2. `--scan-dir <dir>` 指定的扫描产物目录 (读取 `pre_report.json` 或 `pre_scan_gaps.yaml` 的 `summary.total_widgets`)
3. 自动发现 `<src>/coverage_scan/` 或 `./coverage_scan/`

## covered_refs 计算

递归遍历所有 `*.suite.yaml` (含 `steps` / `assert_steps` / `setup` / `teardown` / 嵌套 `suites`), 收集:
- `selector.name` — 持久元素定位
- `items:` 菜单项 — 主菜单 (`dtk_main_menu`) / 右键菜单 (`dtk_context_menu`) 的瞬态菜单项

两者去重并剔除文件名噪音 (含 `.`) 后取并集 = `covered_refs`。items 引用即视为覆盖对应功能, 即使该菜单项不在 `elements.yaml` 清单里。

`elements.yaml` 仅用于辅助报告 (清单内覆盖 / 清单缺口), 不决定分子分母。若无 `elements.yaml`, 分子即 suite 引用全集。

## 噪音过滤

包含 `'.'` 的 name 视为文件名噪音 (如 `normal.pdf`) 剔除 —— 文件名才包含 `'.'` 分隔符, SPI 元素名称不包含 `'.'`。

## Interpreting results

覆盖率 `min(covered_refs, scan_total) / scan_total` 混合了两个不同口径的集合:
- **分子 covered_refs** — suite 引用全集 (selector + 瞬态 items 菜单项)
- **分母 scan_total** — 源码扫描的交互控件数 (不含菜单项)

因为 items 菜单项 (主菜单/右键菜单) 不在扫描统计内, 分子常 ≥ 分母, 覆盖率**封顶 100%**。100% 的含义是"用例引用的去重元素数已覆盖扫描交互控件数", 不代表清单完整或所有 UI 元素都被测到。

有区分度的指标在辅助报告:
- **covered_in_inventory** — covered_refs 中落在 `elements.yaml` 清单内的数量 (本例 18/46)
- **refs_not_in_inventory** — covered_refs 的清单外元素 (瞬态菜单项, 本例 25 个)
- **scan_named_not_in_inventory** — 扫描已命名但清单缺失 (清单缺口, 本例 12 个)
- **inventory_uncovered** — 清单中未被任何 covered_refs 覆盖 (用例缺口, 本例 28 个)

解读覆盖率前先看 `elements_source` 与辅助指标, 区分"清单问题"与"用例缺口"。源码是 AT-SPI 树实际名称的权威, 清单与源码冲突时以源码为准。

动态拼接名 (`setAccessibleName("Button_" + objName)`) 静态扫描无法解析, 运行时才生效 —— 这类控件报 gap 不代表真的缺名, 需用 AT-SPI 实况 dump 验证。


## 用法

```bash
# 1. 先运行 coverage_stats.py 得到 total (扫描产物写入 coverage_scan/)
python3 scripts/coverage_stats.py --src /path/to/repo --cpp-only -o coverage_report.json

# 2. 接力计算 AT 用例覆盖率 (自动发现 <repo>/coverage_scan/ 或 ./coverage_scan/)
python3 scripts/coverage_atcase.py --src /path/to/repo

# 显式指定扫描产物目录 / 直接传 total
python3 scripts/coverage_atcase.py --src /path/to/repo --scan-dir /path/to/coverage_scan
python3 scripts/coverage_atcase.py --src /path/to/repo --total <N>

# 打印已覆盖元素明细
python3 scripts/coverage_atcase.py --src /path/to/repo --scan-dir /path/to/coverage_scan --list-elements

# 自定义输出 / 阈值
python3 scripts/coverage_atcase.py --src /path/to/repo -o coverage_atcase.json --threshold 80
```

## 输出

控制台示例 (路径/数字用 `<占位>` 表示, 实际为项目相关值):

```
============================================================
AT 用例覆盖率统计
============================================================
  项目       : <project>
  AT 用例目录: <repo>/tests/at/yaml
  total 来源 : <scan-dir>/pre_report.json
  suite 文件 : <suite-count>
  elements 来源: elements.yaml   # 或 *.suite.yaml (无 elements.yaml 时)
  扫描交互控件 (total) : <N>
  用例覆盖引用 (covered): <M> (selector ∪ items 去重, 含瞬态 items)
  其中清单内           : <P> 个
  覆盖率               : <X>%
  [INFO] 已剔除文件名噪音: <noise...>
  [INFO] 用例引用的清单外元素 (<n> 个, 瞬态菜单项等): ...
       阈值: <threshold>%  -> PASS|FAIL
```

生成文件:
- `coverage_atcase.json` — 结构化结果 (`total` / `covered_refs` / `covered_in_inventory` / `refs_not_in_inventory` / `scan_named_not_in_inventory` / `inventory_uncovered` / `coverage` / `no_cases` / `passed` 等)
- `coverage_atcase.md` — Markdown 报告

退出码: `0` 表示覆盖率达到阈值且有 AT 用例, `1` 否则 (CI 友好)。无 AT 用例时始终返回 `1` 并报 0。未找到扫描产物时打印运行 `coverage_stats.py` 的提示并返回 `1`。
