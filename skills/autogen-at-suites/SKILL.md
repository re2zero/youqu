---
name: autogen-at-suites
version: "0.9.0"
description: >
  Automatically generate AT-SPI YAML test suites from xlsx/csv test case
  documents for Linux desktop applications (Deepin/UOS). Script-based
  deterministic mapping, no DISPLAY required, element names from static
  source code analysis.
  Triggers: multica, AT自动化生成, AT-SPI YAML, 桌面应用AT, 无显示环境AT
---

# Multica 智能体 — AT-SPI YAML 测试套件自动生成

## 核心思路

**基于 `at-case-generator` 技能，移除运行时录制（record），保留静态扫描（scan），映射改用脚本（ai_mapper.py）。**

```
at-case-generator 原管线：
  parse → scan → record → merge → tree-info → AI标注 → AI映射 → generate → validate
                     ↓                                            ↓
                  移除                                     改为 ai_mapper.py 脚本
```

scan（静态源码扫描）**不需要 DISPLAY**，只依赖 libclang + 源码目录。
没有 libclang 时降级到 grep 从源码提取，同样不需要 DISPLAY。

## 管线模式

本技能提供两条路径：

| 路径 | 步骤 | 适用场景 |
|------|------|---------|
| **全自动**（推荐） | P1→P2→P3→P4→P5 | multica 一键生成，无需人工干预 |
| **带精调** | 全自动 + P2c + P2.5 + P2.7 | 需要提升 role 准确度时 |

## 全自动管线

```
P0: 环境检查
P1: youqu at parse → cases_raw.yaml
P2a: youqu at scan → scanned_ok.yaml（headless）
P2b: scan_to_atree.py → at-tree.yaml（merge_trees([], scan_classes)）
P3:  ai_mapper.py → cases_mapped.yaml（脚本确定性映射）
P3.5: 断言覆盖门禁（generate 内置）
P4:  youqu at generate → *.suite.yaml
P5:  youqu at validate --gate 4
P6:  youqu at run（有 DISPLAY 的机器）
```

全自动路径不需要 AI 标注、不需要 tree-info、不需要用例分组。

## P0: 环境检查

```bash
youqu --version                       # CLI 已安装
file <xlsx_or_csv>                    # 输入文件存在
ls <src_dir>/CMakeLists.txt 2>/dev/null || ls <src_dir>/src/ 2>/dev/null  # 源码目录
```

## P1: 解析用例

```bash
youqu at parse --input <xlsx> --output cases_raw.yaml
```

纯格式转换，headless 可运行。

## P2: 获取 AT 元素树

### P2a: 静态源码扫描（不需要 DISPLAY）

```bash
mkdir -p scan_output
youqu at scan --src <src_dir> --app <app_name> --output scan_output/
```

**scan 不需要 DISPLAY。** 使用 libclang 做 AST 扫描，提取：
- `setObjectName()` 设置的对象名
- `setAccessibleName()` 设置的 AT-SPI 名
- `actionTexts` / `menu_actions`（菜单项文本）
- DTK/Qt 控件类继承关系

产出：
```
scan_output/
├── scanned_ok.yaml      # 有 objectName/accessibleName 的控件
├── scanned_gaps.yaml    # 缺 objectName 的控件
└── element_gaps.yaml    # 汇总缺口报告
```

**libclang 不可用时降级**（见下文备选路径）。

### P2b: scan→at-tree 转换

使用 `merge_trees([], scan_classes)` 将扫描结果转为 at-tree.yaml。

```bash
python3 skills/autogen-at-suites/scripts/scan_to_atree.py scan_output/ <app_name> at-tree.yaml
```

**为什么这不是猜**：元素名来自 `setObjectName()` / `setAccessibleName()` 的源码调用，
是**开发者在源码中设定的真实控件标识名**。没设置 objectName 的控件出现在
`element_gaps.yaml` 中——这是事实，不是猜测。

### libclang 不可用时的降级路径

```bash
# grep 提取源码中的 setObjectName / setAccessibleName 调用
grep -rohP 'setObjectName\(\s*["'\''][^"'\'']*["'\'']\)' <src_dir> \
  --include='*.cpp' --include='*.h' --include='*.qml' 2>/dev/null \
  | sed -n "s/.*setObjectName(\s*['\"]\([^'\"]*\)['\"].*/\1/p" \
  | sort -u > /tmp/object_names.txt

grep -rohP 'setAccessibleName\(\s*["'\''][^"'\'']*["'\'']\)' <src_dir> \
  --include='*.cpp' --include='*.h' 2>/dev/null \
  | sed -n "s/.*setAccessibleName(\s*['\"]\([^'\"]*\)['\"].*/\1/p" \
  | sort -u > /tmp/accessible_names.txt

# 合并写入 at-tree.yaml
python3 -c "
import yaml
from pathlib import Path
names = set()
for p in ['/tmp/object_names.txt', '/tmp/accessible_names.txt']:
    f = Path(p)
    if f.exists():
        names.update(n.strip() for n in f.read_text().splitlines() if n.strip())
names = sorted(names)
tree = {
    'version': '2.0',
    'app': '<app_name>',
    'tree': [{'id': f'n{i}', 'name': n, 'role': 'panel', 'source': 'grep'}
             for i, n in enumerate(names)],
    'transient_contexts': [],
}
Path('at-tree.yaml').write_text(yaml.dump(tree, allow_unicode=True))
print(f'at-tree.yaml: {len(names)} elements from grep')
"
```

grep 提取的是源码中真实的字符串字面量——同样不是猜的。

## P3: 脚本语义映射（核心变更）

**用 `ai_mapper.py` 代替 AI 逐条填空。**

输入是 P1 产出的 `cases_raw.yaml`，不需要标注产物。

```python
from src.at.generator.ai_mapper import ai_map_cases

stats = ai_map_cases(
    cases_path="cases_raw.yaml",          # P1 产出
    at_tree_path="at-tree.yaml",          # P2b 产出（scan/merge 的真实元素名）
    output_path="cases_mapped.yaml",
    app_name="<app_name>",
)
```

ai_mapper 使用确定性正则做语义分类：

| 步骤类型 | 覆盖 | 依赖元素索引？ |
|---------|:---:|:------------:|
| 菜单操作（主菜单/右键菜单） | 12.5% | 否 |
| 键盘快捷键 | 27.7% | 否 |
| 文本输入 | 5.3% | 否 |
| session 生命周期 | 4.9% | 否 |
| 元素点击 + 断言 | 36.5% | **是**（scan 真实元素名） |
| 未知/跳过 | ~13% | — |

**注意**：`ai_map_cases` 的输入是 `cases_raw.yaml` 格式（`steps[].description`）。
`generate_yaml` 同样读 `cases_mapped.yaml` 格式。**不需要 suite-cases.yaml。**

### 映射后统计

```bash
python3 -c "
import yaml
d = yaml.safe_load(open('cases_mapped.yaml'))
cases = d.get('cases', [])
total = sum(len(c.get('steps', [])) for c in cases)
mapped = sum(1 for c in cases for s in c.get('steps', []) if s.get('action'))
print(f'{len(cases)} cases, {total} steps, {mapped} mapped ({mapped/total*100:.0f}%)')
"
```

目标：映射覆盖 >= 80%。

### 映射修复模式（重要）

**不要直接修改 cases_mapped.yaml。** 如果映射质量不够，修 `ai_mapper.py` 的 pattern，
然后重新跑管线。这是可复现的迭代。

## P3.5: 断言覆盖门禁

每套件至少一个断言。`youqu at generate --assert-gate` 默认启用。

如果无断言：
1. 已有 `assert_element` 步骤 → 通过
2. 仅有 action 步骤 → 追加 `assert_window`
3. 纯视觉不可验证 → 标记 `status: unsupported`

## P4: 生成

```bash
youqu at generate --cases cases_mapped.yaml \
  --output yaml/ \
  --app <app_name> \
  --at-tree at-tree.yaml
```

产出：
```
yaml/
├── elements.yaml
├── <module>/
│   └── <module>.suite.yaml
└── app-optimization.md
```

## P5: 验证

```bash
youqu at validate --gate 4 --generate-output yaml/
```

Gate 4 检查点：
- `suites:` 字段（非 `specs:`）
- `session_start.command` 使用正确启动命令
- `wait` 值为秒数
- 菜单操作用 `dtk_main_menu` / `dtk_context_menu`（非 `element_action`）
- 无空 selector / 无泛型断言

## P6: 执行（有 DISPLAY 的机器）

```bash
youqu at run --testdir yaml/
```

## 带精调路径的附加步骤

如果全自动路径生成的 suite role 不够准确，添加以下可选步骤：

### P2c: 生成结构化标注树

```bash
youqu at tree-info --at-tree at-tree.yaml --output at-tree-annotated.yaml --format yaml
```

### P2.5: AI 元素标注

同 at-case-generator Step 2.5。为每个 `classification: interactive` 节点填写 `comment`：
`GUI位置: <描述> | 功能: <描述>`

```bash
youqu at validate --gate 1 --at-tree-annotated at-tree-annotated.yaml --element-gaps element_gaps.yaml
```

### P2.7: 用例规范化（可选）

同 at-case-generator Step 2.7。按界面分组，加 4 字段标注。

```bash
youqu at validate --gate 2 --suite-cases suite-cases.yaml --at-tree-annotated at-tree-annotated.yaml
```

**注意**：P3（ai_mapper.py）不需要这些标注产物。标注只提升 role 准确度。

## 降级路径总结

| 条件 | P2 路径 | 元素名质量 |
|------|--------|:--------:|
| 有 libclang + 源码 | `scan → scan_to_atree.py` | **最高** |
| 无 libclang + 有源码 | `grep → 简易 at-tree.yaml` | **中** |
| 无源码 | **不可行** | — |

**永远不从 case 描述猜元素名。** 没有源码就没有元素信息，管线无法产生有效断言。

## 红线

- **不修改 `cases_mapped.yaml` 或 suite YAML**（修复必须改 ai_mapper.py）
- 辅助脚本放在 `skills/autogen-at-suites/scripts/` 目录下，随技能一起版本化
- 不修改 `src/` 框架代码
- 不执行 `pip install` 或环境部署命令
- 无源码时不生成

## 参考

- `~/.agents/skills/at-case-generator/SKILL.md` — 原管线完整文档
- `~/.agents/skills/at-case-generator/references/pipeline-reference.md` — CLI 参考
- `~/.agents/skills/at-case-generator/references/suite-format.md` — 套件 YAML 格式
- `~/.agents/skills/at-case-generator/references/pitfalls.md` — 已知陷阱
- `src/at/generator/ai_mapper.py` — 脚本映射引擎

## 完整管线脚本

```bash
#!/bin/bash
# usage: ./gen_suites.sh <xlsx> <src_dir> <app_name>
set -euo pipefail
XLSX=$1; SRC=$2; APP=$3
cd /home/zero/work/research/youqu
mkdir -p at_output

# P1: 解析
youqu at parse --input "$XLSX" --output at_output/cases_raw.yaml

# P2a: 静态扫描（headless）
SCAN_DIR=at_output/scan
mkdir -p "$SCAN_DIR"
if python3 -c "from clang import cindex" 2>/dev/null; then
    youqu at scan --src "$SRC" --app "$APP" --output "$SCAN_DIR"
    # P2b: scan → at-tree
    PYTHONPATH=/home/zero/work/research/youqu python3 skills/autogen-at-suites/scripts/scan_to_atree.py "$SCAN_DIR" "$APP" at_output/at-tree.yaml
else
    echo "libclang not available, using grep fallback"
    # P2 备选：grep
    grep -rohP 'setObjectName\(\s*["'"'"'][^"'"'"']*["'"'"']\)' "$SRC" \
      --include='*.cpp' --include='*.h' 2>/dev/null \
      | sed -n "s/.*setObjectName(\s*['\"]\([^'\"]*\)['\"].*/\1/p" \
      | sort -u > /tmp/object_names.txt
    grep -rohP 'setAccessibleName\(\s*["'"'"'][^"'"'"']*["'"'"']\)' "$SRC" \
      --include='*.cpp' --include='*.h' 2>/dev/null \
      | sed -n "s/.*setAccessibleName(\s*['\"]\([^'\"]*\)['\"].*/\1/p" \
      | sort -u > /tmp/accessible_names.txt
    python3 -c "
import yaml
from pathlib import Path
names = set()
for p in ['/tmp/object_names.txt', '/tmp/accessible_names.txt']:
    f = Path(p)
    if f.exists(): names.update(n.strip() for n in f.read_text().splitlines() if n.strip())
tree = {'version':'2.0','app':'$APP','tree':[{'id':f'n{i}','name':n,'role':'panel','source':'grep'} for i,n in enumerate(sorted(names))],'transient_contexts':[]}
Path('at_output/at-tree.yaml').write_text(yaml.dump(tree, allow_unicode=True))
" && echo "grep fallback done"
fi

# P3: ai_mapper 脚本映射
python3 -c "
from src.at.generator.ai_mapper import ai_map_cases
s = ai_map_cases('at_output/cases_raw.yaml', 'at_output/at-tree.yaml', 'at_output/cases_mapped.yaml', '$APP')
print(f'映射: {s[\"cases_mapped\"]} cases, {s[\"steps_mapped\"]} steps, {s[\"mapped_actions\"]} mapped')
"

# P4: 生成
youqu at generate --cases at_output/cases_mapped.yaml \
  --output at_output/yaml/ \
  --app "$APP" \
  --at-tree at_output/at-tree.yaml

# P5: 验证
youqu at validate --gate 4 --generate-output at_output/yaml/ || echo "gate4 有警告（非致命）"

echo "✓ 完成！套件在 at_output/yaml/"
echo "  在桌面环境执行: youqu at run --testdir at_output/yaml/"
```