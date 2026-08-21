#!/usr/bin/env python3
"""AT-SPI QML 源码扫描器 — 独立版。

扫描 .qml 文件中的可交互元素，统计：
- 元素 A（所有可交互 QML 元素）
- 元素 B（已有 Accessible.name 的元素）
- 覆盖率 = |B| / |A|

输出：qml_gaps.yaml + qml_ok.yaml
"""
from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("coverage_scan_qml")

# ── QML 分类常量（内联，无外部依赖）─────────────────────────────
_QML_INTERACTIVE_TYPES: frozenset[str] = frozenset({
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

_QML_DECORATIVE_TYPES: frozenset[str] = frozenset({
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
    "DProgressBar", "DGroupBox", "DScrollView",
    "DDialog", "DPopup", "DDrawer", "DLabel", "DText",
    "DHeaderLine", "DShadowLine", "DFrame", "DWidget",
})

_QML_STRUCTURAL_TYPES: frozenset[str] = frozenset({
    "State", "Transition", "PropertyChanges", "Binding",
    "Connections", "Component", "Repeater", "Loader",
    "Timer", "FontLoader", "Shortcut", "Action", "ActionGroup",
    "Behavior", "AnchorChanges", "ParentChange",
    "Gradient", "GradientStop", "ListModel", "XmlListModel",
    "Instantiator",
})


def _is_interactive_type(elem_type: str) -> bool:
    return elem_type in _QML_INTERACTIVE_TYPES


def _is_decorative_type(elem_type: str) -> bool:
    return elem_type in _QML_DECORATIVE_TYPES


def _is_structural_type(elem_type: str) -> bool:
    return elem_type in _QML_STRUCTURAL_TYPES


def _is_custom_component(elem_type: str, src_dir: str) -> bool:
    """Check if a type name corresponds to a custom QML component file."""
    for root in [Path(src_dir)]:
        for p in root.rglob(f"{elem_type}.qml"):
            return True

# ── QML type → AT-SPI role mapping ─────────────────────────────
_QML_TO_ROLE: dict[str, str] = {
    "Button": "push button", "ToolButton": "push button",
    "RoundButton": "push button",
    "DButton": "push button", "DWarningButton": "push button",
    "DSuggestButton": "push button", "DSwitchButton": "push button",
    "DIconButton": "push button", "DFloatingButton": "push button",
    "DCommandLinkButton": "push button",
    "TextField": "text", "TextArea": "text", "TextInput": "text",
    "DTextField": "text", "DTextArea": "text",
    "ComboBox": "combo box", "DComboBox": "combo box",
    "SpinBox": "spin box", "DSpinBox": "spin box",
    "Tumbler": "spin box",
    "CheckBox": "check box", "DCheckBox": "check box",
    "RadioButton": "radio button", "DRadioButton": "radio button",
    "Switch": "toggle button", "DSwitch": "toggle button",
    "DelayButton": "push button",
    "Slider": "slider", "DSlider": "slider",
    "RangeSlider": "slider", "Dial": "dial",
    "ScrollBar": "scroll bar", "DScrollBar": "scroll bar",
    "TabBar": "page tab list", "TabButton": "page tab",
    "DTabBar": "page tab list", "DTabButton": "page tab",
    "MenuBar": "menu bar", "DMenuBar": "menu bar",
    "Menu": "menu", "DMenu": "menu",
    "MenuItem": "menu item", "DMenuItem": "menu item",
    "TreeView": "tree", "DTreeView": "tree",
    "TableView": "table", "DTableView": "table",
    "ListView": "list", "DListView": "list",
    "GridView": "list",
    "Calendar": "calendar", "DCalendarPicker": "calendar",
    "PageIndicator": "page tab list",
    "SwipeDelegate": "push button", "ItemDelegate": "push button",
    "CheckDelegate": "check box", "RadioDelegate": "radio button",
    "SwitchDelegate": "toggle button",
    "SelectionRectangle": "panel",
}


def _map_qml_role(elem_type: str) -> str:
    return _QML_TO_ROLE.get(elem_type, "")


# ── 数据结构 ──────────────────────────────────────────────────
@dataclass
class QmlElement:
    element_type: str = ""
    id: str = ""
    accessible_name: str = ""
    accessible_role: str = ""
    has_accessible_name: bool = False
    has_accessible_role: bool = False
    has_accessible_ignored: bool = False
    source_file: str = ""
    parent_type: str = ""
    line: int = 0
    suggested_name: str = ""


@dataclass
class QmlScanResult:
    source_dir: str
    total_files: int = 0
    ok_elements: list[QmlElement] = field(default_factory=list)
    gap_elements: list[QmlElement] = field(default_factory=list)


# ── Tokenizer ──────────────────────────────────────────────────
def _tokenize_qml(content: str) -> list[tuple[str, str, int, int]]:
    """Tokenize QML source into (kind, value, line, col) tuples."""
    tokens: list[tuple[str, str, int, int]] = []
    i = 0
    lines = content.splitlines(keepends=True)
    line_num = 1
    col_num = 1
    for line in lines:
        col_num = 1
        j = 0
        while j < len(line):
            ch = line[j]
            if ch.isspace():
                j += 1
                col_num += 1
                continue
            if ch == '"':
                start = j + 1
                j += 1
                while j < len(line) and line[j] != '"':
                    if line[j] == '\\':
                        j += 1
                    j += 1
                val = line[start:j]
                if j < len(line):
                    j += 1
                tokens.append(("string", val, line_num, col_num))
                col_num = j - start + 1
                continue
            if ch == '/':
                if j + 1 < len(line) and line[j + 1] == '/':
                    break
                if j + 1 < len(line) and line[j + 1] == '*':
                    j += 2
                    col_num += 2
                    while j < len(line):
                        if line[j] == '*' and j + 1 < len(line) and line[j + 1] == '/':
                            j += 2
                            col_num += 2
                            break
                        j += 1
                        col_num += 1
                    continue
            if ch in '{}[]():;,':
                tokens.append(("punct", ch, line_num, col_num))
                j += 1
                col_num += 1
                continue
            # identifier or keyword
            if ch.isalpha() or ch == '_' or ch == '.':
                start = j
                while j < len(line) and (line[j].isalnum() or line[j] in '_.'):
                    j += 1
                val = line[start:j]
                tokens.append(("ident", val, line_num, col_num))
                col_num += j - start
                continue
            # number
            if ch.isdigit() or (ch == '-' and j + 1 < len(line) and line[j + 1].isdigit()):
                start = j
                j += 1
                while j < len(line) and (line[j].isalnum() or line[j] in '.xX'):
                    j += 1
                tokens.append(("number", line[start:j], line_num, col_num))
                col_num += j - start
                continue
            j += 1
            col_num += 1
        line_num += 1
    return tokens


# ── 值提取 ──────────────────────────────────────────────────
def _collect_value(tokens: list[tuple[str, str, int, int]], start: int) -> tuple[list[tuple], int]:
    out: list[tuple] = []
    j = start
    depth = 0
    while j < len(tokens):
        kind, val, ln, col = tokens[j]
        if kind == "punct" and val in ")}]":
            if depth == 0:
                break
            depth -= 1
            out.append(tokens[j])
            j += 1
            continue
        if kind == "punct" and val in "{([":
            depth += 1
        if kind == "punct" and val in ",;":
            if depth == 0:
                break
        out.append(tokens[j])
        j += 1
    return out, j


def _extract_value(value_tokens: list[tuple[str, str, int, int]]) -> str:
    parts: list[str] = []
    for kind, val, ln, col in value_tokens:
        if kind == "string":
            parts.append(val)
        elif kind == "ident":
            parts.append(val)
        elif kind == "number":
            parts.append(val)
    return "".join(parts)


# ── 名称生成 ──────────────────────────────────────────────────
def _to_pascal_case(text: str) -> str:
    import re
    words = re.split(r'[_\s\-]+', text)
    return "".join(w.capitalize() for w in words if w)


def _strip_type_prefix(elem_type: str) -> str:
    if elem_type.startswith("D") and len(elem_type) > 1 and elem_type[1].isupper():
        return elem_type[1:]
    if elem_type.startswith("Q") and len(elem_type) > 1 and elem_type[1].isupper():
        return elem_type[1:]
    return elem_type


def _generate_qml_name(elem: QmlElement, existing_names: set[str]) -> str:
    name = ""
    if elem.id:
        name = _to_pascal_case(elem.id)
    if not name and elem.accessible_name:
        name = _to_pascal_case(elem.accessible_name)
    if not name:
        name = _strip_type_prefix(elem.element_type)
    if not name:
        name = "Unnamed"
    # dedup
    base = name
    counter = 2
    while name in existing_names:
        name = f"{base}_{counter}"
        counter += 1
    existing_names.add(name)
    return name


# ── QML 解析器 ──────────────────────────────────────────────
@dataclass
class _Scope:
    kind: str = ""  # "element" | "js"
    elem_type: str = ""
    elem_id: str = ""
    accessible_name: str = ""
    accessible_role: str = ""
    has_acc_name: bool = False
    has_acc_role: bool = False
    has_acc_ignored: bool = False
    line: int = 0
    parent: "_Scope | None" = None


def _nearest_element(scope: _Scope | None) -> _Scope | None:
    while scope:
        if scope.kind == "element":
            return scope
        scope = scope.parent
    return None


def _nearest_named_ancestor(scope: _Scope, src_dir: str) -> str:
    s = scope.parent
    while s:
        if s.kind == "element":
            if _is_interactive_type(s.elem_type) or _is_custom_component(s.elem_type, src_dir):
                return s.elem_type
        s = s.parent
    return ""

def _finalize_scope(scope: _Scope, rel_path: str, src_dir: str) -> QmlElement | None:
    if scope.kind != "element":
        return None
    if scope.has_acc_ignored:
        return None  # Accessible.ignored: true → excluded from AT-SPI
    elem_type = scope.elem_type
    if _is_structural_type(elem_type):
        return None
    if _is_decorative_type(elem_type) and not scope.has_acc_name:
        return None
    parent_type = _nearest_named_ancestor(scope, src_dir)
    elem = QmlElement(
        element_type=elem_type, id=scope.elem_id,
        accessible_name=scope.accessible_name,
        accessible_role=scope.accessible_role,
        has_accessible_name=scope.has_acc_name,
        has_accessible_role=scope.has_acc_role,
        has_accessible_ignored=scope.has_acc_ignored,
        source_file=rel_path, parent_type=parent_type,
        line=scope.line,
    )
    return elem


def _parse_qml(content: str, rel_path: str, src_dir: str) -> list[QmlElement]:
    tokens = _tokenize_qml(content)
    results: list[QmlElement] = []
    root_scope = _Scope(kind="element", elem_type="root", line=0)
    scope_stack: list[_Scope] = [root_scope]
    i = 0
    while i < len(tokens):
        kind, val, ln, col = tokens[i]
        if kind == "ident" and val[0].isupper():
            # Element declaration
            elem_type = val
            elem_id = ""
            acc_name = ""
            acc_role = ""
            has_acc_name = False
            has_acc_role = False
            i += 1
            # skip properties until {
            while i < len(tokens):
                k2, v2, ln2, col2 = tokens[i]
                if k2 == "punct" and v2 == "{":
                    break
                if k2 == "ident" and v2 == "id":
                    i += 1
                    if i < len(tokens) and tokens[i][0] == "punct" and tokens[i][1] == ":":
                        i += 1
                        if i < len(tokens) and tokens[i][0] == "ident":
                            elem_id = tokens[i][1]
                            i += 1
                    continue
                i += 1
            if i < len(tokens) and tokens[i][1] == "{":
                new_scope = _Scope(kind="element", elem_type=elem_type,
                                   elem_id=elem_id, line=ln,
                                   parent=scope_stack[-1])
                scope_stack.append(new_scope)
                i += 1
                # Parse inside braces
                depth = 1
                while i < len(tokens) and depth > 0:
                    k3, v3, ln3, col3 = tokens[i]
                    if k3 == "punct" and v3 == "{":
                        depth += 1
                        # Nested element
                        if i + 1 < len(tokens) and tokens[i + 1][0] == "ident" and tokens[i + 1][1][0].isupper():
                            pass  # will be caught by next iteration
                        i += 1
                        continue
                    if k3 == "punct" and v3 == "}":
                        depth -= 1
                        if depth == 0:
                            elem = _finalize_scope(scope_stack.pop(), rel_path, src_dir)
                            if elem:
                                results.append(elem)
                        i += 1
                        continue
                    # Accessible.name / Accessible.role
                    if k3 == "ident" and v3 == "Accessible":
                        if i + 2 < len(tokens) and tokens[i + 1][0] == "punct" and tokens[i + 1][1] == ".":
                            prop = tokens[i + 2][1] if tokens[i + 2][0] == "ident" else ""
                            if prop == "name":
                                i += 3
                                if i < len(tokens) and tokens[i][0] == "punct" and tokens[i][1] == ":":
                                    i += 1
                                    val_tokens, i = _collect_value(tokens, i)
                                    acc_name = _extract_value(val_tokens)
                                    has_acc_name = True
                                    scope_stack[-1].accessible_name = acc_name
                                    scope_stack[-1].has_acc_name = True
                                continue
                            elif prop == "role":
                                i += 3
                                if i < len(tokens) and tokens[i][0] == "punct" and tokens[i][1] == ":":
                                    i += 1
                                    val_tokens, i = _collect_value(tokens, i)
                                    acc_role = _extract_value(val_tokens)
                                    has_acc_role = True
                                    scope_stack[-1].accessible_role = acc_role
                                    scope_stack[-1].has_acc_role = True
                                continue
                            elif prop == "ignored":
                                i += 3
                                if i < len(tokens) and tokens[i][0] == "punct" and tokens[i][1] == ":":
                                    i += 1
                                    val_tokens, i = _collect_value(tokens, i)
                                    val_str = _extract_value(val_tokens)
                                    if val_str.lower() in ("true", "1"):
                                        scope_stack[-1].has_acc_ignored = True
                                continue
                    # Accessible { name: ... role: ... } block
                    if k3 == "ident" and v3 == "Accessible" and i + 1 < len(tokens) and tokens[i + 1][1] == "{":
                        i += 2
                        block_depth = 1
                        while i < len(tokens) and block_depth > 0:
                            k4, v4, ln4, col4 = tokens[i]
                            if k4 == "punct" and v4 == "{":
                                block_depth += 1
                                i += 1
                                continue
                            if k4 == "punct" and v4 == "}":
                                block_depth -= 1
                                i += 1
                                continue
                            if k4 == "ident" and v4 in ("name", "role", "ignored"):
                                prop = v4
                                i += 1
                                if i < len(tokens) and tokens[i][0] == "punct" and tokens[i][1] == ":":
                                    i += 1
                                    val_tokens, i = _collect_value(tokens, i)
                                    val_str = _extract_value(val_tokens)
                                    if prop == "name":
                                        scope_stack[-1].accessible_name = val_str
                                        scope_stack[-1].has_acc_name = True
                                    elif prop == "role":
                                        scope_stack[-1].accessible_role = val_str
                                        scope_stack[-1].has_acc_role = True
                                    elif prop == "ignored" and val_str.lower() in ("true", "1"):
                                        scope_stack[-1].has_acc_ignored = True
                                continue
                            i += 1
                        continue
                    i += 1
                continue
        i += 1
    return results


def _scan_qml_file(file_path: str, src_dir: str) -> tuple[str, list[QmlElement]]:
    with open(file_path, encoding="utf-8") as f:
        content = f.read()
    rel_path = str(Path(file_path).relative_to(src_dir))
    elements = _parse_qml(content, rel_path, src_dir)
    return rel_path, elements


# ── 主扫描 ──────────────────────────────────────────────────
def scan_qml_source(src_dir: str, output_dir: str = ".") -> QmlScanResult:
    root = Path(src_dir)
    if not root.is_dir():
        logger.error("Source directory not found: %s", src_dir)
        return QmlScanResult(source_dir=src_dir)

    qml_files = sorted(root.rglob("*.qml"))
    if not qml_files:
        logger.warning("No .qml files found in %s", src_dir)
        return QmlScanResult(source_dir=src_dir)

    all_ok: list[QmlElement] = []
    all_gaps: list[QmlElement] = []
    existing_names: set[str] = set()

    for fp in qml_files:
        rel_path, elements = _scan_qml_file(str(fp), src_dir)
        for elem in elements:
            if _is_interactive_type(elem.element_type) or _is_custom_component(elem.element_type, src_dir):
                if elem.has_accessible_name:
                    all_ok.append(elem)
                    if elem.accessible_name:
                        existing_names.add(elem.accessible_name)
                else:
                    elem.suggested_name = _generate_qml_name(elem, existing_names)
                    all_gaps.append(elem)
            elif _is_decorative_type(elem.element_type):
                if elem.has_accessible_name:
                    all_ok.append(elem)
                    if elem.accessible_name:
                        existing_names.add(elem.accessible_name)

    result = QmlScanResult(
        source_dir=src_dir, total_files=len(qml_files),
        ok_elements=all_ok, gap_elements=all_gaps,
    )
    _write_outputs(result, output_dir)
    return result


def _element_to_dict(e: QmlElement) -> dict[str, Any]:
    return {
        "element_type": e.element_type, "id": e.id,
        "accessible_name": e.accessible_name,
        "accessible_role": e.accessible_role,
        "has_accessible_name": e.has_accessible_name,
        "has_accessible_role": e.has_accessible_role,
        "has_accessible_ignored": e.has_accessible_ignored,
        "source_file": e.source_file, "parent_type": e.parent_type,
        "line": e.line, "suggested_name": e.suggested_name,
        "role": _map_qml_role(e.element_type),
    }


def _write_outputs(result: QmlScanResult, output_dir: str) -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    import yaml

    # qml_ok.yaml
    ok_data = {
        "version": "1.0",
        "source_dir": result.source_dir,
        "total_files": result.total_files,
        "widgets": [_element_to_dict(e) for e in result.ok_elements],
    }
    ok_path = out / "qml_ok.yaml"
    with open(ok_path, "w", encoding="utf-8") as f:
        yaml.dump(ok_data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    logger.info("Written %s (%d ok)", ok_path, len(result.ok_elements))

    # qml_gaps.yaml
    gaps_data = {
        "version": "1.0",
        "source_dir": result.source_dir,
        "gaps": [_element_to_dict(e) for e in result.gap_elements],
    }
    gaps_path = out / "qml_gaps.yaml"
    with open(gaps_path, "w", encoding="utf-8") as f:
        yaml.dump(gaps_data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    logger.info("Written %s (%d gaps)", gaps_path, len(result.gap_elements))

    # summary
    total = len(result.ok_elements) + len(result.gap_elements)
    ok_count = len(result.ok_elements)
    coverage = (ok_count / total * 100) if total else 0.0
    logger.info("QML Coverage: %d/%d = %.1f%% (%d gaps)", ok_count, total, coverage, len(result.gap_elements))


# ── CLI ──────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="AT-SPI QML coverage scanner (standalone)")
    parser.add_argument("--src", required=True, help="Source directory")
    parser.add_argument("--output", "-o", default=".", help="Output directory")
    args = parser.parse_args()
    result = scan_qml_source(src_dir=args.src, output_dir=args.output)
    return 0 if result.total_files > 0 else 1


if __name__ == "__main__":
    sys.exit(main())