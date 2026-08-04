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
   - `tr("打开文件")` → `OpenFile`

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
| `m_cancelBtn` (DPushButton) | — | `CancelButton` |
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

### Widgets that NEED AT-SPI names

Interactive controls that users can click, type into, or otherwise interact with:

- Push buttons, tool buttons, icon buttons
- Check boxes, radio buttons
- Line edits, text edits, combo boxes
- Spin boxes, sliders, scroll bars
- List views, tree views, table views
- Tab widgets, tab bars
- Menu items, actions
- Shortcut inputs (key sequence edits)

### Widgets that DON'T need AT-SPI names

- Layouts (QHBoxLayout, QVBoxLayout, QGridLayout)
- Labels (QLabel, DLabel) — unless interactive
- Progress bars
- Frames, group boxes (containers)
- Decorative elements (separators, spacers)

## Quality Gate

After applying fixes, run the quality gate to verify:

| Check | Threshold | Description |
|-------|-----------|-------------|
| **Coverage** | ≥80% | Percentage of widgets with names |
| **New gaps** | 0 | No new gaps introduced |
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
