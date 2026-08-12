# AT-SPI Naming Conventions

## Purpose

AT-SPI (Assistive Technology Service Provider Interface) names enable:

- **Accessibility**: Screen readers and other assistive technologies identify UI elements
- **Automated Testing**: AT-SPI-based test frameworks (like YouQu) locate widgets by name
- **UI Automation**: Tools can programmatically interact with named controls

Every interactive widget in a Qt/DTK application should have both `setObjectName()` and `setAccessibleName()` set to meaningful, unique values.

## Naming Convention

### Format: PascalCase

```
MainMenu_NewWindow          ✓
CustomCommandOptDlg_Button  ✓
m_nameLineEdit              ✗ (Hungarian notation)
custom_command_opt_dlg      ✗ (snake_case)
新建窗口                     ✗ (Chinese)
```

### Rules

| Rule | Description | Example |
|------|-------------|---------|
| **Language** | English only | `NewWindow` ✓, `新建窗口` ✗ |
| **Case** | PascalCase (first letter uppercase) | `MainMenu` ✓, `mainMenu` ✗ |
| **Separators** | Underscore for compound names | `MainMenu_NewWindow` ✓ |
| **Max length** | 64 characters | Truncate if exceeded |
| **Characters** | Alphanumeric and underscore only | `Button1` ✓, `Btn#1` ✗ |
| **Uniqueness** | Unique across the entire project | No duplicate `objectName` values |

### Prefix/Suffix Conventions

- **No Hungarian notation**: `m_nameLineEdit` → `NameInput` or `CustomCommandOptDlg_NameInput`
- **No type suffixes**: `cancelBtn` → `CancelButton` (type info is redundant)
- **No numeric suffixes** unless needed for dedup: `Button`, `Button_2`, `Button_3`

## Name Generation Priority

When generating names for missing widgets, use this priority order:

1. **Display text** (from `tr()` calls): Strip non-alphanumeric, convert to PascalCase
   - `tr("New Window")` → `NewWindow`
   
     > ⚠️ Chinese `tr("打开文件")` cannot be directly converted to English PascalCase.
     > When the display text is Chinese, the name falls through to the variable-name
     > strategy. If a meaningful English name is required, use `ClassName_Role` or
     > provide the English source from the `.ts` file manually.

2. **Variable name**: Strip `m_` prefix, split on camelCase, PascalCase
   - `m_nameLineEdit` → `NameLineEdit`
   - `m_cancelBtn` → `CancelBtn`

3. **Type + Class**: `ClassName_WidgetRole`
   - `CustomCommandOptDlg` + `DPushButton` → `CustomCommandOptDlg_Button`
   - `MainWindow` + `QAction` → `MainWindow_Action`

4. **Role-based** (last resort): `Unnamed<Role><Counter>`
   - `UnnamedButton1`, `UnnamedText2`

## Examples

### Before / After

| Widget | Before (missing) | After (suggested) |
|--------|-----------------|-------------------|
| `m_newAction` (QAction) | — | `NewAction` |
| `m_nameLineEdit` (DLineEdit) | — | `NameLineEdit` |
| `m_cancelBtn` (DPushButton) | — | `CancelBtn` |
| `m_confirmBtn` (DSuggestButton) | — | `ConfirmButton` |
| `lightThemeAction` (QAction) | — | `LightThemeAction` |
| `m_groupNameEdit` (DLineEdit) | — | `GroupNameEdit` |

### Good Names (from existing code)

```
CustomNameLineEdit
CustomCommandLineEdit
CustomShortCutLineEdit
CustomTitleBar
CustomLogoIcon
CustomTitleTextLabel
CustomCloseButton
CustomContentWidget
CustomCancelButton
CustomConfirmButton
CustomQAction
CustomShortcutConflictDialog
```

## Coverage Scope

### Core Principle: Only operable + assertion targets need AT-SPI names.

The skill's scanners and quality gate enforce this rule: **containers are never reported
as gaps, coverage is calculated only over operable+assertion targets.**

### Widgets that NEED AT-SPI names

Interactive controls that users can click, type into, or otherwise interact with:

- Push buttons, tool buttons, icon buttons, switch buttons, suggest buttons
- Check boxes, radio buttons, switches
- Line edits, text edits, combo boxes, spin boxes
- Sliders, scroll bars, dials
- List views, tree views, table views
- Tab bars (not TabWidget — the tab bar itself is interactive)
- Menu items, actions, shortcuts
- Calendar pickers, dialog button boxes
- Key sequence edits

### Widgets that DON'T need AT-SPI names

Container types and decorative elements — tests never directly operate or assert on them:

- Layouts (QHBoxLayout, QVBoxLayout, QGridLayout)
- Labels (QLabel, DLabel, Text) — unless interactive (e.g. DShortcutEditLabel)
- Progress bars, busy indicators
- Frames, group boxes (QGroupBox, DGroupBox, GroupBox)
- Scroll areas / scroll views (QScrollArea, DScrollArea, ScrollView)
- Splitters (QSplitter, DSplitter, SplitView)
- Stacked widgets / stack views (QStackedWidget, DStackedWidget, StackView)
- Status bars (QStatusBar, DStatusBar)
- Tab widgets - the TabWidget itself is a container (TabBar tabs are interactive)
- Tool bars (QToolBar, DToolBar, ToolBar)
- Rectangles, Items, Text, Images — purely decorative QML elements
- Spacers, separators, tool separators
## Quality Gate

After applying fixes, run the quality gate to verify:

| Check | Threshold | Description |
|-------|-----------|-------------|
| **Coverage** | ≥80% | Percentage of widgets with names |
| **New gaps** | 0 | No new gaps introduced |
| **Regression** | 0 | Previously-named widgets (from `expected_names.yaml`) still have names |
| **Uniqueness** | 0 issues | No duplicate objectName values |
| **Conventions** | 0 issues | All names follow PascalCase, English only |

## References

- [AT-SPI Documentation](https://www.freedesktop.org/wiki/Accessibility/AT-SPI2/)
- [Qt Accessibility](https://doc.qt.io/qt-6/accessible.html)
- [DTK Accessibility Guidelines](https://github.com/linuxdeepin/dtkwidget)
## Transient Elements — Translation + Naming (menu_extractor.py)

**All `tr()`-sourced display text must have a `.ts`-resolved Chinese translation.**
This is mandatory — not just for menus. Every user-visible string wrapped in
`tr()` corresponds to a `.ts` entry that provides `text_zh` for test matching.
The `menu_extractor.py` script resolves translations by `(file, line)` match
against the app's `.ts` file.

Menu items created via `addAction(tr(...))` have no variable names. Name them
hierarchically:

| Menu type | Pattern | Example |
|-----------|---------|---------|
| Context menu | `ClassName_ContextMenu_ItemText` | `TermWidget_ContextMenu_Copy` |
| Main menu | `ClassName_MainMenu_ItemText` | `MainWindow_MainMenu_Settings` |
| Nested | `ClassName_MainMenu_SubMenu_ItemText` | `TermWidget_ContextMenu_Search_Bing` |
| Dedup | `_2`/`_3` suffix | `TermWidget_ContextMenu_Split_2` |

ItemText derives from the English source text (`text_en`), PascalCased
(`Open in file manager` → `OpenInFileManager`).

**Chinese matching:** Test cases are written in Chinese and run on a Chinese
environment. The runtime AT-SPI label of a menu item is the *translated* text
(`text_zh`, e.g. `复制`) resolved from the app's `.ts` file. Locate menu items
by `text_zh` when writing tests; use `text_en`-derived objectNames only if the
source explicitly calls `setObjectName()` on the menu item.

## QML Elements — Accessible Naming (scan_qml.py)

QML controls expose AT-SPI through the **`Accessible` attached property** —
there is no `setObjectName()`/`setAccessibleName()` on QML objects. Two
equivalent forms are accepted by Qt:

```qml
// Form 1 — dotted properties
Button {
    id: saveButton
    Accessible.name: "SaveButton"
    Accessible.role: Accessible.Button
}

// Form 2 — attached block
TextField {
    id: nameInput
    Accessible {
        name: "NameInput"
        role: Accessible.EditableText
    }
}
```

### QML Name Generation Priority (scan_qml.py `suggested_name`)

1. **`id` attribute** → PascalCase
   - `id: saveButton` → `SaveButton`
2. **Display text** (`text`/`title`/`placeholderText`/`label`) → PascalCase
   - `text: "Open file"` → `OpenFile`
   - Chinese `text: qsTr("打开文件")` falls through (cannot PascalCase → next)
3. **`objectName`** (rare in QML, but valid) → PascalCase
4. **Parent type + element type**: `ParentType_Type`
   - `GroupBox` containing a `Switch` → `GroupBox_Switch`
   - `Dialog` containing a `Button` → `Dialog_Button`
5. **File stem + element type**: `FileStem_Type`
   - `MainWindow.qml` + `Slider` → `MainWindow_Slider`
6. **Role-based** (last resort): `Unnamed<Role><Counter>`

Names are deduped project-wide with `_2`/`_3` suffixes — reuse the
`suggested_name` values verbatim.

### QML roles (from QtQuick.Accessible)

Use the standard enum for the element type:

| QML element | Accessible.role |
|-------------|-----------------|
| `Button`, `ToolButton` | `Accessible.Button` |
| `TextField`, `TextArea` | `Accessible.EditableText` |
| `ComboBox` | `Accessible.ComboBox` |
| `Slider` | `Accessible.Range` |
| `CheckBox` | `Accessible.CheckBox` |
| `RadioButton` | `Accessible.RadioButton` |
| `Switch` | `Accessible.CheckBox` (or `Accessible.ToggleButton` on newer Qt) |
| `SpinBox`, `Tumbler` | `Accessible.SpinBox` |
| `ListView`/`GridView`/`TableView`/`TreeView` | `Accessible.List`/`Table`/`Tree` |
| `Menu`, `MenuItem` | `Accessible.Menu`/`MenuItem` |

### QML rules

| Rule | Description | Example |
|------|-------------|---------|
| **Language** | English only | `SaveButton` ✓, `保存按钮` ✗ |
| **Case** | PascalCase | `NameInput` ✓, `nameInput` ✗ |
| **Chars** | Alphanumeric + underscore only | `VolumeSlider` ✓ |
| **Max length** | 64 chars | Truncate |
| **Uniqueness** | Unique across the project (`_2`/`_3` dedup) | `Dialog_Button_2` |
| **Role** | Always pair `Accessible.name` with `Accessible.role` | `Accessible.role: Accessible.Button` |
| **Decorative** | `Text`, `Rectangle`, `Item`, layouts never get names | skip |

### QML scope (what scan_qml.py reports)

- **Interactive** (MUST have `Accessible.name`): controls, inputs, menus,
  list/tree/table views, delegates, DTK QML controls (`DButton`, `DTextField`,
  `DListView`, …), and custom components (`MyWidget.qml`).
- **Decorative** (never gaps): `Text`, `Label`, `Rectangle`, `Image`, layouts,
  `MouseArea`, `ScrollView`, popups.
- **Structural** (skipped): `State`, `Transition`, `Binding`, `Connections`,
  `Component`, `Repeater`, `Loader`, `Timer`, `Action`, `Shortcut`.
- `Accessible.ignored: true` → element deliberately excluded; skipped, not a gap.
