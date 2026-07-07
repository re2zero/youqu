# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only

"""Static C++ source scanner using libclang.

Extracts UI skeleton: class inheritance (QWidget/DTK), setObjectName/setAccessibleName
calls, DTK component instantiation. Requires ``pip install clang``.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DTK_WIDGET_CLASSES: frozenset[str] = frozenset({
    "DWidget", "DMainWindow", "DDialog", "DFloatingWidget",
    "DPushButton", "DToolButton", "DLineEdit", "DTextEdit",
    "DComboBox", "DCheckBox", "DRadioButton", "DSlider",
    "DLabel", "DTitlebar", "DButtonBox", "DSwitchButton",
    "DProgressBar", "DTabBar", "DListView", "DTreeView",
    "DListView", "DStyledItemDelegate", "DSuggestButton",
    "DCommandLinkButton", "DPasswordEdit", "DSpinBox",
    "DDialogCloseButton", "DAlertControl", "DFileChooserEdit",
    "DFlowLayout", "DListView", "DStackWidget", "DShadowLine",
    "DSearchEdit", "DComboBox", "DFloatingButton",
})

_QT_BASE_CLASSES: frozenset[str] = frozenset({
    "QWidget", "QMainWindow", "QDialog", "QWindow",
    "QMenu", "QMenuBar", "QStatusBar", "QToolBar",
    "QPushButton", "QToolButton", "QLabel", "QLineEdit",
    "QTextEdit", "QComboBox", "QCheckBox", "QRadioButton",
    "QSlider", "QSpinBox", "QTabWidget", "QTabBar",
    "QListView", "QTreeView", "QTableView", "QScrollArea",
    "QGroupBox", "QFrame", "QStackedWidget", "QSplitter",
    "QProgressBar", "QListWidget", "QTreeWidget", "QTableWidget",
    "QGraphicsView", "QScrollArea", "QScrollBar",
})

_ALL_UI_CLASSES = _DTK_WIDGET_CLASSES | _QT_BASE_CLASSES


def _is_available() -> bool:
    try:
        import clang.cindex  # noqa: F401
        return True
    except ImportError:
        return False


def _find_libclang_path() -> str | None:
    for base in ("/usr/lib/llvm-17", "/usr/lib/llvm-18", "/usr/lib/llvm-19"):
        so = os.path.join(base, "lib", "libclang.so")
        if os.path.exists(so):
            return so
    result = subprocess.run(
        ["find", "/usr/lib", "-name", "libclang.so", "-print", "-quit"],
        capture_output=True, text=True, timeout=5,
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    return None


def _get_qt_dtk_include_flags() -> list[str]:
    flags: list[str] = []
    for pkg in ("Qt5Core", "Qt5Widgets", "Qt5Gui", "dtkcore", "dtkwidget", "dtkgui"):
        try:
            result = subprocess.run(
                ["pkg-config", "--cflags", pkg],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                flags.extend(result.stdout.strip().split())
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
    return flags


def _init_clang() -> Any:
    from clang.cindex import Config, Index

    lib_path = _find_libclang_path()
    if lib_path:
        Config.set_library_file(lib_path)

    return Index.create()


def _extract_ui_classes(tu: Any, source_file: str) -> list[dict[str, Any]]:
    from clang.cindex import CursorKind

    classes: list[dict[str, Any]] = []
    for node in tu.cursor.walk_preorder():
        if node.kind != CursorKind.CLASS_DECL and node.kind != CursorKind.STRUCT_DECL:
            continue
        if not node.location.file or node.location.file.name != source_file:
            continue
        if node.is_definition() is False:
            continue

        base_classes = []
        object_names: list[str] = []
        accessible_names: list[str] = []
        dtk_instantiations: list[str] = []

        for child in node.get_children():
            if child.kind == CursorKind.CXX_BASE_SPECIFIER:
                base_name = child.spelling or ""
                if base_name in _ALL_UI_CLASSES:
                    base_classes.append(base_name)

            elif child.kind == CursorKind.CXX_METHOD:
                method_name = child.spelling or ""
                if method_name in ("setObjectName", "setAccessibleName"):
                    for call in child.get_children():
                        if call.kind == CursorKind.CALL_EXPR:
                            for arg in call.get_children():
                                if arg.kind == CursorKind.STRING_LITERAL:
                                    literal = arg.spelling or ""
                                    value = literal.strip('"')
                                    if method_name == "setObjectName":
                                        object_names.append(value)
                                    else:
                                        accessible_names.append(value)

            elif child.kind == CursorKind.CONSTRUCTOR:
                for call in child.get_children():
                    if call.kind != CursorKind.CALL_EXPR:
                        continue
                    callee = call.spelling or ""
                    if callee in _DTK_WIDGET_CLASSES:
                        dtk_instantiations.append(callee)

        if base_classes or object_names or accessible_names or dtk_instantiations:
            classes.append({
                "class_name": node.spelling,
                "source_file": source_file,
                "base_classes": base_classes,
                "object_names": object_names,
                "accessible_names": accessible_names,
                "dtk_instantiations": dtk_instantiations,
            })

    return classes


def _scan_file(index: Any, file_path: str, extra_args: list[str]) -> list[dict[str, Any]]:
    try:
        tu = index.parse(file_path, args=extra_args)
        return _extract_ui_classes(tu, file_path)
    except Exception:
        logger.warning("Failed to parse %s with libclang", file_path)
        return []


def scan_source_dir(src_dir: str) -> list[dict[str, Any]]:
    """Scan C++ source directory for UI-relevant declarations.

    Walks the directory tree for ``*.cpp``, ``*.cxx``, ``*.h``, ``*.hpp`` files,
    parses each with libclang, and extracts:
    - Class declarations inheriting from QWidget/DTK widgets
    - setObjectName / setAccessibleName string arguments
    - DTK component instantiation (new DPushButton, new DMenu, etc.)

    Args:
        src_dir: Root directory of the target application source code.

    Returns:
        A list of class dicts.  Returns an empty list when libclang is not installed.
    """
    if not _is_available():
        logger.warning("libclang Python bindings not installed; static scan skipped")
        return []

    root = Path(src_dir)
    if not root.is_dir():
        logger.error("Source directory not found: %s", src_dir)
        return []

    index = _init_clang()
    extra_args = ["-x", "c++", "-std=c++17", "-fPIC"]
    extra_args.extend(_get_qt_dtk_include_flags())

    extensions = {".cpp", ".cxx", ".h", ".hpp"}
    results: list[dict[str, Any]] = []

    for path in sorted(root.rglob("*")):
        if path.suffix not in extensions:
            continue
        classes = _scan_file(index, str(path), extra_args)
        results.extend(classes)

    logger.info("Scanned %d files, found %d UI classes in %s", len(list(root.rglob("*"))), len(results), src_dir)
    return results
