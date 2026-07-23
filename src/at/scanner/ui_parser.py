# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only

"""Qt .ui XML file parser.

Parses Qt Designer .ui files and extracts widget tree with
objectName, class, text, and properties.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class UiWidget:
    """A widget from a .ui file."""

    class_name: str
    name: str  # objectName
    text: str = ""
    tool_tip: str = ""
    accessible_name: str = ""
    children: list["UiWidget"] = field(default_factory=list)


def _get_property(elem: ET.Element, name: str) -> str:
    """Get a property value from a widget element."""
    prop = elem.find(f".//property[@name='{name}']")
    if prop is not None and prop.text:
        return prop.text.strip()
    return ""


def _extract_widgets(parent_elem: ET.Element) -> list[UiWidget]:
    """Recursively extract widgets from a .ui element."""
    widgets = []

    # Direct widget children (through layout items)
    for widget in parent_elem.findall(".//widget"):
        w = UiWidget(
            class_name=widget.get("class", ""),
            name=widget.get("name", ""),
            text=_get_property(widget, "text"),
            tool_tip=_get_property(widget, "toolTip"),
            accessible_name=_get_property(widget, "accessibleName"),
        )
        # Recurse into layout items within this widget
        w.children = _extract_widgets(widget)
        widgets.append(w)

    # Menu actions (for QMenuBar/QMenu)
    for action in parent_elem.findall(".//action"):
        name = action.get("name", "")
        text = _get_property(action, "text")
        if name or text:
            widgets.append(
                UiWidget(
                    class_name="QAction",
                    name=name,
                    text=text,
                )
            )

    return widgets


def parse_ui_file(ui_path: str) -> dict[str, Any] | None:
    """Parse a .ui XML file and extract widget tree.

    Returns a dict matching the scan class format for easy merging.

    Args:
        ui_path: Path to the .ui XML file.

    Returns:
        Dict with class_name, source_file, base_classes, is_ui_widget,
        object_names, accessible_names, ui_children. None if parse fails.
    """
    path = Path(ui_path)
    if not path.is_file():
        return None

    try:
        tree = ET.parse(str(path))
        root = tree.getroot()
    except ET.ParseError as e:
        logger.warning("Failed to parse %s: %s", ui_path, e)
        return None

    # Extract class name and root widget
    class_elem = root.find("class")
    class_name = class_elem.text if class_elem is not None else ""

    widget_elem = root.find("widget")
    if widget_elem is None:
        return None

    root_widget_class = widget_elem.get("class", "")
    root_widget_name = widget_elem.get("name", "")

    # Build children list
    children = _extract_widgets(widget_elem)

    # Convert to scan-compatible format
    return {
        "class_name": class_name,
        "source_file": str(path),
        "base_classes": [root_widget_class],
        "is_ui_widget": True,
        "object_names": [root_widget_name],
        "accessible_names": [_get_property(widget_elem, "accessibleName")],
        "ui_children": [
            {
                "class": w.class_name,
                "name": w.name,
                "text": w.text,
                "toolTip": w.tool_tip,
                "accessibleName": w.accessible_name,
            }
            for w in children
            if w.name or w.text
        ],
    }


def scan_ui_files(src_dir: str) -> list[dict[str, Any]]:
    """Scan a directory for .ui files and parse them.

    Args:
        src_dir: Root directory to search for .ui files.

    Returns:
        List of parsed UI dicts in scan-compatible format.
    """
    root = Path(src_dir)
    if not root.is_dir():
        return []

    results = []
    skip_dirs = {"build", "CMakeFiles", ".cmake", "_build"}

    for ui_file in root.rglob("*.ui"):
        # Skip build directories
        if any(part in skip_dirs for part in ui_file.parts):
            continue

        result = parse_ui_file(str(ui_file))
        if result:
            results.append(result)
            logger.info(
                "Parsed %s: %s (%d children)",
                ui_file,
                result["class_name"],
                len(result.get("ui_children", [])),
            )

    return results
