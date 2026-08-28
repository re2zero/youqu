# coverage_atcase.py — AT 用例覆盖率

统计应用项目的 AT 用例对 UI 元素的覆盖情况。使用 `scripts/coverage_atcase.py`, 只依赖 `pyyaml`, 不需要 libclang / 源码扫描。

这是对 `coverage_stats.py` 的**接力**:

- **scan_total (分母)** — 由 `coverage_stats.py` 扫描出的交互控件总数 (源码扫描结果), 本脚本不计算, 只从扫描产物读取
- **covered_refs (分子)** — 本脚本计算: suite 持久元素引用全集 = `selector.name` (去重去噪)。**瞬态菜单项 (`dtk_main_menu` / `dtk_context_menu` 的 `items`) 不计入覆盖**, 仅在报告 `transient_items` 中列出供查看。
- **覆盖率** — `min(covered_refs, scan_total) / scan_total × 100%`, 封顶 100%

若项目不存在 AT 用例 (`<src>/tests/at/` 下无含 `*.suite.yaml` 的子目录), 覆盖率记为 0。

## 用例数统计口径

用例数以 suite 内 `- id` 条目计: 一个 `*.suite.yaml` 含一个 `suites:` 列表,
每个 `- id` 是一个独立 case。报告输出两个数:

- **case_count** — 用例数: 所有 `*.suite.yaml` 的 `suites:` 列表下 `- id` 条目总数
- **suite_files** — suite 文件数: `*.suite.yaml` 文件数 (仅辅助展示, 不是用例数)

`no_cases` (无用例) 判定基于 `case_count == 0`。

## AT 用例目录定位

`tests/at/yaml` 只是常见命名, 不是硬编码。脚本按以下顺序定位:

1. `--at-dir <dir>` 显式指定
2. 自动发现 `<src>/tests/at/` 下第一个含 `*.suite.yaml` 的子目录 (支持 `yaml`, `yaml_xxx` 等任意命名, 递归 `rglob`)
3. 均不存在 → 无 AT 用例, 覆盖率记为 0

## total 来源 (coverage_stats.py 扫描产物)

`coverage_stats.py` 扫描完成后, 产物写在 `<output 目录>/coverage_scan/` 下。`coverage_atcase.py` 按以下顺序取 total:

1. `--total <N>` 直接传入
2. `--scan-dir <dir>` 指定的扫描产物目录 (读取 `pre_report.json` 或 `pre_scan_gaps.yaml` 的 `summary.total_widgets`)
3. 自动发现 `<src>/coverage_scan/` 或 `./coverage_scan/`

**纯 QML 项目回退:** C++ 扫描产物 (pre_report.json / pre_scan_gaps.yaml) 的
`total_widgets` 为 0 或不存在时, 自动回退到 QML 产物
(`qml_report.json` / `qml_gaps.yaml` 的 `summary.total_elements`)。`--qml-only`
扫描只生成 QML 产物 (无 pre_report.json), 同样被自动发现与读取。

**混合项目求和:** C++ 与 QML 都有控件时, total = C++ total_widgets + QML
total_elements (分别读取后求和)。

## covered_refs 计算

递归遍历所有 `*.suite.yaml` (含 `steps` / `assert_steps` / `setup` / `teardown` / 嵌套 `suites`), 收集:
- `selector.name` — 持久元素定位 (计入覆盖)
- `items:` 菜单项 — 仅在 `action` 为 `dtk_main_menu` / `dtk_context_menu` 时收集, 属**瞬态菜单项**, 不计入覆盖, 归入 `transient_items`

持久 `selector.name` 去重并剔除文件名噪音 (含 `.`) 后即 `covered_refs` (分子)。瞬态菜单项只在报告中单独列出, 反映"当前有哪些菜单动作被用例覆盖"。

`elements.yaml` 仅用于辅助报告 (清单内覆盖 / 清单缺口), 不决定分子分母。若无 `elements.yaml`, 分子直接取 suite 持久引用全集, **不报覆盖为 0**。

## 噪音过滤

包含 `'.'` 的 name 视为文件名噪音 (如 `normal.pdf`) 剔除 —— 文件名才包含 `'.'` 分隔符, SPI 元素名称不包含 `'.'`。

## Interpreting results

覆盖率 `min(covered_refs, scan_total) / scan_total` 混合了两个不同口径的集合:
- **分子 covered_refs** — suite 持久 selector 引用全集 (瞬态菜单项已剔除)
- **分母 scan_total** — 源码扫描的交互控件数 (不含菜单项)

因为瞬态菜单项已从分子剔除, 分子与扫描口径更一致; 覆盖率达到或超过扫描交互控件数时仍**封顶 100%**。100% 的含义是"用例引用的持久去重元素数已覆盖扫描交互控件数", 不代表清单完整或所有 UI 元素都被测到。

有区分度的指标在辅助报告:
- **covered_in_inventory** — covered_refs 中落在 `elements.yaml` 清单内的数量
- **transient_items** — 瞬态菜单项清单 (主菜单/右键菜单, 不参与覆盖)
- **refs_not_in_inventory** — covered_refs 的清单外元素
- **scan_named_not_in_inventory** — 扫描已命名但清单缺失 (清单缺口)
- **inventory_uncovered** — 清单中未被任何 covered_refs 覆盖 (用例缺口)

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

# 显式指定 AT 用例目录 (跳过自动发现; 支持 tests/at/yaml_xxx 等)
python3 scripts/coverage_atcase.py --src /path/to/repo --at-dir /path/to/tests/at/yaml_xxx

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
  AT 用例目录: <repo>/tests/at/yaml_xxx   # 自动发现任意含 *.suite.yaml 的子目录
  total 来源 : <scan-dir>/pre_report.json
  suite 文件 : <suite-files>
  用例 (case) : <case-count> 个 (suite 文件 <suite-files> 个)
  elements 来源: elements.yaml   # 或 *.suite.yaml (无 elements.yaml 时)
  扫描交互控件 (total) : <N>
  用例覆盖引用 (covered): <M> (selector 去重, 不含瞬态 items)
  其中清单内           : <P> 个
  覆盖率               : <X>%
  [INFO] 瞬态菜单项 (不计覆盖, <K> 个): ...
  [INFO] 已剔除文件名噪音: <noise...>
  [INFO] 用例引用的清单外元素 (<n> 个): ...
       阈值: <threshold>%  -> PASS|FAIL
```

生成文件:
- `coverage_atcase.json` — 结构化结果 (`total` / `case_count` / `suite_files` / `covered_refs` / `covered_in_inventory` / `transient_items` / `refs_not_in_inventory` / `scan_named_not_in_inventory` / `inventory_uncovered` / `coverage` / `no_cases` / `passed` 等)
- `coverage_atcase.md` — Markdown 报告

退出码: `0` 表示覆盖率达到阈值且有 AT 用例, `1` 否则 (CI 友好)。无 AT 用例时始终返回 `1` 并报 0。未找到扫描产物时打印运行 `coverage_stats.py` 的提示并返回 `1`。
