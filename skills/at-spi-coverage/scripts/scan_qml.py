#!/usr/bin/env python3
"""QML AT-SPI accessibility scanner.

Scans .qml source files for interactive QML elements that lack
Accessible.name declarations. Uses a lightweight tokenizer + scope-stack
parser — no Qt/QML runtime or libclang dependency.

Output schema (aligned with scan_gaps.py for pipeline compatibility):
    qml_ok.yaml     — QML elements with Accessible.name set
    qml_gaps.yaml   — QML elements missing Accessible.name (with suggested_name)
    qml_report.json — summary statistics

Usage:
    python3 scan_qml.py --src <source_dir> --output <output_dir>
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("scan_qml")

# ---------------------------------------------------------------------------
# QML type classification
#
# interactive  — real controls that MUST expose an AT-SPI name
# decorative   — containers/visuals that only appear in output if explicitly
#                given an Accessible.name
# structural   — QML plumbing (states, bindings, components) that is never
#                exposed to AT-SPI; skipped entirely
# ---------------------------------------------------------------------------

_QML_INTERACTIVE_TYPES: frozenset[str] = frozenset({
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
    # DTK QML types
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
    # DTK decorative
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

# ---------------------------------------------------------------------------
# QML type → AT-SPI role mapping
# ---------------------------------------------------------------------------

_QML_TO_ROLE: dict[str, str] = {
    "Button": "push button",
    "ToolButton": "push button",
    "RoundButton": "push button",
    "DButton": "push button",
    "DWarningButton": "push button",
    "DSuggestButton": "push button",
    "DSwitchButton": "push button",
    "DIconButton": "push button",
    "DFloatingButton": "push button",
    "DCommandLinkButton": "push button",
    "TextField": "text",
    "TextArea": "text",
    "TextInput": "text",
    "DTextField": "text",
    "DTextArea": "text",
    "ComboBox": "combo box",
    "DComboBox": "combo box",
    "SpinBox": "spin box",
    "DSpinBox": "spin box",
    "Tumbler": "spin box",
    "CheckBox": "check box",
    "DCheckBox": "check box",
    "RadioButton": "radio button",
    "DRadioButton": "radio button",
    "Switch": "toggle button",
    "DSwitch": "toggle button",
    "DelayButton": "push button",
    "Slider": "slider",
    "DSlider": "slider",
    "RangeSlider": "slider",
    "Dial": "dial",
    "ScrollBar": "scroll bar",
    "DScrollBar": "scroll bar",
    "TabBar": "page tab list",
    "TabButton": "page tab",
    "DTabBar": "page tab list",
    "DTabButton": "page tab",
    "MenuBar": "menu bar",
    "DMenuBar": "menu bar",
    "Menu": "menu",
    "DMenu": "menu",
    "MenuItem": "menu item",
    "DMenuItem": "menu item",
    "TreeView": "tree",
    "DTreeView": "tree",
    "TableView": "table",
    "DTableView": "table",
    "ListView": "list",
    "DListView": "list",
    "GridView": "list",
    "Calendar": "calendar",
    "DCalendarPicker": "calendar",
    "PageIndicator": "page tab list",
    "SwipeDelegate": "push button",
    "ItemDelegate": "push button",
    "CheckDelegate": "check box",
    "RadioDelegate": "radio button",
    "SwitchDelegate": "toggle button",
    "SelectionRectangle": "panel",
}

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class QmlElement:
    """A QML element found in source code."""
    element_type: str = ""
    id_name: str = ""
    source_file: str = ""
    line: int = 0
    column: int = 0
    has_accessible_name: bool = False
    has_accessible_role: bool = False
    has_accessible_ignored: bool = False
    accessible_name: str = ""
    accessible_role: str = ""
    parent_type: str = ""
    object_name: str = ""
    text_property: str = ""
    role: str = ""
    suggested_name: str = ""


@dataclass
class QmlScanResult:
    source_dir: str
    total_files: int = 0
    ok_elements: list[QmlElement] = field(default_factory=list)
    gap_elements: list[QmlElement] = field(default_factory=list)


@dataclass
class _Scope:
    """A brace-delimited scope in QML: an object declaration or a JS block."""
    type_name: str = ""
    is_element: bool = False
    is_attached_accessible: bool = False

    decl_line: int = 0
    decl_col: int = 0
    props: dict[str, str] = field(default_factory=dict)
    accessible: dict[str, str] = field(default_factory=dict)
    parent: "_Scope | None" = None


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------


def _tokenize_qml(content: str) -> list[tuple[str, str, int, int]]:
    """Tokenize QML source into (kind, value, line, col) tuples.

    Kinds: ID, NUMBER, STRING, NEWLINE, PUNCT (value is the single char).
    """
    tokens: list[tuple[str, str, int, int]] = []
    i = 0
    n = len(content)
    line = 1
    col = 1
    while i < n:
        ch = content[i]
        if ch == "\n":
            tokens.append(("NEWLINE", "\n", line, col))
            line += 1
            col = 1
            i += 1
            continue
        if ch in " \t\r":
            col += 1
            i += 1
            continue
        if ch == "/" and i + 1 < n and content[i + 1] == "/":
            while i < n and content[i] != "\n":
                i += 1
                col += 1
            continue
        if ch == "/" and i + 1 < n and content[i + 1] == "*":
            while i + 1 < n and not (content[i] == "*" and content[i + 1] == "/"):
                if content[i] == "\n":
                    line += 1
                    col = 1
                else:
                    col += 1
                i += 1
            i += 2
            col += 2
            continue
        if ch in ('"', "'"):
            sline, scol = line, col
            quote = ch
            i += 1
            col += 1
            buf: list[str] = []
            while i < n and content[i] != quote:
                if content[i] == "\\" and i + 1 < n:
                    buf.append(content[i])
                    buf.append(content[i + 1])
                    i += 2
                    col += 2
                    continue
                if content[i] == "\n":
                    line += 1
                    col = 1
                else:
                    col += 1
                buf.append(content[i])
                i += 1
            if i < n:  # closing quote
                i += 1
                col += 1
            tokens.append(("STRING", "".join(buf), sline, scol))
            continue
        if ch.isalnum() or ch == "_":
            start = i
            sline, scol = line, col
            while i < n and (content[i].isalnum() or content[i] == "_"):
                i += 1
                col += 1
            tok = content[start:i]
            kind = "NUMBER" if tok.isdigit() else "ID"
            tokens.append((kind, tok, sline, scol))
            continue
        tokens.append(("PUNCT", ch, line, col))
        i += 1
        col += 1
    return tokens


# ---------------------------------------------------------------------------
# Type classification helpers
# ---------------------------------------------------------------------------


def _is_interactive_type(elem_type: str) -> bool:
    return elem_type in _QML_INTERACTIVE_TYPES


def _is_decorative_type(elem_type: str) -> bool:
    return elem_type in _QML_DECORATIVE_TYPES


def _is_structural_type(elem_type: str) -> bool:
    return elem_type in _QML_STRUCTURAL_TYPES


def _map_qml_role(elem_type: str) -> str:
    return _QML_TO_ROLE.get(elem_type, "")


def _is_custom_component(elem_type: str, src_dir: str) -> bool:
    """Check if a type name corresponds to a custom QML component file."""
    if len(elem_type) > 1 and elem_type[0].isupper():
        if elem_type[0] == "Q" and elem_type[1].isupper():
            return False
        if elem_type[0] == "D" and elem_type[1].isupper():
            return False
    src = Path(src_dir)
    for _ in src.rglob(f"{elem_type}.qml"):
        return True
    return False



def _is_element_complete(e: QmlElement, src_dir: str) -> bool:
    """Check if element has complete AT-SPI exposure.

    - Standard Qt Quick Controls 2 types and DTK QML types have C++ backends
      that auto-set Accessible.role — only Accessible.name is required.
    - Custom components (user-defined .qml files) need BOTH name AND role.
    - Decorative elements only need Accessible.name.
    """
    if not e.has_accessible_name:
        return False
    # Standard interactive types (Qt Quick Controls 2 + DTK) auto-infer role
    if _is_interactive_type(e.element_type):
        return True
    # Custom components need explicit role
    if _is_custom_component(e.element_type, src_dir):
        return e.has_accessible_role
    return True  # decorative — name is sufficient

# ---------------------------------------------------------------------------
# Value extraction
# ---------------------------------------------------------------------------


def _collect_value(
    tokens: list[tuple[str, str, int, int]], start: int,
) -> tuple[list[tuple[str, str, int, int]], int]:
    """Collect tokens of a property value expression until a terminator.

    Stops at NEWLINE, `;`, `}`, `]`, `,`, `(`, `{`, `[` at depth 0.
    Returns (value_tokens, next_index).
    """
    depth = 0
    j = start
    out: list[tuple[str, str, int, int]] = []
    while j < len(tokens):
        k, v, _, _ = tokens[j]
        if depth == 0 and (
            k == "NEWLINE" or (k == "PUNCT" and v in (";", "}", "]", ",", "{", "["))
        ):
            break
        if k == "PUNCT" and v in ("(", "[", "{"):
            depth += 1
        elif k == "PUNCT" and v in (")", "]", "}"):
            depth -= 1
        out.append(tokens[j])
        j += 1
    return out, j


def _extract_value(value_tokens: list[tuple[str, str, int, int]]) -> str:
    """Extract a scalar display value from value tokens.

    Returns the first string literal's inner text if present, else the
    concatenated ID/NUMBER chain (dotted enums like Accessible.Button).
    """
    for k, v, _, _ in value_tokens:
        if k == "STRING":
            return v
    parts: list[str] = []
    for k, v, _, _ in value_tokens:
        if k in ("ID", "NUMBER"):
            parts.append(v)
        elif k == "PUNCT" and v == "." and parts:
            parts[-1] += "."
    return "".join(parts)


# ---------------------------------------------------------------------------
# Name generation for QML elements
# ---------------------------------------------------------------------------


def _to_pascal_case(text: str) -> str:
    """Convert arbitrary text to PascalCase."""
    text = re.sub(r"[^a-zA-Z0-9]", " ", text)
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    words = text.split()
    return "".join(w.capitalize() for w in words if w)


def _strip_type_prefix(elem_type: str) -> str:
    """Strip D or Q prefix from a type name for cleaner naming."""
    if elem_type.startswith("D") and len(elem_type) > 1 and elem_type[1].isupper():
        return elem_type[1:]
    if elem_type.startswith("Q") and len(elem_type) > 1 and elem_type[1].isupper():
        return elem_type[1:]
    return elem_type


def _generate_qml_name(elem: QmlElement, existing_names: set[str]) -> str:
    """Generate a unique PascalCase AT-SPI name for a QML element.

    Priority: id → text → objectName → parent_type + type → file_stem + type → role.
    """
    name: str | None = None

    if elem.id_name:
        candidate = _to_pascal_case(elem.id_name)
        if candidate:
            name = candidate

    if not name and elem.text_property:
        candidate = _to_pascal_case(elem.text_property)
        if candidate:
            name = candidate

    if not name and elem.object_name:
        candidate = _to_pascal_case(elem.object_name)
        if candidate:
            name = candidate

    if not name and elem.parent_type:
        parent_part = _to_pascal_case(elem.parent_type)
        base_type = _strip_type_prefix(elem.element_type)
        if parent_part:
            name = f"{parent_part}_{base_type}"

    if not name:
        file_stem = Path(elem.source_file).stem
        file_part = _to_pascal_case(file_stem)
        base_type = _strip_type_prefix(elem.element_type)
        name = f"{file_part}_{base_type}"

    if not name:
        role = elem.role or "widget"
        role_pascal = _to_pascal_case(role)
        name = f"Unnamed{role_pascal}"

    # Ensure uniqueness
    if name in existing_names:
        counter = 2
        while f"{name}_{counter}" in existing_names:
            counter += 1
        name = f"{name}_{counter}"

    # Truncate to 64 chars, re-check uniqueness
    if len(name) > 64:
        name = name[:64]
        if name in existing_names:
            counter = 2
            while f"{name}_{counter}" in existing_names:
                counter += 1
            name = f"{name}_{counter}"

    return name


# ---------------------------------------------------------------------------
# QML parser (tokenizer + scope stack)
# ---------------------------------------------------------------------------


def _nearest_element(scope: "_Scope | None") -> "_Scope | None":
    """Nearest scope that is a declared QML object (element), inclusive."""
    cur = scope
    while cur is not None:
        if cur.is_element:
            return cur
        cur = cur.parent
    return None


def _nearest_named_ancestor(scope: "_Scope", src_dir: str) -> str:
    """Nearest ancestor element type that is interactive/structural/custom.

    Skips decorative containers (layouts, Item, Rectangle) so names like
    GroupBox_Button win over RowLayout_Button.
    """
    p = scope.parent
    while p is not None:
        if p.is_element and p.type_name not in ("Accessible", ""):
            t = p.type_name
            if (_is_interactive_type(t) or _is_structural_type(t)
                    or _is_custom_component(t, src_dir)
                    or t in ("GroupBox", "DGroupBox", "Dialog", "DDialog",
                             "TabBar", "DTabBar", "ApplicationWindow", "Window")):
                return t
        p = p.parent
    return ""


def _finalize_scope(scope: "_Scope", rel_path: str, src_dir: str) -> QmlElement | None:
    """Build a QmlElement from a completed scope, or None if it must be skipped."""
    t = scope.type_name
    if not scope.is_element or t == "Accessible":
        return None
    if _is_structural_type(t):
        return None

    is_interactive = _is_interactive_type(t)
    is_decorative = _is_decorative_type(t)
    if not is_interactive and not is_decorative:
        if not _is_custom_component(t, src_dir):
            return None  # unknown type — not a UI element
        is_interactive = True  # custom component → treat as interactive

    acc_ignored = scope.accessible.get("ignored", "").lower() in ("true", "1")
    if acc_ignored:
        return None  # explicitly excluded from accessibility

    has_name = bool(scope.accessible.get("name"))
    if is_decorative and not has_name:
        return None

    # text_property: prefer text, then title, placeholderText, label
    text_prop = (
        scope.props.get("text")
        or scope.props.get("title")
        or scope.props.get("placeholderText")
        or scope.props.get("label")
        or ""
    )

    elem = QmlElement(
        element_type=t,
        id_name=scope.props.get("id", ""),
        object_name=scope.props.get("objectName", ""),
        text_property=text_prop,
        source_file=rel_path,
        line=scope.decl_line,
        column=scope.decl_col,
        has_accessible_name=has_name,
        has_accessible_role=bool(scope.accessible.get("role")),
        has_accessible_ignored=acc_ignored,
        accessible_name=scope.accessible.get("name", ""),
        accessible_role=scope.accessible.get("role", ""),
        parent_type=_nearest_named_ancestor(scope, src_dir),
        role=_map_qml_role(t),
    )
    return elem


def _parse_qml(content: str, rel_path: str, src_dir: str) -> list[QmlElement]:
    """Parse QML content into classified elements (in source order)."""
    tokens = _tokenize_qml(content)
    root = _Scope()
    stack: list[_Scope] = [root]
    results: list[QmlElement] = []
    n = len(tokens)
    i = 0

    while i < n:
        kind, val, line, col = tokens[i]

        if kind == "ID":
            name = val

            # property declaration: property [modifiers] <type> <name> : <value>
            # Skip the whole declaration without attaching anything.
            if name == "property":
                j = i + 1
                while j < n and tokens[j][0] != ":" and tokens[j][0] != "NEWLINE":
                    j += 1
                if j < n and tokens[j][0] == ":":
                    _, i = _collect_value(tokens, j + 1)
                else:
                    i = j
                continue

            # Dotted chain: A.B.C : value  (e.g. Accessible.name, Layout.fillWidth)
            chain = [name]
            j = i + 1
            while (
                j + 1 < n
                and tokens[j][0] == "PUNCT"
                and tokens[j][1] == "."
                and tokens[j + 1][0] == "ID"
            ):
                chain.append(tokens[j + 1][1])
                j += 2

            if j < n and tokens[j][0] == "PUNCT" and tokens[j][1] == ":":
                value_tokens, ni = _collect_value(tokens, j + 1)
                value_text = _extract_value(value_tokens)
                scope = stack[-1]

                if scope.is_attached_accessible:
                    # Inside Accessible { name: ... } — forward to parent element
                    target = _nearest_element(scope.parent)
                    if target is not None:
                        target.accessible[chain[0]] = value_text
                elif chain[0] == "Accessible":
                    # Dotted form Accessible.name: "..." — attach to current element
                    target = _nearest_element(scope)
                    if target is not None:
                        key = ".".join(chain[1:]) if len(chain) > 1 else "name"
                        target.accessible[key] = value_text
                elif scope.is_element:
                    target = _nearest_element(scope)
                    if target is not None:
                        prop = ".".join(chain)
                        if prop in ("id", "objectName", "text", "title",
                                    "placeholderText", "label"):
                            target.props[prop] = value_text
                # else: JS block — ignore
                i = ni
                continue

            i = j
            continue

        if kind == "PUNCT" and val == "{":
            # Determine what this brace opens.
            prev = tokens[i - 1] if i > 0 else None
            type_name = ""
            is_element = False
            decl_line, decl_col = line, col

            if prev and prev[0] == "ID" and prev[1][0].isupper():
                # Direct object declaration: Button {
                type_name = prev[1]
                is_element = True
                decl_line, decl_col = prev[2], prev[3]
            else:
                # JS block or anonymous object value; check first token inside.
                k = i + 1
                while k < n and tokens[k][0] == "NEWLINE":
                    k += 1
                if (k + 1 < n and tokens[k][0] == "ID"
                        and tokens[k][1][0].isupper()
                        and tokens[k + 1][0] == "PUNCT" and tokens[k + 1][1] == "{"):
                    type_name = tokens[k][1]
                    is_element = True
                    decl_line, decl_col = tokens[k][2], tokens[k][3]

            if len(stack) == 0:
                # Stack was emptied by stray closing braces; re-seat the root.
                stack.append(_Scope())
            scope = _Scope(
                type_name=type_name,
                is_element=is_element,
                is_attached_accessible=(type_name == "Accessible"),
                decl_line=decl_line,
                decl_col=decl_col,
                parent=stack[-1],
            )
            stack.append(scope)
            i += 1
            continue

        if kind == "PUNCT" and val == "}":
            if len(stack) > 1:
                scope = stack.pop()
                elem = _finalize_scope(scope, rel_path, src_dir)
                if elem is not None:
                    results.append(elem)
            # else: stray closing brace or mismatched scope — ignore
            i += 1
            continue

        i += 1

    results.sort(key=lambda e: (e.source_file, e.line, e.column))
    return results


def _scan_qml_file(file_path: str, src_dir: str) -> tuple[str, list[QmlElement]]:
    """Scan a single .qml file. Returns (rel_path, elements)."""
    try:
        with open(file_path, encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        logger.warning("Failed to read %s: %s", file_path, e)
        return "", []

    rel_path = os.path.relpath(file_path, src_dir) if src_dir else file_path
    elements = _parse_qml(content, rel_path, src_dir)
    return rel_path, elements


# ---------------------------------------------------------------------------
# Main scan orchestrator
# ---------------------------------------------------------------------------


def scan_qml_source(src_dir: str, output_dir: str = ".") -> QmlScanResult:
    """Scan a directory for .qml files and check Accessible.name coverage.

    Args:
        src_dir: Source directory to scan.
        output_dir: Where to write output files.

    Returns:
        QmlScanResult with ok and gap elements.
    """
    root = Path(src_dir)
    if not root.is_dir():
        logger.error("Source directory not found: %s", src_dir)
        return QmlScanResult(source_dir=src_dir)

    _SKIP_DIRS = {
        "tests", "test", "autotests", "autotest",
        "examples", "example", "samples", "sample", "demo", "demos",
        "build", "Build", "builddir", "_build",
        "cmake-build", "CMakeFiles", ".cmake",
        "debian", ".git", "3rdparty", "thirdparty", "third_party",
        "node_modules", ".moc", "moc",
    }

    all_files: list[Path] = []
    for p in root.rglob("*.qml"):
        if any(part in _SKIP_DIRS for part in p.parts):
            continue
        all_files.append(p)
    if not all_files:
        logger.warning("No .qml files found in %s", src_dir)
        return QmlScanResult(source_dir=src_dir)

    parsed = 0
    all_elements: list[QmlElement] = []
    for p in all_files:
        rel_path, elements = _scan_qml_file(str(p), src_dir)
        if rel_path:
            parsed += 1
        all_elements.extend(elements)

    ok_elements = [e for e in all_elements if _is_element_complete(e, src_dir)]
    gap_elements = [e for e in all_elements if not _is_element_complete(e, src_dir)]

    # Project-wide name dedup: seed with existing names, then assign gaps.
    existing_names: set[str] = {e.accessible_name for e in ok_elements if e.accessible_name}
    for g in gap_elements:
        g.suggested_name = _generate_qml_name(g, existing_names)
        existing_names.add(g.suggested_name)

    # Deterministic order
    ok_elements.sort(key=lambda w: (w.source_file, w.line, w.element_type))
    gap_elements.sort(key=lambda w: (w.source_file, w.line, w.element_type))

    result = QmlScanResult(
        source_dir=src_dir,
        total_files=len(all_files),
        ok_elements=ok_elements,
        gap_elements=gap_elements,
    )

    _write_outputs(result, output_dir)
    return result


# ---------------------------------------------------------------------------
# Output writing
# ---------------------------------------------------------------------------


def _element_to_dict(e: QmlElement) -> dict[str, Any]:
    return {
        "element_type": e.element_type,
        "id": e.id_name,
        "source_file": e.source_file,
        "line": e.line,
        "column": e.column,
        "has_accessible_name": e.has_accessible_name,
        "has_accessible_role": e.has_accessible_role,
        "has_accessible_ignored": e.has_accessible_ignored,
        "accessible_name": e.accessible_name,
        "accessible_role": e.accessible_role,
        "parent_type": e.parent_type,
        "object_name": e.object_name,
        "text_property": e.text_property,
        "role": e.role,
        "suggested_name": e.suggested_name,
    }


def _write_outputs(result: QmlScanResult, output_dir: str) -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    total = len(result.ok_elements) + len(result.gap_elements)
    ok_count = len(result.ok_elements)
    gap_count = len(result.gap_elements)
    coverage = f"{ok_count / total * 100:.1f}%" if total else "0%"

    try:
        import yaml
    except ImportError:
        logger.error("PyYAML not installed. Run: pip install pyyaml")
        yaml = None

    ok_path = out / "qml_ok.yaml"
    ok_data = {
        "version": "1.0",
        "source": "qml",
        "widgets": [_element_to_dict(e) for e in result.ok_elements],
    }
    if yaml:
        with open(ok_path, "w", encoding="utf-8") as f:
            yaml.dump(ok_data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    else:
        with open(ok_path, "w", encoding="utf-8") as f:
            json.dump(ok_data, f, indent=2, ensure_ascii=False)
    logger.info("Written %s (%d elements)", ok_path, ok_count)

    gaps_path = out / "qml_gaps.yaml"
    gaps_data = {
        "version": "1.0",
        "source": "qml",
        "summary": {
            "total_elements": total,
            "with_names": ok_count,
            "missing_names": gap_count,
            "coverage": coverage,
        },
        "gaps": [_element_to_dict(e) for e in result.gap_elements],
    }
    if yaml:
        with open(gaps_path, "w", encoding="utf-8") as f:
            yaml.dump(gaps_data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    else:
        with open(gaps_path, "w", encoding="utf-8") as f:
            json.dump(gaps_data, f, indent=2, ensure_ascii=False)
    logger.info("Written %s (%d gaps)", gaps_path, gap_count)

    report_path = out / "qml_report.json"
    report = {
        "version": "1.0",
        "source_dir": result.source_dir,
        "stats": {
            "total_files": result.total_files,
        },
        "summary": {
            "total_elements": total,
            "with_names": ok_count,
            "missing_names": gap_count,
            "coverage": coverage,
        },
    }
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    logger.info("Written %s", report_path)

    print(f"  QML scan summary: {total} elements in {result.total_files} files",
          file=sys.stderr)
    if total:
        print(f"  With Accessible.name: {ok_count}  Missing: {gap_count}  Coverage: {coverage}",
              file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Scan QML source for interactive elements missing Accessible.name",
    )
    parser.add_argument("--src", required=True, help="Source directory")
    parser.add_argument("--output", "-o", default=".",
                        help="Output directory (default: current dir)")
    args = parser.parse_args()

    result = scan_qml_source(
        src_dir=args.src,
        output_dir=args.output,
    )

    return 0 if result.total_files > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
