# QML Apply Fixes — 详细补全规则

Read this when doing Phase 4 (QML Apply). SKILL.md Phase 4 gives the default
path; this file holds the gap-field semantics, element classification, fix
patterns, suggested-name priority, and QML gotchas.

## Input (from at-spi-coverage)

- `qml_ok.yaml` — elements that already set required AT-SPI properties (standard types: `Accessible.name`; custom components: `Accessible.name` + `Accessible.role`)
- `qml_gaps.yaml` — elements missing required AT-SPI properties, each with `suggested_name`
- `qml_report.json` — summary

## `qml_gaps.yaml` 中每个 gap 的字段说明

| 字段 | 含义 | 判断依据 |
|------|------|---------|
| `has_accessible_name` | 是否已有 `Accessible.name` | `false` → 需要补 |
| `has_accessible_role` | 是否已有 `Accessible.role` | `false` 且是自定义组件 → 需要补 |
| `element_type` | 元素类型 | 标准类型→只补 name；自定义组件→补 name+role |
| `suggested_name` | 建议的 `Accessible.name` 值 | 直接使用，不要改 |
| `accessible_name` | 已有的 `Accessible.name` 值 | 已有的话直接复用 |
| `accessible_role` | 已有的 `Accessible.role` 值 | 已有的话直接复用 |
| `source_file` / `line` | 文件路径和行号 | 定位元素位置 |

## QML element classification

| Category | Types | Gate behavior |
|----------|-------|---------------|
| Standard interactive | `Button`, `TextField`, `ComboBox`, `Slider`, `CheckBox`, `RadioButton`, `Switch`, `SpinBox`, `TabBar`/`TabButton`, `Menu`/`MenuItem`, `ListView`/`GridView`/`TreeView`/`TableView`, delegates (`ItemDelegate`, `CheckDelegate`, …), DTK QML (`DButton`, `DTextField`, …) | **MUST have `Accessible.name`** → gap if missing. Role auto-inferred by C++ backend. |
| Custom component | `MyWidget { … }` matching a `<Name>.qml` file in the tree | **MUST have `Accessible.name` + `Accessible.role`** → gap if missing either |
| Decorative | `Text`, `Label`, `Rectangle`, `Item`, layouts, `MouseArea`, `Flickable`, `ScrollView` | Only reported if explicitly named; never a gap |
| Structural | `State`, `Transition`, `Binding`, `Connections`, `Component`, `Repeater`, `Loader`, `Timer`, `Action`, `Shortcut` | Skipped entirely |

Custom components referenced but defined outside the scanned tree are skipped
(unknown type). Run the scan with `--src` at the repo root so custom
components resolve.

## Fix pattern (what to insert) — 增量补全

**核心原则：**

1. 检查元素是否已有 `Accessible { ... }` 块或 `Accessible.name:` / `Accessible.role:` 属性
2. **只补缺的**，已有的不动
3. 如果已有 `Accessible { }` 块，往块内追加缺少的属性（不重建块）
4. 如果已有 `Accessible.name` 或 `Accessible.role` 的单独属性（点号形式），追加缺少的另一个
5. 不修改任何已有代码——不调缩进、不删空行、不改注释、不碰括号风格

### 场景一：完全无 Accessible 属性

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

### 场景二：已有 Accessible 块，缺属性

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

### 场景三：已有点号形式的 Accessible 属性

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

> **注意：** 装饰元素（`Rectangle`、`Text` 等）被扫描器归为装饰类型，只要有
> `Accessible.name` 就归为 ok，不会出现在 gap 中。如果这类元素实际充当交互组件
> （如列表项 delegate），需要手动检查并补充 `Accessible.role`。

> ⚠️ **不能修改代码格式。** 不动缩进、空行、注释、括号风格、命名风格。只做纯增量插入。

**名称来源：** 使用 `qml_gaps.yaml` 中的 `suggested_name` 字段，不要自行发明名称。

## Suggested names (qml_gaps.yaml `suggested_name`)

Priority: `id` → display `text`/`title`/`placeholderText`/`label` →
`objectName` → `ParentType_Type` → `FileStem_Type` → `Unnamed<Role>`.
Names are deduped project-wide (`_2`/`_3` suffix). Use them verbatim, same as
the C++ `name_map.txt` discipline.

## Validation with QML

Pass `--qml-baseline` to quality_gate (Phase 5) so it runs scan_qml.py and folds
QML coverage, uniqueness, and conventions into the gate:

```bash
python3 scripts/quality_gate.py --src /path/to/repo/root \
  --baseline tests/at/spi/pre_scan_gaps.yaml \
  --qml-baseline tests/at/spi/qml_gaps.yaml \
  --threshold 80 --output tests/at/spi/
```

Pure-QML repos (no C++ sources): the C++ gates are skipped automatically;
pass `--qml-baseline` only.

## QML gotchas

| Gotcha | Handling |
|--------|----------|
| Multi-line `Accessible { name: ... role: ... }` block | ✅ parsed (scope-stack, not line regex) |
| `Accessible.ignored: true` | Element excluded from AT-SPI → skipped, not a gap |
| Delegates (`delegate: ItemDelegate { … }`) | Delegates are templates — name the delegate element itself; each instantiation inherits it |
| `Loader { sourceComponent: … }` | The loaded component's elements are found by scanning the referenced file |
| Same `id` reused across files | Names deduped project-wide with `_2`/`_3` |
| Inline JS (`onClicked: { … }`) with braces | JS blocks never confuse the scope stack (only uppercase-element braces open elements) |
| `Accessible.name` / `Accessible.role` set on a decorative element | Reported as ok (explicit naming is respected) |
| Chinese matching | Same as C++ — test cases match the *translated* label (`qsTr` source + `.ts`) at runtime, while `Accessible.name` stays English PascalCase |
