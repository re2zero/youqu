---
name: at-spi-completion
description: Use when C++ Qt/DTK widgets lack AT-SPI setAccessibleName() or setObjectName() calls, typically found via libclang AST scan showing coverage <80%, or when QML elements lack Accessible.name / Accessible.role (scan_qml.py, tokenizer-based, no libclang needed), or when accessibility/automation test frameworks fail to locate interactive UI elements
---

# AT-SPI API Completion

## Overview

Scans C++ Qt/DTK source for missing `setAccessibleName()` / `setObjectName()` calls on interactive widget instances, generates PascalCase names, and guides the LLM to insert the missing calls. **QML apps** are covered by a separate path: `scan_qml.py` scans `.qml` files for interactive elements missing the `Accessible.name` / `Accessible.role` attached properties and guides insertion of an `Accessible` block (tokenizer-based — no libclang/Qt runtime needed).

**Transient element coverage:** Runtime AT-SPI dumps (dogtail/youqu at dump) cannot see transient menus — context menus, main menus, dropdowns only exist while visible. This skill's `menu_extractor.py` statically recovers them from source (see [Transient Menus](#transient-menus--naming)).

> **⚠️ 全局约束：只做增量补全，不修改已有代码。** 无论是 C++ 还是 QML 补全，都只添加缺失的 AT-SPI 调用/属性。不动缩进、空行、注释、括号风格、分号风格、命名风格、代码顺序。已有的 `setObjectName()`、`setAccessibleName()`、`Accessible.name`、`Accessible.role` 等调用**一律不修改、不删除、不移动**。

## When to Use

- Scan output shows widget AT-SPI name coverage < 80%
- Accessibility tools / YouQu test framework cannot locate UI controls by name
- "no such node" or "name not found" errors for interactive elements
- QML app: interactive elements have no `Accessible.name` / `Accessible.role` (scan_qml.py finds them)

**When NOT to use:**
- Layouts, labels, progress bars, frames — decorative elements don't need names
- Third-party code you don't own
- QML: `Text`, `Rectangle`, `Item`, layouts, `MouseArea` — decorative; skip

> **Core Principle: Only operable + assertion targets need AT-SPI names.**
> Container types (GroupBox, ScrollArea, Splitter, TabWidget, ToolBar, StatusBar, StackedWidget)
> are **decorative** — they hold other controls but tests never directly operate or assert on them.
> Only real interactive controls (buttons, inputs, sliders, menus, lists, tables, trees, tabs)
> need `setAccessibleName()` / `Accessible.name` (standard QML types auto-infer role; custom components need explicit `Accessible.role`). This spans both C++ and QML classification.
> The skill's scanners (`scan_gaps.py`, `scan_qml.py`) and quality gate enforce this:
> containers are never reported as gaps, coverage is calculated only over operable+assertion targets.
| **Scan (QML)** | `scan_qml.py --src <dir> --output tests/at/spi/` | `qml_gaps.yaml` + `qml_ok.yaml` |
| **Generate** | `naming.py pre_scan_gaps.yaml -o map.txt` | `name_map.txt` (with source_file:line info) |
| **Apply** | LLM inserts calls in constructor / `Accessible` block | Modified `.cpp` / `.qml` files |
| **Validate** | `quality_gate.py --src <dir> --build <dir> --baseline pre_scan_gaps.yaml --qml-baseline qml_gaps.yaml --expected-names expected_names.yaml` | `quality_report.json` + `quality_gate_scan/` |
| **Transient** | `menu_extractor.py --src <dir> --compile-commands <cc> --ts-dir <td> --ts-lang zh_CN` | `menu_structure.yaml` |
| **Merge** | `merge_names.py --input tests/at/spi --scan-dir tests/at/spi/quality_gate_scan --qml-dir tests/at/spi` | `expected_names.yaml` ✅ |

## Name Generation Priority

```dot
digraph name_priority {
    "Has display_text (tr())?" [shape=diamond];
    "Has variable name?" [shape=diamond];
    "Type + Class name?" [shape=diamond];
    "Use display_text → PascalCase" [shape=box];
    "Use variable → strip m_ → PascalCase" [shape=box];
    "Use ClassName_Role" [shape=box];
    "Use Unnamed<Role><Counter>" [shape=box];

    "Has display_text (tr())?" -> "Use display_text → PascalCase" [label="yes"];
    "Has display_text (tr())?" -> "Has variable name?" [label="no"];
    "Has variable name?" -> "Use variable → strip m_ → PascalCase" [label="yes"];
    "Has variable name?" -> "Type + Class name?" [label="no"];
    "Type + Class name?" -> "Use ClassName_Role" [label="yes"];
    "Type + Class name?" -> "Use Unnamed<Role><Counter>" [label="no"];
}
```

Full naming rules: [naming_conventions.md](naming_conventions.md) (PascalCase, English, 64-char max, alphanumeric + underscore only).

## Workflow

### Phase 1 — Scan

```bash
# Primary: AST-level scan (libclang)
# NOTE: Large projects may take 5+ minutes. Use `timeout 360` if needed.
# --src MUST be the repo root (contains src/ subdirectory) so that file paths
# in output match those in .ts translation files.
python3 scripts/scan_gaps.py --src /path/to/repo/root --build /path/to/build --output tests/at/spi/

# Optional: Qt Designer .ui supplement (experimental, see ui_parser.py --help)
python3 scripts/ui_parser_merge.sh tests/at/spi/
```

> ⚠️ `--src` must be the repository root, not `src/` subdirectory. The `.ts` translation files store paths relative to repo root (e.g. `src/views/w.cpp`); menu_extractor matches them by path suffix.

### Phase 2 — Generate Names

```bash
# Basic — stdout
python3 scripts/naming.py tests/at/spi/pre_scan_gaps.yaml

# For parallel apply, save mapping to a file for all agents to reference:
python3 scripts/naming.py tests/at/spi/pre_scan_gaps.yaml -o tests/at/spi/name_map.txt
```

Priority: display text (`tr()`) → variable name (strip `m_`) → `ClassName_Role` → `Unnamed<Role><Counter>`.

> **⚠️ For parallel execution**: Always run naming.py first and save the name_map file (`-o map.txt`). Every sub-agent must read this file and use the exact canonical name, **including `_2`/`_3` suffixes and the `source_file:line` info to disambiguate same-named variables in different files**. Parsing format:
> ```
> m_okButton     -> OkButton       # src/a.cpp:42
> m_okButton     -> OkButton_2     # src/b.cpp:15
> ```
> The `# {src}:{line}` suffix uniquely identifies which instance each name belongs to.

### Phase 3 — Apply Fixes (LLM)

**核心原则：增量补全，不修改已有代码。**

1. 打开 `source_file` 定位到 `line` 行附近的 `variable` 声明
2. 检查该变量附近**是否已有** `setObjectName()` / `setAccessibleName()` 调用
3. **只补缺的**，已有的**不动**
4. 不修改任何已有代码——不调缩进、不删空行、不改注释、不碰括号风格

**`pre_scan_gaps.yaml` 中每个 gap 的字段说明：**

| 字段 | 含义 | 判断依据 |
|------|------|---------|
| `has_object_name` | 是否已有 `setObjectName()` 调用 | `false` → 需要补 |
| `has_accessible_name` | 是否已有 `setAccessibleName()` 调用 | `false` → 需要补 |
| `is_action` | 是否为 `QAction` 类型 | `true` → 只能补 `setObjectName()` |
| `type` | 控件类型 | 含 `QAction`/`QShortcut`/`DAction` → 只能补 `setObjectName()` |
| `variable` | 变量名 | 用于 `name_map.txt` 查找规范名称 |
| `existing_object_name` | 已有的 `setObjectName("...")` 值 | 已有的话直接复用 |

#### 增量补全示例

```cpp
// 已有 objectName，缺 accessibleName → 只补后者
// BEFORE:
m_nameLineEdit = new DLineEdit(this);
m_nameLineEdit->setObjectName("NameLineEdit");

// AFTER: 只追加缺失的 setAccessibleName()
m_nameLineEdit = new DLineEdit(this);
m_nameLineEdit->setObjectName("NameLineEdit");          // ← 已有，不动
m_nameLineEdit->setAccessibleName("NameLineEdit");       // ← 新增
```

```cpp
// 已有 accessibleName，缺 objectName → 只补前者
// BEFORE:
ui->setupUi(this);
ui->nameEdit->setAccessibleName("NameEdit");

// AFTER:
ui->setupUi(this);
ui->nameEdit->setObjectName("NameEdit");                 // ← 新增
ui->nameEdit->setAccessibleName("NameEdit");             // ← 已有，不动
```

```cpp
// 两者都缺 → 在 new 表达式之后追加
// BEFORE:
m_nameLineEdit = new DLineEdit(this);

// AFTER:
m_nameLineEdit = new DLineEdit(this);
m_nameLineEdit->setObjectName("NameLineEdit");           // ← 新增
m_nameLineEdit->setAccessibleName("NameLineEdit");       // ← 新增
```

```cpp
// QAction: 只有 setObjectName()
// BEFORE:
m_newAction = new QAction(tr("New Window"), this);

// AFTER:
m_newAction = new QAction(tr("New Window"), this);
m_newAction->setObjectName("NewWindowAction");           // ← 新增
// 注意：不添加 setAccessibleName() — QAction 没有此方法
```

> ⚠️ **Only QWidget subclasses have `setAccessibleName()`.** QAction, QShortcut, and other pure-QObject types compile with `setObjectName()` only — adding `setAccessibleName()` to them is a **compile error**. Verify the widget type in `pre_scan_gaps.yaml` (`type` field) before inserting. Common non-widget types: `QAction *`, `QShortcut *`, `QMenu *` (QMenu IS a widget, OK), `DMenu *` (OK).
>
> ⚠️ **不要贪多。** 只补 `pre_scan_gaps.yaml` 中列出的 gap。如果一个 gap 同时有 `has_object_name=true` 和 `has_accessible_name=true`，说明它已被修复——跳过。

> ⚠️ **不能修改代码格式。** 不动缩进、空行、注释、括号风格、分号风格、命名风格。只做纯增量插入。

**插入位置规则：**
| 模式 | 插入位置 |
|------|---------|
| 成员指针 `m_var = new Type(this)` | 在 `new` 表达式**之后**（同一行或下一行缩进） |
| 值成员 / `Ui_*` 模式 `ui->setupUi(this)` | 在 `setupUi()` 调用**之后** |
| `addAction(...)` | 在 `addAction` 调用**之后** |
| `new QShortcut(...)` | 在 `new QShortcut` 表达式**之后** |

**名称来源：** 必须使用 `name_map.txt` 中的规范名称（`# {src}:{line}` 后缀用于去重），不能自行发明名称。

Re-scan every 2-3 batches to check for regressions.

### 👥 Parallel Apply Strategy

When gaps span many files (>20), use parallel sub-agents for efficiency:

1. **Generate authoritative map** — `python3 naming.py gaps.yaml -o map.txt` (produces `source_file:line` disambiguated format)
2. **Split by file** — assign disjoint file sets to sub-agents (never split gaps within one file)
3. **Sub-agents read the map** — each agent must read `map.txt` and use exact names from it, keyed by `# {src}:{line}`
4. **Re-scan after all complete** — run `scan_gaps.py` to check for collisions
5. **Fix residual collisions** — if any duplicate names remain despite the map, use `ClassName_Role` (e.g., `CompactCpuMonitor_DetailButton`, `CpuMonitor_DetailButton`)

```bash
# Step 1: Generate canonical name file (with source_file:line disambiguation)
python3 scripts/naming.py tests/at/spi/pre_scan_gaps.yaml -o tests/at/spi/name_map.txt
# map.txt format:
#   m_okButton     -> OkButton       # src/a.cpp:42
#   m_okButton     -> OkButton_2     # src/b.cpp:15

# Step 2: Sub-agents read and apply from name_map.txt

# Step 3: Validate (with regression check if expected_names.yaml exists)
python3 scripts/quality_gate.py --src ... --build ... \
  --baseline tests/at/spi/pre_scan_gaps.yaml \
  --expected-names tests/at/spi/expected_names.yaml \
  --threshold 80 --output tests/at/spi/
```

### Phase 4 — Validate (with regression check)

After applying fixes (Phase 3), validate coverage and check for regressions.
If a previous `expected_names.yaml` exists (from a prior run), pass it via
`--expected-names` to detect any backsliding on already-named widgets:

```bash
python3 scripts/quality_gate.py --src /path/to/repo/root --build /path/to/build \
  --baseline tests/at/spi/pre_scan_gaps.yaml \
  --expected-names tests/at/spi/expected_names.yaml \
  --threshold 80 --output tests/at/spi/
```

**On first run** (no prior expected_names.yaml), omit `--expected-names`:

```bash
python3 scripts/quality_gate.py --src /path/to/repo/root --build /path/to/build \
  --baseline tests/at/spi/pre_scan_gaps.yaml --threshold 80 --output tests/at/spi/
```

The fresh scan results are written to `<output>/quality_gate_scan/`. These are
used in Phase 6 to build the updated `expected_names.yaml`.

### Phase 4.5 — QML Apps: Scan + Apply (Accessible attached property)

QML controls expose AT-SPI via the **`Accessible` attached property**, not
`setObjectName()`/`setAccessibleName()`. `scan_qml.py` handles this with a
lightweight tokenizer + scope-stack parser — **no libclang / Qt runtime
required** (pure Python stdlib + PyYAML).

```bash
python3 scripts/scan_qml.py --src /path/to/repo/root --output tests/at/spi/
```

Output (same pipeline shape as the C++ scan):
- `qml_ok.yaml` — elements that already set required AT-SPI properties (standard types: `Accessible.name`; custom components: `Accessible.name` + `Accessible.role`)
- `qml_gaps.yaml` — elements missing required AT-SPI properties, each with `suggested_name`
- `qml_report.json` — summary

**`qml_gaps.yaml` 中每个 gap 的字段说明：**

| 字段 | 含义 | 判断依据 |
|------|------|---------|
| `has_accessible_name` | 是否已有 `Accessible.name` | `false` → 需要补 |
| `has_accessible_role` | 是否已有 `Accessible.role` | `false` 且是自定义组件 → 需要补 |
| `element_type` | 元素类型 | 标准类型→只补 name；自定义组件→补 name+role |
| `suggested_name` | 建议的 `Accessible.name` 值 | 直接使用，不要改 |
| `accessible_name` | 已有的 `Accessible.name` 值 | 已有的话直接复用 |
| `accessible_role` | 已有的 `Accessible.role` 值 | 已有的话直接复用 |
| `source_file` / `line` | 文件路径和行号 | 定位元素位置 |

#### QML element classification

| Category | Types | Gate behavior |
|----------|-------|---------------|
| Standard interactive | `Button`, `TextField`, `ComboBox`, `Slider`, `CheckBox`, `RadioButton`, `Switch`, `SpinBox`, `TabBar`/`TabButton`, `Menu`/`MenuItem`, `ListView`/`GridView`/`TreeView`/`TableView`, delegates (`ItemDelegate`, `CheckDelegate`, …), DTK QML (`DButton`, `DTextField`, …) | **MUST have `Accessible.name`** → gap if missing. Role auto-inferred by C++ backend. |
| Custom component | `MyWidget { … }` matching a `<Name>.qml` file in the tree | **MUST have `Accessible.name` + `Accessible.role`** → gap if missing either |
| Decorative | `Text`, `Label`, `Rectangle`, `Item`, layouts, `MouseArea`, `Flickable`, `ScrollView` | Only reported if explicitly named; never a gap |
| Structural | `State`, `Transition`, `Binding`, `Connections`, `Component`, `Repeater`, `Loader`, `Timer`, `Action`, `Shortcut` | Skipped entirely |

Custom components referenced but defined outside the scanned tree are skipped
(unknown type). Run the scan with `--src` at the repo root so custom
components resolve.

#### Fix pattern (what to insert) — 增量补全

**核心原则：**

1. 检查元素是否已有 `Accessible { ... }` 块或 `Accessible.name:` / `Accessible.role:` 属性
2. **只补缺的**，已有的不动
3. 如果已有 `Accessible { }` 块，往块内追加缺少的属性（不重建块）
4. 如果已有 `Accessible.name` 或 `Accessible.role` 的单独属性（点号形式），追加缺少的另一个
5. 不修改任何已有代码——不调缩进、不删空行、不改注释、不碰括号风格

**场景一：完全无 Accessible 属性**

在元素体内（`id` 或其他属性之后，`onClicked` 等事件处理之前）插入 `Accessible` 属性：

```qml
// BEFORE:
Button {
    id: saveButton
    text: qsTr("Save")
    onClicked: save()
}

// AFTER: 在 id/text 之后、onClicked 之前追加
Button {
    id: saveButton
    text: qsTr("Save")

    Accessible.name: "SaveButton"           // ← 新增
    onClicked: save()
}
```

```qml
// 自定义组件，完全无 Accessible
// BEFORE:
MyWidget {
    id: customWidget
}

// AFTER:
MyWidget {
    id: customWidget

    Accessible.name: "CustomWidget"         // ← 新增
    Accessible.role: Accessible.Panel       // ← 新增
}
```

**场景二：已有 Accessible 块，缺属性**

在已有 `Accessible { }` 块内部追加缺失的属性：

```qml
// 已有 Accessible 块，缺 role
// BEFORE:
MyWidget {
    id: customWidget
    Accessible {
        name: "CustomWidget"
    }
}

// AFTER: 往块内追加 role
MyWidget {
    id: customWidget
    Accessible {
        name: "CustomWidget"                 // ← 已有，不动
        role: Accessible.Panel               // ← 新增
    }
}
```

```qml
// 已有 Accessible 块，缺 name
// BEFORE:
MyWidget {
    id: customWidget
    Accessible {
        role: Accessible.Panel
    }
}

// AFTER: 往块内追加 name
MyWidget {
    id: customWidget
    Accessible {
        name: "CustomWidget"                 // ← 新增
        role: Accessible.Panel               // ← 已有，不动
    }
}
```

**场景三：已有点号形式的 Accessible 属性**

在已有 `Accessible.name:` 或 `Accessible.role:` 之后追加缺失的另一个：

```qml
// 已有 Accessible.name，缺 Accessible.role
// BEFORE:
Rectangle {
    id: fileItem
    Accessible.name: "FileItem"
}

// AFTER:
Rectangle {
    id: fileItem
    Accessible.name: "FileItem"              // ← 已有，不动
    Accessible.role: Accessible.ListItem     // ← 新增
}
```

> **注意：** 装饰元素（`Rectangle`、`Text` 等）被扫描器归为装饰类型，只要有 `Accessible.name` 就归为 ok，不会出现在 gap 中。如果这类元素实际充当交互组件（如列表项 delegate），需要手动检查并补充 `Accessible.role`。

> ⚠️ **不能修改代码格式。** 不动缩进、空行、注释、括号风格、命名风格。只做纯增量插入。

**名称来源：** 使用 `qml_gaps.yaml` 中的 `suggested_name` 字段，不要自行发明名称。

#### Suggested names (qml_gaps.yaml `suggested_name`)

Priority: `id` → display `text`/`title`/`placeholderText`/`label` →
`objectName` → `ParentType_Type` → `FileStem_Type` → `Unnamed<Role>`.
Names are deduped project-wide (`_2`/`_3` suffix). Use them verbatim, same as
the C++ `name_map.txt` discipline.

#### Validation with QML

Pass `--qml-baseline` to quality_gate; it then runs scan_qml.py too and folds
QML coverage, uniqueness, conventions, and regressions into the gate:

```bash
python3 scripts/quality_gate.py --src /path/to/repo/root \
  --baseline tests/at/spi/pre_scan_gaps.yaml \
  --qml-baseline tests/at/spi/qml_gaps.yaml \
  --expected-names tests/at/spi/expected_names.yaml \
  --threshold 80 --output tests/at/spi/
```

Pure-QML repos (no C++ sources): the C++ gates are skipped automatically;
pass `--qml-baseline` only.

#### QML gotchas

| Gotcha | Handling |
|--------|----------|
| Multi-line `Accessible { name: ... role: ... }` block | ✅ parsed (scope-stack, not line regex) |
| `Accessible.ignored: true` | Element excluded from AT-SPI → skipped, not a gap |
| Delegates (`delegate: ItemDelegate { … }`) | Delegates are templates — name the delegate element itself; each instantiation inherits it |
| `Loader { sourceComponent: … }` | The loaded component's elements are found by scanning the referenced file |
| Same `id` reused across files | Names deduped project-wide with `_2`/`_3` |
| Inline JS (`onClicked: { … }`) with braces | JS blocks never confuse the scope stack (only uppercase-element braces open elements) |
| `Accessible.name` / `Accessible.role` set on a decorative element | Reported as ok (explicit naming is respected) |
**Chinese matching:** same as C++ — test cases match the *translated* label
(`qsTr` source + `.ts`) at runtime, while `Accessible.name` stays English
PascalCase. `Accessible.name` is what tests should use as the locator anchor
(standard types auto-infer role; custom components also need `Accessible.role` for correct semantic role).

### Phase 5 — Transient Elements: Extract + Translate

Runtime AT-SPI dumps cannot see transient elements — context menus, main menus,
dropdowns, and any `tr()`-labeled widgets only exist while visible or have no
static variable reference. `menu_extractor.py` recovers them statically:

```bash
python3 scripts/menu_extractor.py \
  --src /path/to/src \
  --compile-commands /path/to/build/compile_commands.json \
  --ts-dir /path/to/translations \     # Qt .ts files
  --ts-lang zh_CN \                     # test env language (必做)
  --output tests/at/spi/
```

Output: `menu_structure.yaml` — every menu item with `text_en` (from source `tr()`/`translate()`) and `text_zh` (from `.ts` file, matched by file+line).

> **`text_zh` is mandatory for all `tr()`-sourced elements**, not just menus.
> The `.ts` file provides the Chinese translation that test cases match against
> in a Chinese test environment. If a user-visible element has a `tr()` call
> in its display text, its Chinese translation MUST be resolved via `.ts`.
> Elements without a `.ts` entry (brand names, DTK-provided translations) keep
> EN-only — this is correct behaviour for untranslated strings.

Extraction coverage (verified on deepin-terminal):

| Element | Source pattern | Extracted? |
|---------|---------------|-----------|
| Context menu items | `m_menu->addAction(tr("Copy"), ...)` | ✅ EN + ZH |
| Submenus | `QMenu *search = new QMenu(); m_menu->addMenu(search)` | ✅ parent link |
| Main menu items | `addAction(qApp->translate("Ctx", THEME_CONST))` | ✅ EN (const resolved) |
| Menu separators | `m_menu->addSeparator()` | ✅ type=separator |
| Brand names (Bing/Baidu) | `search->addAction("Bing")` | ✅ EN only (no .ts entry — correct) |
| DTK-provided translations | `qApp->translate("TitleBarMenu", ...)` | ✅ EN only (.ts lacks them — correct) |
| `addAction(existingActionVar)` | `group->addAction(lightThemeAction)` | ⏭ skipped (not a new item) |

### Phase 6 — Merge: Produce `expected_names.yaml`

Merge the **fresh scan** results (Phase 4 output in `quality_gate_scan/`) with
transient results (Phase 5) into the single regression baseline. For QML
apps pass `--qml-dir` so `qml_ok.yaml` elements land in `qml_elements`.

⚠️ **Use `--scan-dir` to point at the fresh scan output**, not the stale Phase 1
snapshot. This ensures `expected_names.yaml` reflects the actual state after
all fixes were applied:

```bash
python3 scripts/merge_names.py \
  --input tests/at/spi \
  --scan-dir tests/at/spi/quality_gate_scan \
  --qml-dir tests/at/spi \              # optional; QML apps
  --output /path/to/target/app/tests/at/spi/expected_names.yaml
```

`menu_structure.yaml` (Phase 5) is optional when absent — pure-QML apps may
have no C++ transient menus. `expected_names.yaml` gains a `qml_elements`
section; the quality gate's regression check covers both `widgets` and
`qml_elements`.

**The output MUST be written to the TARGET APP project** (e.g. `deepin-terminal/tests/at/spi/expected_names.yaml`), not to the skill directory.

**Clean up intermediate artifacts:** Once `expected_names.yaml` is produced, remove
the per-phase output files (they are NOT committed):
```bash
rm -f tests/at/spi/pre_scan_*.yaml tests/at/spi/pre_*.json \
      tests/at/spi/qml_*.yaml tests/at/spi/qml_report.json \
      tests/at/spi/menu_structure.yaml tests/at/spi/name_map.txt \
      tests/at/spi/quality_gate_scan/
```

### Phase 7 — Commit (REQUIRED in the target project)

Commit `expected_names.yaml` **together with the applied source changes** to the
**target app repository** (e.g. deepin-terminal, not this skill repo). This is
the AT-SPI naming contract — consumed by:

- **Quality Gate** (Phase 4, `--expected-names`): detects regressions in future runs
- **AT-SPI case generation** (`youqu at` pipeline): provides element names for test locators

Complete the commit using the commit skill.

```bash
cd /path/to/target/app        # e.g. deepin-terminal
# Stage: modified .cpp/.h files + tests/at/spi/expected_names.yaml
git add -A
git commit
```

## Transient Elements — Naming

Widgets created via `addAction(tr(...))` lack variable names. Name them
hierarchically by their role in the UI tree:

| Menu type | Pattern | Example |
|-----------|---------|--------|
| Context menu | `ClassName_ContextMenu_ItemText` | `TermWidget_ContextMenu_Copy` |
| Main menu | `ClassName_MainMenu_ItemText` | `MainWindow_MainMenu_Settings` |
| Nested | `ClassName_MainMenu_SubMenu_ItemText` | `TermWidget_ContextMenu_Search_Bing` |
| Dedup | `_2`/`_3` suffix | `TermWidget_ContextMenu_Split_2` |

`ItemText` comes from `text_en` (PascalCase, e.g. `Copy` → `Copy`, `Open in file manager` → `OpenInFileManager`).

**Chinese matching:** Test cases are written in Chinese and run on a Chinese
environment. The runtime AT-SPI label of a transient element is the *translated*
text (`text_zh`, e.g. `复制`). **Always match against `text_zh` when writing
tests**, not the English `text_en`. If a transient element must be locatable by
objectName, it needs explicit `setObjectName()` in source (same as Phase 3).

**Coverage boundary for `tr()`:** All user-visible strings wrapped in `tr()`
have a corresponding `.ts` entry. The `menu_extractor.py` script resolves these
by `(file, line)` match. Strings without a `.ts` entry (brand names, DTK-provided
translations) keep EN-only — this is correct behaviour: they are either not
translated or managed by the framework.

## Common Mistakes
| Mistake | Consequence | Fix |
|---------|-------------|-----|
| Naming labels/frames/layouts | Noisy results, wasted review | Only interactive widgets need names |
| Missing `setAccessibleName()` | Tests may still fail | Always add both for QWidget subclasses |
| Inserting before `new` expression | SEGFAULT | Place calls after widget creation |
| Modifying `ui_*.h` files | Changes lost on next `uic` | Modify the consumer `.cpp` file |
| Chinese / special characters | AT-SPI resolution failure | English PascalCase only |
| Naming collisions | Two widgets share `objectName` | Use `_2`/`_3` suffix or `ClassName_Role` |
| **Ignoring `_2`/`_3` suffixes** | **Duplicate objectNames pass quality gate** | **Always check uniqueness in both `pre_scan_ok.yaml` AND `pre_scan_gaps.yaml`** |
| **Parallel sub-agents inventing names** | **Inconsistent naming, missed collisions** | **All sub-agents MUST read the naming map file** |
| **Using `setAccessibleName()` on QML** | Compile error — QML has no such method | Use the `Accessible` attached property (`Accessible.name` / `Accessible.role`) |
| **Forgetting `Accessible.role` on custom/decorative QML** | Custom components and decorative elements used as interactive (e.g. `Rectangle` delegate) expose wrong semantic role | Add `Accessible.role` for custom components and decorative elements used as interactive; standard Qt Quick Controls 2 / DTK types auto-infer role |
| **Adding `Accessible.role` to standard QML types** | Unnecessary; role is auto-inferred by C++ backend | Only `Accessible.name` is needed for `Button`, `TextField`, `Slider`, etc. |


## Red Flags
- **"setObjectName is enough"** — for QWidget subclasses both calls required
- **"I modified the ui_*.h"** — it's auto-generated; edit the consuming `.cpp`
- **"Add names to everything"** — decorative elements don't need names
- **"I'll name it myself, naming.py is just a suggestion"** — always use naming.py output verbatim; it handles deduplication
- **"I'll worry about collisions later"** — fix them now; uniqueness is checked per-file, not per-widget-tree
- **"Menus are invisible to static scan"** — false: `menu_extractor.py` recovers them from `addAction(tr(...))` + `.ts` files
- **"translate() first arg is the label"** — first arg is the *context*; display text is the 2nd arg (may be a constexpr constant)
- **"Intermediate files are final output"** — `pre_scan_gaps.yaml`, `qml_gaps.yaml` and `menu_structure.yaml` are intermediate; the **only** deliverable committed is `expected_names.yaml`
- **"QML uses setObjectName/setAccessibleName"** — false: QML uses `Accessible.name` / `Accessible.role` attached properties
- **"Accessible.name is enough for QML"** — depends on type: standard Qt Quick Controls 2 / DTK types auto-infer role, so name alone is sufficient. Custom components and decorative elements used as interactive (e.g. `Rectangle` delegate) need explicit `Accessible.role`.


## Architecture

```
skills/at-spi-completion/
├── SKILL.md                    # This file
├── naming_conventions.md       # Full naming rules
└── scripts/
    ├── scan_gaps.py            # C++ AST scanner (libclang)
    ├── scan_qml.py             # QML scanner (tokenizer + scope stack, no libclang)
    ├── menu_extractor.py       # Transient menu extractor (EN+ZH via .ts)
    ├── merge_names.py          # Merge → expected_names.yaml regression baseline
    ├── ui_parser.py            # Qt Designer .ui supplement
    ├── naming.py               # PascalCase name generator (C++ + QML)
    ├── quality_gate.py         # Re-scan + baseline compare (C++ + QML)
    └── generate_type_db.py     # Type DB from DTK/Qt headers
```

Run `python3 scripts/<name>.py --help` for per-script options.

## Quality Gate
| Check | Threshold | Description |
|-------|-----------|-------------|
| Coverage (QML) | ≥ 80% | Interactive QML elements with `Accessible.name` (role auto-inferred for standard types; custom components also need `Accessible.role`) |
| Regression | 0 | Previously-named widgets (from `expected_names.yaml` `widgets` + `qml_elements`) still have names |
| Uniqueness | 0 | No duplicate `objectName`/`accessible_name` (checked on both `ok` and `gaps` files, C++ + QML) |
| Conventions | 0 | PascalCase, English, no special chars |

> ⚠️ **Regression check requires `--expected-names`**. On first run (no prior baseline), omit the flag. On subsequent runs, always provide it to prevent backsliding.
>
> ⚠️ **Quality gate checks uniqueness on both `pre_scan_ok.yaml` AND `pre_scan_gaps.yaml`**. When coverage reaches 100% the gaps file is empty; without the ok-file check, duplicates would be invisible.

Dependencies: `sudo apt install python3-clang-18 libclang-18-dev && pip install pyyaml`