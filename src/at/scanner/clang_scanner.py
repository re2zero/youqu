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
        # Core widgets
        "DWidget",
        "DMainWindow",
        "DWindow",
        "DFrame",
        # Dialogs
        "DAbstractDialog",
        "DDialog",
        "DDialogCloseButton",
        "DAboutDialog",
        "DInputDialog",
        "DFeatureDisplayDialog",
        # Buttons
        "DPushButton",
        "DToolButton",
        "DIconButton",
        "DSwitchButton",
        "DSuggestButton",
        "DCommandLinkButton",
        "DButtonBox",
        "DFloatingButton",
        # Input widgets
        "DLineEdit",
        "DTextEdit",
        "DComboBox",
        "DCheckBox",
        "DRadioButton",
        "DSlider",
        "DSpinBox",
        "DPasswordEdit",
        "DSearchEdit",
        "DFileChooserEdit",
        # Display widgets
        "DLabel",
        "DTitlebar",
        "DProgressBar",
        "DIndeterminateProgressBar",
        "DWaterProgress",
        "DAlertControl",
        # Navigation and containers
        "DTabBar",
        "DListView",
        "DTreeView",
        "DStackWidget",
        "DDrawer",
        "DFloatingWidget",
        "DToolBox",
        # Layout and separators
        "DFlowLayout",
        "DHeaderLine",
        "DShadowLine",
        # Menu and toolbar (may not exist in all DTK versions)
        "DMenuBar",
        "DStatusBar",
        "DMenu",
        "DAction",
        "DMenuItem",
        # Settings
        "DSettings",
        "DSettingsWidget",
        # Effects and decorations
        "DArrowRectangle",
        "DToolTip",
        "DSegmentedControl",
        "DClipEffectWidget",
        # Abstract base classes
        "DAbstractButton",
        # Flyout and popup (may not exist in all DTK versions)
        "DFlyoutWidget",
        "DMessageBox",
        # View item action (inherits from QAction)
        "DViewItemAction",
        # Additional DTK6 widgets
        "DMessageManager",
        "DHBoxWidget",
        "DBoxWidget",
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

    # Node kinds that may contain nested calls (compound statements + functions)
    _RECURSIVE_KINDS = {
        CursorKind.COMPOUND_STMT,
        CursorKind.DECL_STMT,
        CursorKind.IF_STMT,
        CursorKind.FOR_STMT,
        CursorKind.WHILE_STMT,
        CursorKind.SWITCH_STMT,
        CursorKind.CASE_STMT,
        CursorKind.CXX_TRY_STMT,
        CursorKind.CXX_CATCH_STMT,
        # Function/method bodies also contain calls
        CursorKind.CONSTRUCTOR,
        CursorKind.CXX_METHOD,
        CursorKind.FUNCTION_DECL,
        CursorKind.FUNCTION_TEMPLATE,
        # Expression kinds that nest calls
        CursorKind.CXX_NEW_EXPR,
        CursorKind.UNEXPOSED_EXPR,
        CursorKind.BINARY_OPERATOR,
        CursorKind.CXX_STATIC_CAST_EXPR,
        CursorKind.CXX_DYNAMIC_CAST_EXPR,
        CursorKind.CXX_REINTERPRET_CAST_EXPR,
        CursorKind.CXX_CONST_CAST_EXPR,
        CursorKind.MEMBER_REF_EXPR,
        CursorKind.CALL_EXPR,  # Nested calls (e.g., func(inner()))
    }

    calls: list[Any] = []
    try:
        if cursor.kind in (CursorKind.CALL_EXPR, CursorKind.CXX_NEW_EXPR):
            calls.append(cursor)
        if cursor.kind in _RECURSIVE_KINDS:
            for child in cursor.get_children():
                calls.extend(_find_calls_in_subtree(child))
    except Exception:
        # Silently skip problematic nodes — partial results are better than crash
        pass
    return calls
def _find_string_literal(cursor: Any) -> str | None:
    """Find the first STRING_LITERAL in a cursor subtree, returning its value.

    libclang wraps string arguments in UNEXPOSED_EXPR layers (e.g. implicit
    QString construction). Direct-children iteration misses the literal —
    this helper recurses to find it regardless of nesting.

    Supports:
    - Direct string literals: "text"
    - tr("text") / QObject::tr("text")
    - QStringLiteral("text") / QLatin1String("text")
    - qApp->translate("context", "text") — returns second argument
    """
    from clang.cindex import CursorKind

    try:
        # Direct string literal (check current node first)
        if cursor.kind == CursorKind.STRING_LITERAL:
            literal = cursor.spelling or ""
            return literal.strip('"')

        # Handle tr() / QStringLiteral() / QLatin1String() calls at this node
        if cursor.kind == CursorKind.CALL_EXPR:
            spelling = cursor.spelling or ""

            if spelling in ("tr", "QStringLiteral", "QLatin1String"):
                # First argument is the string
                args = list(cursor.get_arguments())
                if args:
                    return _find_string_literal(args[0])

            if spelling == "translate":
                # qApp->translate("context", "text") — second argument is the text
                args = list(cursor.get_arguments())
                if len(args) >= 2:
                    return _find_string_literal(args[1])

        # Recurse into children for nested literals
        for child in cursor.get_children():
            result = _find_string_literal(child)
            if result is not None:
                return result
    except Exception:
        # Silently skip problematic nodes
        pass
    return None

def _get_object_name_from_expr(cursor: Any) -> str | None:
    """Try to extract objectName from an expression (e.g., member variable reference).

    For: addAction(m_closeTabAction) → returns "m_closeTabAction"
    For: addAction(new QAction(...)->setObjectName("x")) → returns "x"
    Returns None if not found. This is a best-effort heuristic.
    """
    from clang.cindex import CursorKind

    try:
        if cursor.kind == CursorKind.DECL_REF_EXPR:
            # Variable reference like m_closeTabAction
            return cursor.spelling

        if cursor.kind == CursorKind.CXX_NEW_EXPR:
            # new QAction(...) — check for chained ->setObjectName()
            for child in cursor.get_children():
                if child.kind == CursorKind.CALL_EXPR and child.spelling == "setObjectName":
                    return _find_string_literal(child)
    except Exception:
        # Silently skip problematic nodes
        pass

    return None


def _extract_ui_classes(tu: Any, source_file: str) -> list[dict[str, Any]]:
    from clang.cindex import CursorKind

    _METHOD_KINDS = {
        CursorKind.CXX_METHOD,
        CursorKind.CONSTRUCTOR,
        CursorKind.FUNCTION_TEMPLATE,
        CursorKind.FUNCTION_DECL,  # For out-of-line method definitions
    }

    method_info: dict[str, dict[str, Any]] = {}

    # Collect diagnostics for logging (non-fatal parse issues)
    diag_count = len(list(tu.diagnostics)) if hasattr(tu, "diagnostics") else 0
    if diag_count > 0:
        logger.debug("File %s has %d diagnostics (non-fatal)", source_file, diag_count)

    # Walk preorder with error recovery — partial results are better than nothing
    all_nodes: list[Any] = []
    try:
        all_nodes = list(tu.cursor.walk_preorder())
    except Exception as e:
        logger.warning("walk_preorder failed for %s: %s — trying partial extraction", source_file, e)
        # Fallback: try direct children only (may miss nested methods but better than empty)
        try:
            all_nodes = list(tu.cursor.get_children())
        except Exception as e2:
            logger.error("Fallback traversal also failed for %s: %s", source_file, e2)
            return []

    def _get_class_name_from_node(node) -> str:
        """Get class name from a method/function node.

        Handles both in-class methods (via semantic_parent) and
        out-of-line definitions (via qualified name like ClassName::method).
        """
        # Try semantic_parent first (in-class methods)
        parent = node.semantic_parent
        if parent and parent.spelling:
            return parent.spelling

    for node in all_nodes:
        try:
            if node.kind not in _METHOD_KINDS:
                continue
            loc_file = node.location.file.name if node.location.file else ""
            src_stem = Path(source_file).stem
            if not loc_file or Path(loc_file).stem != src_stem:
                continue

            class_name = _get_class_name_from_node(node)
            if not class_name:
                continue

            if class_name not in method_info:
                method_info[class_name] = {
                    "object_names": set(),
                    "accessible_names": set(),
                    "dtk_instantiations": set(),
                    "action_texts": set(),      # QAction text from tr() for AT-SPI name
                    "menu_actions": set(),      # addAction relationships
                }
            info = method_info[class_name]
            for call in _find_calls_in_subtree(node):
                callee = call.spelling or ""
                if callee in ("setObjectName", "setAccessibleName"):
                    value = _find_string_literal(call)
                    if value:
                        if callee == "setObjectName":
                            info["object_names"].add(value)
                        else:
                            info["accessible_names"].add(value)
                # NEW: Utils::set_Object_Name(this) — objectName = class_name
                elif callee == "set_Object_Name":
                    args = list(call.get_arguments())
                    if args:
                        # Check if argument is 'this' (CXX_THIS_EXPR, possibly wrapped)
                        is_this = False
                        for child in args[0].walk_preorder():
                            if child.kind == CursorKind.CXX_THIS_EXPR:
                                is_this = True
                                break
                        if is_this:
                            info["object_names"].add(class_name)
                # NEW: QAction constructor — capture text for AT-SPI name
                # Handle both direct CALL_EXPR and CXX_NEW_EXPR (new QAction(...))
                elif callee == "QAction":
                    args = list(call.get_arguments())
                    if args:
                        text = _find_string_literal(args[0])
                        if text:
                            info["action_texts"].add(text)
                # NEW: addAction — capture menu-action relationships
                elif callee == "addAction":
                    args = list(call.get_arguments())
                    if args:
                        action_name = _get_object_name_from_expr(args[0])
                        if action_name:
                            info["menu_actions"].add(action_name)
                elif callee in _DTK_WIDGET_CLASSES:
                    info["dtk_instantiations"].add(callee)
        except Exception as e:
            # Per-node error recovery: skip problematic nodes, continue with others
            logger.debug("Skipping node in %s: %s", source_file, e)
            continue

    # Collect class declarations with per-node error recovery
    classes: list[dict[str, Any]] = []
    for node in all_nodes:
        try:
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

            if base_classes or info["object_names"] or info["accessible_names"] or info["dtk_instantiations"] or info["action_texts"] or info["menu_actions"]:
                is_ui_widget = any(base in _ALL_UI_CLASSES for base in base_classes)
                classes.append(
                    {
                        "class_name": name,
                        "source_file": source_file,
                        "base_classes": base_classes,
                        "is_ui_widget": is_ui_widget,
                        "object_names": sorted(info["object_names"]),
                        "accessible_names": sorted(info["accessible_names"]),
                        "dtk_instantiations": sorted(info["dtk_instantiations"]),
                        "action_texts": sorted(info["action_texts"]),
                        "menu_actions": sorted(info["menu_actions"]),
                    }
                )
        except Exception as e:
            logger.debug("Skipping class node in %s: %s", source_file, e)
            continue

    return classes


def _scan_file(
    index: Any, file_path: str, source_file: str, extra_args: list[str]
) -> tuple[list[dict[str, Any]], str | None]:
    try:
        tu = index.parse(file_path, args=extra_args)
        return _extract_ui_classes(tu, source_file), None
    except Exception as e:
        err_msg = f"{type(e).__name__}: {e}"
        # Classify known template/template-argument errors
        if "template" in err_msg.lower() or "Unknown" in err_msg:
            return [], f"template_parse_error: {err_msg}"
        return [], err_msg


def _worker_init(args: list[str]):
    global _w_index, _w_extra
    _w_index = _init_clang()
    _w_extra = args


def _worker_scan(item: tuple[str, str, list[str]]) -> tuple[str, list[dict], str | None]:
    """Scan a single file with its specific flags.

    Args:
        item: (file_path, source_file, flags) tuple.
    """
    file_path, source_file, flags = item
    return source_file, *_scan_file(_w_index, file_path, source_file, flags)


def _worker_scan_batch(batch: list[tuple[str, str, list[str]]]) -> list[tuple[str, list[dict], str | None]]:
    return [_worker_scan(item) for item in batch]

_w_index: Any = None
_w_extra: list[str] = []


def _load_compile_commands(src_dir: str) -> dict[str, list[str]] | None:
    """Load compile_commands.json from src_dir or its build directory.

    Returns a dict mapping file_path -> compile_flags, or None if not found.
    """
    import json
    import shlex

    root = Path(src_dir)
    candidates = [
        root / "compile_commands.json",
        root / "build" / "compile_commands.json",
        root.parent / "build" / "compile_commands.json",
    ]

    for candidate in candidates:
        if candidate.is_file():
            try:
                with open(candidate, encoding="utf-8") as f:
                    cmds = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Failed to load %s: %s", candidate, e)
                continue

            file_flags: dict[str, list[str]] = {}
            for cmd in cmds:
                file_path = cmd.get("file", "")
                command = cmd.get("command", "")
                if not file_path or not command:
                    continue
                try:
                    parts = shlex.split(command)
                    # Remove compiler and source file from flags
                    flags = [
                        p for p in parts
                        if not p.startswith("/usr/bin")
                        and file_path not in p
                        and not p.startswith("-c")
                    ]
                    file_flags[file_path] = flags
                except ValueError as e:
                    logger.debug("Failed to parse command for %s: %s", file_path, e)

            if file_flags:
                logger.info(
                    "Loaded compile_commands.json: %d entries from %s",
                    len(file_flags),
                    candidate,
                )
                return file_flags

    return None


def scan_source_dir(
    src_dir: str,
    progress_cb: Callable[[int, int, str], None] | None = None,
    file_done_cb: Callable[[str, list[dict], str | None], None] | None = None,
    include_dirs: list[str] | None = None,
    pool: multiprocessing.Pool | None = None,
    target_lang: str = "zh_CN",
    compile_commands: str | None = None,
) -> ScanResult:
    """Scan C++ source directory for UI-relevant declarations.

    Walks the directory tree for ``*.cpp``, ``*.cxx``, ``*.h``, ``*.hpp`` files,
    parses each with libclang, and extracts:
    - Class declarations inheriting from QWidget/DTK widgets
    - setObjectName / setAccessibleName string arguments
    - DTK component instantiation (new DPushButton, new DMenu, etc.)
    - QAction text from tr() calls (with translation lookup)
    - .ui XML file widget trees

    Args:
        src_dir: Root directory of the target application source code.
        progress_cb: Optional callback(current_index, total, file_path) per file.
            Errors are logged via logger when this callback is set.
        include_dirs: Optional subdirectory names to restrict scanning to.
            Only files whose path contains one of these directory segments are scanned.
        pool: Optional pre-created multiprocessing.Pool. When provided, the caller
            is responsible for creating (in the main thread) and closing the pool.
            When None, a new pool is created and closed internally.
        target_lang: Target language code for translation lookup (default: zh_CN).
            Used to find .ts files and translate tr() strings.
        compile_commands: Optional path to compile_commands.json. If None,
            auto-detects from src_dir/build/. Using compile_commands.json is
            strongly recommended for accurate AST parsing.

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
    # Load compile_commands.json if available (strongly recommended for accurate parsing)
    file_flags: dict[str, list[str]] | None = None
    if compile_commands:
        file_flags = _load_compile_commands(compile_commands)
    if file_flags is None:
        file_flags = _load_compile_commands(src_dir)

    # Fallback: generic flags if no compile_commands.json
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

    # Build task items with per-file flags (from compile_commands) or fallback to extra_args
    task_items: list[tuple[str, str, list[str]]] = []
    for p in all_files:
        abs_path = str(p)
        rel_path = str(p.relative_to(root))
        flags = file_flags.get(abs_path, extra_args) if file_flags else extra_args
        task_items.append((abs_path, rel_path, flags))

    total = len(task_items)
    n_workers = min(os.cpu_count() or 4, 8)
    batch_size = max(1, (total + n_workers - 1) // n_workers)
    batches = [task_items[i : i + batch_size] for i in range(0, total, batch_size)]

    results: list[dict[str, Any]] = []
    parsed = 0
    failed = 0
    template_errors = 0
    done = 0
    if progress_cb:
        progress_cb(0, total, f"scanning {total} files with {n_workers} processes")

    def _consume(pool_obj):
        nonlocal parsed, failed, template_errors, done
        for batch_results in pool_obj.imap_unordered(_worker_scan_batch, batches):
            for rel_path, classes, error in batch_results:
                if error:
                    logger.warning("Failed to parse %s: %s", rel_path, error)
                    failed += 1
                    if "template_parse_error" in error:
                        template_errors += 1
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

    # NEW: Parse .ui files
    from src.at.scanner.ui_parser import scan_ui_files

    ui_results = scan_ui_files(src_dir)
    logger.info("Found %d .ui files", len(ui_results))

    # NEW: Load translation files and apply to action_texts
    from src.at.scanner.ts_translator import TsTranslator, find_ts_files

    ts_files = find_ts_files(str(root.parent), target_lang) or find_ts_files(src_dir, target_lang)
    translator = None
    if ts_files:
        # Use parent directory for translations (common layout: project/translations/)
        trans_dir = root.parent / "translations"
        if not trans_dir.is_dir():
            trans_dir = root / "translations"
        if not trans_dir.is_dir():
            trans_dir = root
        translator = TsTranslator(str(trans_dir), target_lang)

    # Apply translations to action_texts
    if translator:
        for cls in results:
            if "action_texts" in cls and cls["action_texts"]:
                translated = [
                    translator.translate(text, context=cls.get("class_name", ""))
                    for text in cls["action_texts"]
                ]
                cls["translated_action_texts"] = translated

    # Merge .ui results with C++ results
    all_classes = results + ui_results

    logger.info(
        "Scanned %d files, found %d UI classes in %s",
        total,
        len(all_classes),
        src_dir,
    )
    return ScanResult(
        classes=all_classes,
        stats={
            "total_files": total,
            "parsed_files": parsed,
            "failed_files": failed,
            "template_errors": template_errors,
            "ui_files": len(ui_results),
            "ts_files_loaded": len(ts_files),
            "compile_commands_used": file_flags is not None,
            "compile_commands_entries": len(file_flags) if file_flags else 0,
        },
    )
