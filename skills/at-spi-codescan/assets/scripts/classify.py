#!/usr/bin/env python3
"""AT-SPI 控件分类常量 — 可交互 vs 装饰 vs 布局。

两条分析线共享此分类标准，确保覆盖率可比。
"""
from __future__ import annotations

# ── C++ 可交互控件（需要 AT-SPI 名称）─────────────────────────────
INTERACTIVE_CLASSES: frozenset[str] = frozenset({
    # DTK 按钮
    "DPushButton", "DToolButton", "DIconButton", "DSwitchButton",
    "DSuggestButton", "DCommandLinkButton", "DFloatingButton",
    "DAbstractButton", "DButtonBox",
    # Qt 按钮
    "QPushButton", "QToolButton", "QDialogButtonBox",
    # DTK 输入
    "DLineEdit", "DTextEdit", "DComboBox", "DCheckBox", "DRadioButton",
    "DSlider", "DSpinBox", "DPasswordEdit", "DSearchEdit", "DFileChooserEdit",
    "DKeySequenceEdit", "DPlainTextEdit",
    # Qt 输入
    "QLineEdit", "QTextEdit", "QPlainTextEdit", "QComboBox", "QCheckBox",
    "QRadioButton", "QSlider", "QSpinBox", "QDoubleSpinBox", "QKeySequenceEdit",
    # DTK 列表/树/表
    "DListView", "DTreeView", "DTabBar",
    # Qt 列表/树/表
    "QListWidget", "QTreeWidget", "QTableWidget",
    "QListView", "QTreeView", "QTableView",
    "QTabBar", "QScrollBar", "QCalendarWidget",
    # 菜单
    "QMenu", "QMenuBar", "DMenu", "DMenuItem", "DMenuBar",
    # 抽象基类（继承链分类用）
    "QAbstractButton", "QAbstractItemView", "QAbstractScrollArea",
    "QAbstractSlider", "QAbstractSpinBox", "QWidgetAction",
})

# ── C++ 非 Widget 可交互（只有 setObjectName，没有 setAccessibleName）──
NON_WIDGET_INTERACTIVE: frozenset[str] = frozenset({
    "QAction", "QActionGroup", "QShortcut", "QButtonGroup", "DAction",
})

DECORATIVE_CLASSES: frozenset[str] = frozenset({
    # DTK 装饰
    "DLabel", "DTitlebar", "DProgressBar", "DIndeterminateProgressBar",
    "DWaterProgress", "DAlertControl",
    "DHeaderLine", "DShadowLine", "DVerticalLine",
    "DArrowRectangle", "DToolTip", "DClipEffectWidget",
    "DFlyoutWidget", "DMessageBox",
    "DFloatingMessage", "DFloatingWidget", "DDrawer",
    "DSegmentedControl",
    "DGroupBox", "DScrollArea", "DSplitter",
    "DStackedWidget", "DStatusBar", "DTabWidget", "DToolBar",
    # DTK 窗口/容器基类（继承链分类用）
    "DWidget", "DMainWindow", "DDialog", "DAbstractDialog", "DFrame",
    "DGraphicsView",
    # Qt 装饰
    "QLabel", "QProgressBar", "QFrame", "QGraphicsView",
    "QMainWindow", "QWidget", "QDialog", "QWindow",
    "QGroupBox", "QScrollArea", "QSplitter",
    "QStackedWidget", "QStatusBar", "QTabWidget", "QToolBar",
})

# ── C++ 布局（跳过）─────────────────────────────────────────────
LAYOUT_CLASSES: frozenset[str] = frozenset({
    "QHBoxLayout", "QVBoxLayout", "QGridLayout", "QFormLayout",
    "QStackedLayout", "QBoxLayout",
})

# ── QML 可交互控件 ─────────────────────────────────────────────
QML_INTERACTIVE_TYPES: frozenset[str] = frozenset({
    # QtQuick.Controls 2
    "Button", "ToolButton", "RoundButton",
    "TextField", "TextArea", "TextInput",
    "ComboBox", "Tumbler", "SpinBox",
    "CheckBox", "RadioButton", "Switch", "DelayButton",
    "Slider", "RangeSlider", "Dial", "ScrollBar",
    "TabBar", "TabButton",
    "MenuBar", "MenuItem",
    "Calendar", "CalendarModel",
    "PageIndicator",
    "SwipeDelegate", "ItemDelegate", "CheckDelegate",
    "RadioDelegate", "SwitchDelegate",
    "TreeView", "TableView", "ListView", "GridView",
    "SelectionRectangle",
    # DTK QML
    "DButton", "DWarningButton", "DSuggestButton",
    "DSwitchButton", "DIconButton", "DFloatingButton",
    "DCommandLinkButton",
    "DTextField", "DComboBox",
    "DCheckBox", "DRadioButton", "DSwitch",
    "DSlider", "DSpinBox", "DTextArea",
    "DListView", "DTreeView", "DTableView",
    "DTabBar", "DTabButton",
    "DCalendarPicker", "DScrollBar",
    # DTK 扩展交互组件（dtkdeclarative，项目内无 .qml，需显式声明）
    "ActionButton", "IconButton", "FloatingButton", "WarningButton",
    "RecommandButton", "TitleBar", "WindowButton", "SearchEdit",
    "ButtonBox", "LineEdit", "DialogWindow",
})

# ── QML 装饰/容器 ──────────────────────────────────────────────
QML_DECORATIVE_TYPES: frozenset[str] = frozenset({
    "Rectangle", "Image", "BorderImage", "AnimatedImage",
    "Text", "Label",
    "Item", "QtObject",
    "Column", "Row", "Grid", "Flow", "Repeater",
    "StackLayout", "GridLayout", "RowLayout", "ColumnLayout",
    "Flickable", "MouseArea", "DropArea", "PinchArea",
    "AnimatedSprite", "SpriteSequence",
    "Canvas", "ShaderEffect", "ShaderEffectSource",
    "ScrollIndicator",
    "SplitView", "StackView",
    "HeaderView", "FooterView",
    "Window", "ApplicationWindow", "Dialog",
    "Popup", "Pane", "Page", "Drawer",
    # Menu/DMenu are QQuickPopup (not Item/Action) — Accessible cannot attach
    # to them, so they are never nameable. Only MenuItem children carry names.
    "Menu", "DMenu",
    "ToolTip", "ToolSeparator",
    "BusyIndicator", "ProgressBar",
    "GroupBox", "ScrollView",
    "DialogButtonBox",
    # DTK 装饰
    "DProgressBar", "DGroupBox", "DScrollView",
    "DDialog", "DPopup", "DDrawer", "DLabel", "DText",
    "DHeaderLine", "DShadowLine", "DFrame", "DWidget",
})

# ── QML 结构类型（跳过）─────────────────────────────────────────
QML_STRUCTURAL_TYPES: frozenset[str] = frozenset({
    "State", "Transition", "PropertyChanges", "Binding",
    "Connections", "Component", "Repeater", "Loader",
    "Timer", "FontLoader", "Shortcut", "Action", "ActionGroup",
})

# ── QML 类型名启发式（覆盖枚举无法穷举的自定义/第三方组件）──────────
# 仅用于"未知类型"（不在任何已知列表）。类型名以交互控件后缀结尾 → 交互。
# 非 UI 后缀优先排除（Animation/Model/Shadow 等），避免误报。
QML_INTERACTIVE_SUFFIXES: tuple[str, ...] = (
    "button", "combobox", "edit", "slider", "spinbox", "checkbox",
    "radiobutton", "switch", "tabbar", "tabbutton", "scrollbar",
    "searchbox", "picker", "delegate", "menu", "menuitem", "dialog",
    "listview", "treeview", "tableview", "gridview", "combo",
)
# 非 UI 后缀：即使含交互关键字也排除（动画/模型/阴影/状态等）
QML_NON_UI_SUFFIXES: tuple[str, ...] = (
    "animation", "model", "shadow", "separator", "handler", "states",
    "optimizer", "element", "effect", "transition", "state", "loader",
    "repeater", "timer", "metrics", "palette", "validator", "path",
    "positioner", "adapter", "helper", "manager", "controller",
)
# 装饰后缀（类型名以这些结尾 → 装饰）
QML_DECORATIVE_SUFFIXES: tuple[str, ...] = (
    "label", "text", "icon", "image", "progress", "tooltip", "notice",
    "panel", "titlebar", "header", "footer", "separator", "indicator",
    "bar", "view",
)


def is_qml_interactive_by_keyword(elem_type: str) -> bool:
    """未知类型启发式：类型名以交互后缀结尾且不以非 UI 后缀结尾 → 交互。"""
    t = elem_type.lower()
    if any(t.endswith(s) for s in QML_NON_UI_SUFFIXES):
        return False
    return any(t.endswith(s) for s in QML_INTERACTIVE_SUFFIXES)


def is_qml_decorative_by_keyword(elem_type: str) -> bool:
    """未知类型启发式：类型名以装饰后缀结尾且非交互 → 装饰。"""
    t = elem_type.lower()
    if is_qml_interactive_by_keyword(elem_type):
        return False
    if any(t.endswith(s) for s in QML_NON_UI_SUFFIXES):
        return False
    return any(t.endswith(s) for s in QML_DECORATIVE_SUFFIXES)


# ── 辅助函数 ──────────────────────────────────────────────────

def is_interactive(type_name: str) -> bool:
    base = type_name.replace(" *", "").replace("&", "").split("<")[0].strip()
    return base in INTERACTIVE_CLASSES


def is_decorative(type_name: str) -> bool:
    base = type_name.replace(" *", "").replace("&", "").split("<")[0].strip()
    return base in DECORATIVE_CLASSES


def is_layout(type_name: str) -> bool:
    base = type_name.replace(" *", "").replace("&", "").split("<")[0].strip()
    return base in LAYOUT_CLASSES


def is_non_widget_interactive(type_name: str) -> bool:
    base = type_name.replace(" *", "").replace("&", "").split("<")[0].strip()
    return base in NON_WIDGET_INTERACTIVE


def is_qml_interactive(elem_type: str) -> bool:
    return elem_type in QML_INTERACTIVE_TYPES


def is_qml_decorative(elem_type: str) -> bool:
    return elem_type in QML_DECORATIVE_TYPES


def is_qml_structural(elem_type: str) -> bool:
    return elem_type in QML_STRUCTURAL_TYPES