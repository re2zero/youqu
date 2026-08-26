---
name: at-spi-completion
description: >
  Fix missing AT-SPI accessibility names in Qt/DTK C++ widgets and QML
  elements (setObjectName/setAccessibleName, Accessible.name/role) so
  accessibility tools and YouQu tests can locate them. Consumes
  at-spi-coverage scan products (pre_scan_gaps.yaml / qml_gaps.yaml),
  generates canonical PascalCase names via naming.py, and applies
  incremental fixes (C++ auto + LLM, QML).
  Use when the user reports "no such node", "name not found",
  setAccessibleName 缺口, 控件补全, 控件无名称, AT-SPI 名称缺失,
  or wants to fix accessibility gaps after a coverage scan.
  For measuring coverage only (no fixing), use at-spi-coverage instead.
version: "1.1.0"
license: MIT
author: Uniontech
---

# AT-SPI API Completion

## Overview

Adds missing AT-SPI names to interactive Qt/DTK widgets and QML elements
(`setAccessibleName()` / `setObjectName()`, `Accessible.name` / `Accessible.role`)
so accessibility tools and YouQu tests can locate them.

**扫描由 `at-spi-coverage` 技能负责。** 本技能**不扫描**——它消费
`at-spi-coverage` 的扫描产物（`pre_scan_gaps.yaml` / `pre_scan_ok.yaml` /
`qml_gaps.yaml` / `qml_ok.yaml`），生成规范名称并实施增量补全，最后用
`quality_gate.py` 重新扫描验证。扫描器（`scan_gaps.py` / `scan_qml.py` /
`type_db.json`）的唯一所有者是 `at-spi-coverage`，本技能不再自带副本。

## When to Use

- `at-spi-coverage` 扫描产物显示覆盖率 < 80%，或存在待补全 gap
- Accessibility tools / YouQu test framework cannot locate UI controls by name
- "no such node" or "name not found" errors for interactive elements
- QML app: interactive elements have no `Accessible.name` / `Accessible.role`
  （由 `at-spi-coverage` 的 `scan_qml.py` 找出）

**前置依赖：** 先运行 `at-spi-coverage` 技能（`coverage_stats.py`）得到
`pre_scan_gaps.yaml` / `qml_gaps.yaml` 等扫描产物，再进入本技能补全。
本技能不执行初始扫描。

**When NOT to use:**
- Layouts, labels, progress bars, frames — decorative elements don't need names
- Third-party code you don't own
- QML: `Text`, `Rectangle`, `Item`, layouts, `MouseArea` — decorative; skip
- Measuring coverage only (no code changes) — use `at-spi-coverage` instead

> **Core Principle: Only operable + assertion targets need AT-SPI names.**
> Container types (GroupBox, ScrollArea, Splitter, TabWidget, ToolBar, StatusBar, StackedWidget)
> are **decorative** — they hold other controls but tests never directly operate or assert on them.
> Only real interactive controls (buttons, inputs, sliders, menus, lists, tables, trees, tabs)
> need `setAccessibleName()` / `Accessible.name` (standard QML types auto-infer role; custom components need explicit `Accessible.role`). This spans both C++ and QML classification.
> The scanners (`scan_gaps.py`, `scan_qml.py`) live in the `at-spi-coverage`
> skill and enforce this: containers are never reported as gaps, coverage is
> calculated only over operable+assertion targets.

## Default Path

| Project type | Flow |
|--------------|------|
| C++ only | Phase 1 → 2 → 3 → 5 → 6 |
| QML only | Phase 1 → 2 → 4 → 5 → 6 |
| Mixed C++/QML | Phase 1 → 2 → 3 → 4 → 5 → 6 |

## Pipeline

| Step | Tool | Output |
|------|------|--------|
| **Input (scan)** | `at-spi-coverage` 产出（`coverage_stats.py`） | `pre_scan_gaps.yaml` + `pre_scan_ok.yaml` + `qml_gaps.yaml` + `qml_ok.yaml` |
| **Generate** | `naming.py tests/at/spi/pre_scan_gaps.yaml -o tests/at/spi/name_map.txt` | `name_map.txt` (with source_file:line info) |
| **Apply (auto)** | `apply_fixes.py` | `apply_fixes_report.json` + modified `.cpp` files |
| **Apply (LLM)** | LLM inserts calls for unsupported gaps / QML files | Modified `.cpp` / `.qml` files |
| **Validate** | `quality_gate.py` | `quality_report.json` + `quality_gate_scan/` |

## Workflow

> **工作目录约定：** 所有命令默认在 **目标应用仓库根目录** 执行（例如 `deepin-terminal/`），`scripts/` 目录相对于技能路径 `skills/at-spi-completion/`。
>
> **输入输出路径约定：** 扫描产物由 `at-spi-coverage` 产出到 `tests/at/spi/` 或
> `<repo>/coverage_scan/`；本技能的中间产物（`name_map.txt`、
> `apply_fixes_report.json`）输出到 `tests/at/spi/`。
>
> **前置：** 扫描产物由 `at-spi-coverage` 技能产出。若尚未扫描，先运行
> `at-spi-coverage` 的 `coverage_stats.py`（见其 SKILL.md），再回到本技能。

### Phase 1 — 获取扫描产物（来自 at-spi-coverage）

本技能**不执行初始扫描**。扫描由 `at-spi-coverage` 技能完成，产物为：

```bash
# 由 at-spi-coverage 技能执行（本技能不运行）：
# python3 <at-spi-coverage>/scripts/coverage_stats.py --src /path/to/repo/root
# 产物写入 <repo>/coverage_scan/ 或 tests/at/spi/：
#   pre_scan_gaps.yaml   — 缺失 AT-SPI 调用的控件列表（补全输入）
#   pre_scan_ok.yaml     — 已有完整命名的控件列表
#   qml_gaps.yaml        — QML 缺失 Accessible 属性的元素列表
#   qml_ok.yaml          — QML 已有 Accessible 属性的元素列表
```

> ⚠️ 若 `pre_scan_gaps.yaml` 不存在，先运行 `at-spi-coverage` 技能完成扫描，
> 不要在本技能内自行扫描。扫描器（`scan_gaps.py` / `scan_qml.py`）只存在于
> `at-spi-coverage/scripts/`。

**输入：** `pre_scan_gaps.yaml`（缺失 AT-SPI 调用的控件列表）+ `pre_scan_ok.yaml`（已有完整命名的控件列表）+ `qml_gaps.yaml` / `qml_ok.yaml`（QML）

### Phase 2 — Generate Names

```bash
# Basic — stdout
python3 scripts/naming.py tests/at/spi/pre_scan_gaps.yaml

# For parallel apply, save mapping to a file for all agents to reference:
python3 scripts/naming.py tests/at/spi/pre_scan_gaps.yaml -o tests/at/spi/name_map.txt
```

Priority: display text (`tr()`) → variable name (strip `m_`) → `ClassName_Role` → `Unnamed<Role><Counter>`.
Full naming rules: [naming_conventions.md](naming_conventions.md).

> **⚠️ 所有后续步骤必须使用 `name_map.txt` 中的规范名称**，包括 `_2`/`_3` 后缀。格式：
> ```
> m_okButton     -> OkButton       # src/a.cpp:42
> m_okButton     -> OkButton_2     # src/b.cpp:15
> ```
> `# {src}:{line}` 后缀用于区分不同文件中同名变量。

### Phase 3 — Apply Fixes (C++)

Phase 3 分为两步：Phase 3a（自动化脚本）+ Phase 3b（LLM 人工修复）。

#### Phase 3a — Automated Apply (`apply_fixes.py`)

**覆盖 80% 常见 C++ 模式**，剩余 20% 交给 Phase 3b LLM 处理。

```bash
# Step 1: 生成规范名称映射
python3 scripts/naming.py tests/at/spi/pre_scan_gaps.yaml -o tests/at/spi/name_map.txt

# Step 2: 自动修复（--dry-run 预览）
python3 scripts/apply_fixes.py tests/at/spi/pre_scan_gaps.yaml \
  --name-map tests/at/spi/name_map.txt --src-dir . --dry-run

# Step 3: 确认无误后执行
python3 scripts/apply_fixes.py tests/at/spi/pre_scan_gaps.yaml \
  --name-map tests/at/spi/name_map.txt --src-dir .

# Step 4: 查看报告
cat apply_fixes_report.json | python3 -m json.tool
```

**未支持（unsupported）的 gap 交给 Phase 3b LLM 处理。**

> ⚠️ **Phase 3a 完成后，必须继续执行 Phase 5（重新扫描验证）**，确认覆盖率
> 提升、无新增 gap。

#### Phase 3b — Apply Fixes (LLM)

处理 Phase 3a 无法覆盖的 gap（`apply_fixes_report.json` 中
`status: "unsupported"` 的项）。

**核心原则：增量补全，不修改已有代码。**

1. 打开 `source_file` 定位到 `line` 行（`pre_scan_gaps.yaml` 中的行号，指向 `.h` 文件中的 FIELD_DECL）
2. **注意：`line` 指向 `.h` 文件中的变量声明行，`new` 表达式通常在 `.cpp` 文件中**。到 `.cpp` 文件中搜索 `variable = new Type(...)` 或 `ui->variable = new Type(...)` 或 `ui->setupUi(this)` 作为插入点
3. 检查插入点附近**是否已有** `setObjectName()` / `setAccessibleName()` 调用
4. **只补缺的**，已有的**不动**
**名称来源：** 必须使用 `name_map.txt` 中的规范名称，不能自行发明名称。

> ⚠️ **Only QWidget subclasses have `setAccessibleName()`.** QAction, QShortcut,
> and other pure-QObject types compile with `setObjectName()` only — adding
> `setAccessibleName()` to them is a **compile error**. Verify the `type` field in
> `pre_scan_gaps.yaml` before inserting.

> **Read `references/apply-patterns.md`** for: gap 字段表、插入位置规则、增量补全
> 示例、`setAccessibleName()` 编译限制、大项目 Parallel Apply Strategy。

### Phase 4 — QML Apply

QML controls expose AT-SPI via the **`Accessible` attached property** (not
`setObjectName()`/`setAccessibleName()`). Run this phase for QML apps
or mixed C++/QML projects.

**QML 扫描由 `at-spi-coverage` 技能完成**（`scan_qml.py` 在其 `scripts/` 下）。
本技能直接消费其产物 `qml_gaps.yaml` / `qml_ok.yaml`，不再自行扫描：

```bash
# 由 at-spi-coverage 技能执行（本技能不运行）：
# python3 <at-spi-coverage>/scripts/scan_qml.py --src /path/to/repo/root --output tests/at/spi/
```

**分类：** 标准交互类型（`Button`, `TextField`, `ComboBox`, `Slider`, …）→ 只补
`Accessible.name`（role 自动推断）；自定义组件（`MyWidget.qml`）→ 补
`Accessible.name` + `Accessible.role`；装饰元素（`Text`, `Rectangle`, `Item`,
layouts）→ 不补。

**核心原则：**
1. 检查元素是否已有 `Accessible { ... }` 块或 `Accessible.name:` / `Accessible.role:` 属性
2. **只补缺的**，已有的不动
3. 已有 `Accessible { }` 块 → 往块内追加缺少的属性（不重建块）
4. 已有点号形式属性 → 追加缺少的另一个
5. 不修改任何已有代码——只做纯增量插入

**名称来源：** 使用 `qml_gaps.yaml` 中的 `suggested_name` 字段，不要自行发明名称。

> **Read `references/qml-apply.md`** for: `qml_gaps.yaml` 字段表、QML element
> classification、完整 fix patterns（含三种场景示例）、QML gotchas。
> QML 命名规则见 [naming_conventions.md](naming_conventions.md) 的
> `## QML Elements — Accessible Naming` 一节。

### Phase 5 — Validate (重新扫描验证)

补全后重新扫描验证。`quality_gate.py` 在运行时从 `at-spi-coverage/scripts/`
导入同一套扫描器，保证补全前后用同一扫描器、覆盖率数字一致。

```bash
# 首次运行（无历史基线）：
python3 scripts/quality_gate.py --src /path/to/repo/root --build /path/to/build \
  --baseline tests/at/spi/pre_scan_gaps.yaml --threshold 80 --output tests/at/spi/
```

QML 项目追加 `--qml-baseline tests/at/spi/qml_gaps.yaml`（见
`references/qml-apply.md`）。

验证目标：`quality_report.json` 中覆盖率达标（完整补全 = 100%）、
`fixed_gaps` 等于基线 gap 数、`new_gaps` 为 0。达到即补全完成。

**Clean up intermediate artifacts**（不提交）：
```bash
rm -f tests/at/spi/pre_scan_*.yaml tests/at/spi/pre_*.json \
      tests/at/spi/qml_*.yaml tests/at/spi/qml_report.json \
      tests/at/spi/name_map.txt tests/at/spi/quality_gate_scan/
```

### Phase 6 — Commit (REQUIRED in the target project)

提交补全后的源码改动到 **目标应用仓库**（例如 `deepin-terminal`，不是技能仓库）。

Complete the commit using the commit skill.

```bash
cd /path/to/target/app        # e.g. deepin-terminal
# Stage: modified .cpp/.h files（补全改动）
git add -A
git commit
```

## Gotchas

| Mistake | Consequence | Fix |
|---------|-------------|-----|
| Naming labels/frames/layouts | Noisy results, wasted review | Only interactive widgets need names |
| Missing `setAccessibleName()` | Tests may still fail | Always add both for QWidget subclasses |
| Inserting before `new` expression | SEGFAULT | Place calls after widget creation |
| Modifying `ui_*.h` files | Changes lost on next `uic` | Modify the consumer `.cpp` file |
| Chinese / special characters | AT-SPI resolution failure | English PascalCase only |
| Naming collisions | Two widgets share `objectName` | Use `_2`/`_3` suffix or `ClassName_Role` |
| Ignoring `_2`/`_3` suffixes | Duplicate objectNames pass quality gate | Always check uniqueness in both `pre_scan_ok.yaml` AND `pre_scan_gaps.yaml` |
| Parallel sub-agents inventing names | Inconsistent naming, missed collisions | All sub-agents MUST read the naming map file |
| Using `setAccessibleName()` on QML | Compile error — QML has no such method | Use the `Accessible` attached property (`Accessible.name` / `Accessible.role`) |
| Forgetting `Accessible.role` on custom/decorative QML | Custom components / decorative-as-interactive expose wrong semantic role | Add `Accessible.role` for custom components and decorative elements used as interactive; standard Qt Quick Controls 2 / DTK types auto-infer role |
| Adding `Accessible.role` to standard QML types | Unnecessary; role is auto-inferred by C++ backend | Only `Accessible.name` is needed for `Button`, `TextField`, `Slider`, etc. |

**Red flags** — "setObjectName is enough" (QWidget subclasses need both);
"I modified the ui_*.h" (auto-generated; edit the consuming `.cpp`);
"I'll name it myself, naming.py is just a suggestion" (always use naming.py
output verbatim — it handles deduplication).

## Quality Gate

| Check | Threshold | Description |
|-------|-----------|-------------|
| Coverage (C++) | ≥ 80% (完整补全 100%) | Interactive C++ widgets with both `setObjectName()` + `setAccessibleName()` |
| Coverage (QML) | ≥ 80% (完整补全 100%) | Interactive QML elements with `Accessible.name` (role auto-inferred for standard types; custom components also need `Accessible.role`) |
| Uniqueness | 0 | No duplicate `objectName`/`accessible_name` (checked on both `ok` and `gaps` files, C++ + QML) |
| Conventions | 0 | PascalCase, English, no special chars |

> ⚠️ **Quality gate checks uniqueness on both `pre_scan_ok.yaml` AND `pre_scan_gaps.yaml`**. When coverage reaches 100% the gaps file is empty; without the ok-file check, duplicates would be invisible.

## Architecture

```
skills/at-spi-completion/
├── SKILL.md                    # This file
├── naming_conventions.md       # Full naming rules (C++ + QML)
├── references/
│   ├── apply-patterns.md       # C++ Phase 3 detail (fields, patterns, parallel)
│   └── qml-apply.md            # QML Phase 4 detail (classification, patterns, gotchas)
└── scripts/
    ├── naming.py               # PascalCase name generator (C++ + QML)
    ├── apply_fixes.py          # Automated fix application for C++ gaps
    └── quality_gate.py         # Re-scan + baseline compare (C++ + QML)

# 扫描器由 at-spi-coverage 技能持有（本技能不复制）：
skills/at-spi-coverage/scripts/
    ├── scan_gaps.py            # C++ AST scanner (libclang)
    ├── scan_qml.py             # QML scanner (tokenizer + scope stack, no libclang)
    └── type_db.json            # Type DB
```

`quality_gate.py` 在运行时从 `at-spi-coverage/scripts/` 导入扫描器
（`scan_gaps.py` / `scan_qml.py`），保证补全前后用同一扫描器。
Run `python3 scripts/<name>.py --help` for per-script options.

## Dependencies

`sudo apt install python3-clang-18 libclang-18-dev && pip install pyyaml`

扫描器（`scan_gaps.py`）需要 libclang Python 绑定；未安装时会降级或报错。
QML 扫描（`scan_qml.py`）纯 tokenizer 实现，无外部依赖。
扫描器位于 `at-spi-coverage/scripts/`，本技能通过 `quality_gate.py` 运行时导入。
