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
    "DKeySequenceEdit",
    # Qt 输入
    "QLineEdit", "QTextEdit", "QComboBox", "QCheckBox", "QRadioButton",
    "QSlider", "QSpinBox", "QDoubleSpinBox", "QKeySequenceEdit",
    # DTK 列表/树/表
    "DListView", "DTreeView", "DTabBar",
    # Qt 列表/树/表
    "QListWidget", "QTreeWidget", "QTableWidget",
    "QListView", "QTreeView", "QTableView",
    "QTabBar", "QScrollBar",
    # 菜单
    "QMenu", "QMenuBar", "DMenu", "DMenuItem", "DMenuBar",
    # 动作/快捷键（仅 objectName）
    "QAction", "QActionGroup", "QShortcut", "QButtonGroup",
    "DAction",
    # 其他
    "QCalendarWidget",
})

# ── C++ 非 Widget 可交互（只有 setObjectName，没有 setAccessibleName）──
NON_WIDGET_INTERACTIVE: frozenset[str] = frozenset({
    "QAction", "QActionGroup", "QShortcut", "QButtonGroup", "DAction",
})

# ── C++ 装饰/容器（不纳入覆盖率统计）─────────────────────────────
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
    "MenuBar", "Menu", "MenuItem",
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
    "DMenu", "DMenuItem", "DMenuBar",
    "DCalendarPicker", "DScrollBar",
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
    "Behavior", "AnchorChanges", "ParentChange",
    "Gradient", "GradientStop", "ListModel", "XmlListModel",
    "Instantiator",
})


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