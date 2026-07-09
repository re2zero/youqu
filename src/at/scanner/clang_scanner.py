# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only

"""Static C++ source scanner using libclang.

Extracts UI skeleton: class inheritance (QWidget/DTK), setObjectName/setAccessibleName
calls, DTK component instantiation. Requires ``pip install clang``.
"""

from __future__ import annotations

import logging
import multiprocessing
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

_DTK_WIDGET_CLASSES: frozenset[str] = frozenset(
    {
        "DWidget",
        "DMainWindow",
        "DDialog",
        "DFloatingWidget",
        "DPushButton",
        "DToolButton",
        "DLineEdit",
        "DTextEdit",
        "DComboBox",
        "DCheckBox",
        "DRadioButton",
        "DSlider",
        "DLabel",
        "DTitlebar",
        "DButtonBox",
        "DSwitchButton",
        "DProgressBar",
        "DTabBar",
        "DListView",
        "DTreeView",
        "DListView",
        "DStyledItemDelegate",
        "DSuggestButton",
        "DCommandLinkButton",
        "DPasswordEdit",
        "DSpinBox",
        "DDialogCloseButton",
        "DAlertControl",
        "DFileChooserEdit",
        "DFlowLayout",
        "DListView",
        "DStackWidget",
        "DShadowLine",
        "DSearchEdit",
        "DComboBox",
        "DFloatingButton",
    }
)

_QT_BASE_CLASSES: frozenset[str] = frozenset(
    {
        "QWidget",
        "QMainWindow",
        "QDialog",
        "QWindow",
        "QMenu",
        "QMenuBar",
        "QStatusBar",
        "QToolBar",
        "QPushButton",
        "QToolButton",
        "QLabel",
        "QLineEdit",
        "QTextEdit",
        "QComboBox",
        "QCheckBox",
        "QRadioButton",
        "QSlider",
        "QSpinBox",
        "QTabWidget",
        "QTabBar",
        "QListView",
        "QTreeView",
        "QTableView",
        "QScrollArea",
        "QGroupBox",
        "QFrame",
        "QStackedWidget",
        "QSplitter",
        "QProgressBar",
        "QListWidget",
        "QTreeWidget",
        "QTableWidget",
        "QGraphicsView",
        "QScrollArea",
        "QScrollBar",
    }
)

_ALL_UI_CLASSES = _DTK_WIDGET_CLASSES | _QT_BASE_CLASSES


@dataclass
class ScanResult:
    """Result of a source directory scan."""

    classes: list[dict[str, Any]]
    stats: dict = field(
        default_factory=lambda: {
            "total_files": 0,
            "parsed_files": 0,
            "failed_files": 0,
        }
    )


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
        capture_output=True,
        text=True,
        timeout=5,
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    return None


def _get_cxx_stdlib_flags() -> list[str]:
    flags: list[str] = []
    try:
        result = subprocess.run(
            ["g++", "-v", "-x", "c++", "/dev/null", "-fsyntax-only"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        for line in result.stderr.splitlines():
            stripped = line.strip()
            if not stripped or not stripped.startswith("/"):
                continue
            if os.path.isdir(stripped) and (
                "c++/" in stripped
                or stripped.startswith("/usr/lib/gcc/")
            ):
                flags.extend(["-isystem", stripped])
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return flags


def _get_qt_dtk_include_flags() -> list[str]:
    flags: list[str] = []
    for pkg in ("Qt5Core", "Qt5Widgets", "Qt5Gui", "dtkcore", "dtkwidget", "dtkgui"):
        try:
            result = subprocess.run(
                ["pkg-config", "--cflags", pkg],
                capture_output=True,
                text=True,
                timeout=5,
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
        try:
            Config.set_library_file(lib_path)
        except Exception:
            pass  # Already set (forked child inherits main process state)

    return Index.create()


def _find_calls_in_subtree(cursor: Any) -> list[Any]:
    """Recursively collect CALL_EXPR and CXX_NEW_EXPR from a cursor subtree.

    libclang nests CALL_EXPR inside COMPOUND_STMT, DECL_STMT, IF_STMT, etc.
    Direct-children iteration misses them — this helper recurses into compound
    nodes to find all calls regardless of nesting depth.
    """
    from clang.cindex import CursorKind

    _COMPOUND_KINDS = {
        CursorKind.COMPOUND_STMT,
        CursorKind.DECL_STMT,
        CursorKind.IF_STMT,
        CursorKind.FOR_STMT,
        CursorKind.WHILE_STMT,
        CursorKind.SWITCH_STMT,
        CursorKind.CASE_STMT,
        CursorKind.CXX_TRY_STMT,
        CursorKind.CXX_CATCH_STMT,
        CursorKind.LAMBDA_EXPR,
        CursorKind.UNEXPOSED_EXPR,
    }
    calls: list[Any] = []
    for child in cursor.get_children():
        if child.kind in (CursorKind.CALL_EXPR, CursorKind.CXX_NEW_EXPR):
            calls.append(child)
        elif child.kind in _COMPOUND_KINDS:
            calls.extend(_find_calls_in_subtree(child))
    return calls


def _find_string_literal(cursor: Any) -> str | None:
    """Find the first STRING_LITERAL in a cursor subtree, returning its value.

    libclang wraps string arguments in UNEXPOSED_EXPR layers (e.g. implicit
    QString construction). Direct-children iteration misses the literal —
    this helper recurses to find it regardless of nesting.
    """
    from clang.cindex import CursorKind

    for child in cursor.get_children():
        if child.kind == CursorKind.STRING_LITERAL:
            literal = child.spelling or ""
            return literal.strip('"')
        result = _find_string_literal(child)
        if result is not None:
            return result
    return None


def _extract_ui_classes(tu: Any, source_file: str) -> list[dict[str, Any]]:
    from clang.cindex import CursorKind

    _METHOD_KINDS = {
        CursorKind.CXX_METHOD,
        CursorKind.CONSTRUCTOR,
        CursorKind.FUNCTION_TEMPLATE,
    }

    method_info: dict[str, dict[str, Any]] = {}
    all_nodes = list(tu.cursor.walk_preorder())

    for node in all_nodes:
        if node.kind not in _METHOD_KINDS:
            continue
        loc_file = node.location.file.name if node.location.file else ""
        src_stem = Path(source_file).stem
        if not loc_file or Path(loc_file).stem != src_stem:
            continue
        parent = node.semantic_parent
        class_name = parent.spelling if parent else ""
        if not class_name:
            continue

        if class_name not in method_info:
            method_info[class_name] = {
                "object_names": [],
                "accessible_names": [],
                "dtk_instantiations": [],
            }
        info = method_info[class_name]
        for call in _find_calls_in_subtree(node):
            callee = call.spelling or ""
            if callee in ("setObjectName", "setAccessibleName"):
                value = _find_string_literal(call)
                if value:
                    if callee == "setObjectName":
                        info["object_names"].append(value)
                    else:
                        info["accessible_names"].append(value)
            elif callee in _DTK_WIDGET_CLASSES:
                info["dtk_instantiations"].append(callee)

    classes: list[dict[str, Any]] = []
    for node in all_nodes:
        if node.kind not in (CursorKind.CLASS_DECL, CursorKind.STRUCT_DECL):
            continue
        if not node.spelling:
            continue
        if node.spelling not in method_info:
            continue
        name = node.spelling
        info = method_info[name]

        base_classes = []
        for child in node.get_children():
            if child.kind == CursorKind.CXX_BASE_SPECIFIER:
                base_name = child.spelling or ""
                base_classes.append(base_name)

        if base_classes or info["object_names"] or info["accessible_names"] or info["dtk_instantiations"]:
            classes.append(
                {
                    "class_name": name,
                    "source_file": source_file,
                    "base_classes": base_classes,
                    **info,
                }
            )

    return classes


def _scan_file(
    index: Any, file_path: str, source_file: str, extra_args: list[str]
) -> tuple[list[dict[str, Any]], str | None]:
    try:
        tu = index.parse(file_path, args=extra_args)
        return _extract_ui_classes(tu, source_file), None
    except Exception as e:
        return [], f"{type(e).__name__}: {e}"


def _worker_init(args: list[str]):
    global _w_index, _w_extra
    _w_index = _init_clang()
    _w_extra = args


def _worker_scan(item: tuple[str, str]) -> tuple[str, list[dict], str | None]:
    file_path, source_file = item
    return source_file, *_scan_file(_w_index, file_path, source_file, _w_extra)


def _worker_scan_batch(batch: list[tuple[str, str]]) -> list[tuple[str, list[dict], str | None]]:
    return [_worker_scan(item) for item in batch]


_w_index: Any = None
_w_extra: list[str] = []


def scan_source_dir(
    src_dir: str,
    progress_cb: Callable[[int, int, str], None] | None = None,
    file_done_cb: Callable[[str, list[dict], str | None], None] | None = None,
    include_dirs: list[str] | None = None,
    pool: multiprocessing.Pool | None = None,
) -> ScanResult:
    """Scan C++ source directory for UI-relevant declarations.

    Walks the directory tree for ``*.cpp``, ``*.cxx``, ``*.h``, ``*.hpp`` files,
    parses each with libclang, and extracts:
    - Class declarations inheriting from QWidget/DTK widgets
    - setObjectName / setAccessibleName string arguments
    - DTK component instantiation (new DPushButton, new DMenu, etc.)

    Args:
        src_dir: Root directory of the target application source code.
        progress_cb: Optional callback(current_index, total, file_path) per file.
            Errors are logged via logger when this callback is set.
        include_dirs: Optional subdirectory names to restrict scanning to.
            Only files whose path contains one of these directory segments are scanned.
        pool: Optional pre-created multiprocessing.Pool. When provided, the caller
            is responsible for creating (in the main thread) and closing the pool.
            When None, a new pool is created and closed internally.

    Returns:
        A ``ScanResult`` with found classes and scan statistics.
        Returns an empty ScanResult when libclang is not installed.
    """
    if not _is_available():
        logger.warning("libclang Python bindings not installed; static scan skipped")
        return ScanResult(
            classes=[], stats={"total_files": 0, "parsed_files": 0, "failed_files": 0}
        )

    root = Path(src_dir)
    if not root.is_dir():
        logger.error("Source directory not found: %s", src_dir)
        return ScanResult(
            classes=[], stats={"total_files": 0, "parsed_files": 0, "failed_files": 0}
        )

    extra_args = ["-x", "c++", "-std=c++17", "-fPIC"]
    extra_args.extend(_get_cxx_stdlib_flags())
    extra_args.extend(_get_qt_dtk_include_flags())

    extensions = {".cpp", ".cxx", ".h", ".hpp"}
    _SKIP_DIRS = {
        "tests", "test", "autotests", "autotest",
        "build", "Build", "builddir", "_build",
        "cmake-build", "CMakeFiles", ".cmake",
        "debian", ".git",
    }
    _SKIP_PREFIXES = ("test_", "moc_", "mocs_", "ui_", "qrc_")
    include_set = frozenset(include_dirs) if include_dirs else None
    all_files: list[Path] = []
    for p in root.rglob("*"):
        if p.suffix not in extensions:
            continue
        if any(part in _SKIP_DIRS for part in p.parts):
            continue
        if p.stem.startswith(_SKIP_PREFIXES):
            continue
        if include_set:
            rel_parts = p.relative_to(root).parts
            if not any("/".join(rel_parts[:i + 1]) in include_set for i in range(len(rel_parts))):
                continue
        all_files.append(p)
    all_files.sort()

    if not all_files:
        return ScanResult(
            classes=[], stats={"total_files": 0, "parsed_files": 0, "failed_files": 0}
        )

    task_items = [(str(p), str(p.relative_to(root))) for p in all_files]
    total = len(task_items)
    n_workers = min(os.cpu_count() or 4, 8)
    batch_size = max(1, (total + n_workers - 1) // n_workers)
    batches = [task_items[i : i + batch_size] for i in range(0, total, batch_size)]

    results: list[dict[str, Any]] = []
    parsed = 0
    failed = 0
    done = 0

    if progress_cb:
        progress_cb(0, total, f"scanning {total} files with {n_workers} processes")

    def _consume(pool_obj):
        nonlocal parsed, failed, done
        for batch_results in pool_obj.imap_unordered(_worker_scan_batch, batches):
            for rel_path, classes, error in batch_results:
                if error:
                    logger.warning("Failed to parse %s: %s", rel_path, error)
                    failed += 1
                else:
                    parsed += 1
                results.extend(classes)
                done += 1
                if progress_cb:
                    progress_cb(done, total, rel_path)
                if file_done_cb:
                    file_done_cb(rel_path, classes, error)

    if pool is not None:
        _consume(pool)
    else:
        with multiprocessing.Pool(processes=n_workers, initializer=_worker_init, initargs=(extra_args,)) as p:
            _consume(p)

    logger.info(
        "Scanned %d files, found %d UI classes in %s",
        total,
        len(results),
        src_dir,
    )
    return ScanResult(
        classes=results,
        stats={"total_files": total, "parsed_files": parsed, "failed_files": failed},
    )
