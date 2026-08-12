#!/usr/bin/env python3
"""Generate a type database for AT-SPI widget classification.

Parses DTK DWidget and Qt6 QtWidgets headers to extract class inheritance
chains, then classifies each class as interactive, decorative, or layout
based on its Qt root ancestor.

Output: JSON file loadable by scan_gaps.py's TypeDatabase.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# libclang bootstrap — MUST happen before any clang import
# ---------------------------------------------------------------------------

_LIBCLANG_CANDIDATES = [
    "/usr/lib/x86_64-linux-gnu",
    "/usr/lib64",
    "/usr/lib",
    "/usr/lib/llvm-18/lib",
    "/usr/lib/llvm-17/lib",
    "/usr/lib/llvm-19/lib",
]

_libclang_path: str | None = None
for _base in _LIBCLANG_CANDIDATES:
    if not os.path.isdir(_base):
        continue
    try:
        for _f in os.listdir(_base):
            if "libclang" in _f and _f.endswith(".so") or _f.endswith(".so.1"):
                _libclang_path = _base
                break
    except OSError:
        continue
    if _libclang_path:
        break

if _libclang_path:
    os.environ.setdefault("LD_LIBRARY_PATH", "")
    paths = os.environ["LD_LIBRARY_PATH"].split(":")
    if _libclang_path not in paths:
        os.environ["LD_LIBRARY_PATH"] = f"{_libclang_path}:" + os.environ["LD_LIBRARY_PATH"]

try:
    from clang.cindex import Config as _ClangConfig

    _ClangConfig.set_library_path(_libclang_path or "/usr/lib/x86_64-linux-gnu")
    from clang.cindex import CursorKind, Index

    _LIBCLANG_READY = True
except Exception as e:
    print(f"WARNING: libclang not available: {e}", file=sys.stderr)
    _LIBCLANG_READY = False

# ---------------------------------------------------------------------------
# Qt root class categories
# ---------------------------------------------------------------------------

QT_INTERACTIVE_ROOTS: set[str] = {
    # Buttons
    "QAbstractButton",
    # Text input
    "QLineEdit",
    "QTextEdit",
    "QPlainTextEdit",
    # Selection
    "QComboBox",
    # Spin / slider / scroll
    "QAbstractSpinBox",
    "QAbstractSlider",
    "QScrollBar",
    # Item views
    "QAbstractItemView",
    "QAbstractScrollArea",
    # Tab bar (not tab widget — tab widget is a container)
    "QTabBar",
    # Menu
    "QMenu",
    "QMenuBar",
    # Actions
    "QAction",
    "QActionGroup",
    "QShortcut",
    "QButtonGroup",
    # Calendar
    "QCalendarWidget",
    "QDialogButtonBox",
    "QKeySequenceEdit",
}

QT_DECORATIVE_ROOTS: set[str] = {
    "QLabel",
    "QProgressBar",
    "QFrame",
    "QGraphicsView",
    "QWidget",
    "QMainWindow",
    "QDialog",
    "QWindow",
    # Container types — not interactive, no assertion target
    "QGroupBox",
    "QScrollArea",
    "QSplitter",
    "QStackedWidget",
    "QStatusBar",
    "QTabWidget",
    "QToolBar",
}

# DTK override table: classes whose inheritance chain doesn't reveal their true category.
# DTK often inherits interactive widgets directly from QWidget (not from QLineEdit, QSlider, etc.),
# so inheritance analysis alone can't distinguish them from decorative containers.
DTK_CATEGORY_OVERRIDES: dict[str, str] = {
    # Text input (inherit QWidget directly)
    "DLineEdit": "interactive",
    "DPasswordEdit": "interactive",  # inherits DLineEdit
    "DSearchEdit": "interactive",  # inherits DLineEdit
    "DFileChooserEdit": "interactive",  # inherits DLineEdit
    # Value selection (inherit QWidget directly)
    "DSlider": "interactive",
    # Tab navigation (inherit QWidget directly)
    "DTabBar": "interactive",
    # List selection (inherit QWidget directly)
    "DSimpleListView": "interactive",
    # Button container (inherit QWidget directly)
    "DButtonBox": "interactive",
    # Visual indicators / decorative (inherit QWidget directly)
    "DArrowRectangle": "decorative",
    "DBackgroundGroup": "decorative",
    "DCircleProgress": "decorative",
    "DClipEffectWidget": "decorative",
    "DFloatingWidget": "decorative",
    "DIndeterminateProgressbar": "decorative",
    "DPageIndicator": "decorative",
    "DShadowLine": "decorative",
    "DSpinner": "decorative",
    "DStackWidget": "decorative",
    "DWaterProgress": "decorative",
    "DWarningButton": "interactive",  # inherits DPushButton (typedef)
    "ColorButton": "interactive",  # inherits DPushButton (typedef)
    "DShortcutEditLabel": "interactive",  # inherits QLabel but is interactive
}

QT_LAYOUT_ROOTS: set[str] = {
    "QLayout",
    "QBoxLayout",
    "QHBoxLayout",
    "QVBoxLayout",
    "QGridLayout",
    "QFormLayout",
    "QStackedLayout",
}

ALL_QT_ROOTS: set[str] = QT_INTERACTIVE_ROOTS | QT_DECORATIVE_ROOTS | QT_LAYOUT_ROOTS

# ---------------------------------------------------------------------------
# Include path auto-detection
# ---------------------------------------------------------------------------

def _detect_include_flags() -> list[str]:
    """Auto-detect Qt and DTK include paths.

    Only includes specific DTK subdirectories (DWidget, DCore, DGui)
    to avoid symbol conflicts from DDeclarative, DLog etc.
    """
    flags = ["-x", "c++", "-std=c++17", "-fPIC"]
    for base in ["/usr/include/x86_64-linux-gnu/qt6", "/usr/include/qt6",
                  "/usr/include/x86_64-linux-gnu/qt5", "/usr/include/qt5"]:
        p = Path(base)
        if p.is_dir():
            flags.extend(["-isystem", str(p)])
            for sub in p.iterdir():
                if sub.is_dir():
                    flags.extend(["-isystem", str(sub)])
    for base in ["/usr/include/x86_64-linux-gnu/dtk6", "/usr/include/dtk6",
                  "/usr/include/x86_64-linux-gnu/dtk5", "/usr/include/dtk5",
                  "/usr/include/DtkWidget", "/usr/include/DtkGui"]:
        p = Path(base)
        if p.is_dir():
            for sub in ["DWidget", "DCore", "DGui"]:
                sp = p / sub
                if sp.is_dir():
                    flags.extend(["-isystem", str(sp)])
    return flags

def _find_qt_headers() -> list[str]:
    """Find all Qt6 QtWidgets header files via auto-detection.
    Uses the first base that exists to avoid duplicates from symlinks.
    """
    headers = []
    for base in ["/usr/include/x86_64-linux-gnu/qt6", "/usr/include/qt6",
                  "/usr/include/x86_64-linux-gnu/qt5", "/usr/include/qt5"]:
        qtwidgets = Path(base) / "QtWidgets"
        if qtwidgets.is_dir():
            for entry in qtwidgets.iterdir():
                if entry.is_file() and not entry.name.startswith(".") and not entry.name.endswith("_p.h"):
                    headers.append(str(entry))
            break  # Use first found base only
    return sorted(headers)


def _find_dtk_headers() -> list[str]:
    """Find all DTK DWidget header files via auto-detection.
    Uses the first base that exists to avoid duplicates from symlinks.
    """
    headers = []
    for base in ["/usr/include/x86_64-linux-gnu/dtk6", "/usr/include/dtk6",
                  "/usr/include/x86_64-linux-gnu/dtk5", "/usr/include/dtk5",
                  "/usr/include/DtkWidget"]:
        dwidget = Path(base) / "DWidget"
        if dwidget.is_dir():
            for entry in dwidget.iterdir():
                if entry.is_file() and entry.suffix == ".h" and not entry.name.endswith("_p.h"):
                    headers.append(str(entry))
            break  # Use first found base only
    return sorted(headers)

def _build_include_all_source(headers: list[str]) -> str:
    """Build a C++ source that includes all given headers."""
    lines = []
    for h in headers:
        name = Path(h).name
        lines.append(f'#include <{name}>')
    return "\n".join(lines)


def _parse_dtk_typedefs() -> dict[str, str]:
    """Parse typedef aliases from dwidgetstype.h.

    DTK defines many widget types as typedefs (e.g. typedef QPushButton DPushButton).
    These don't appear as CLASS_DECL in libclang, so we extract them manually.
    """
    typedefs: dict[str, str] = {}

    # Auto-detect dwidgetstype.h location
    type_h = None
    for base in ["/usr/include/x86_64-linux-gnu/dtk6", "/usr/include/dtk6",
                  "/usr/include/x86_64-linux-gnu/dtk5", "/usr/include/dtk5",
                  "/usr/include/DtkWidget"]:
        candidate = Path(base) / "DWidget" / "dwidgetstype.h"
        if candidate.is_file():
            type_h = candidate
            break
    if type_h is None:
        return typedefs

    import re
    pattern = re.compile(r"typedef\s+(\w+(?:\s*\*)?)\s+(\w+)\s*;")
    with open(type_h) as f:
        for line in f:
            m = pattern.search(line)
            if m:
                src_type = m.group(1).strip()
                dst_type = m.group(2).strip()
                if dst_type.startswith("D") and dst_type[1:].isalpha():
                    typedefs[dst_type] = src_type
    return typedefs

def _extract_classes(tu, source_files: set[str]) -> dict[str, list[str]]:
    """Extract class name → direct base classes from a translation unit.

    Only includes classes defined in the given source_files.
    Handles forward declarations: if a forward decl (no bases) is seen first,
    the real definition (with bases) overwrites it.
    """
    classes: dict[str, list[str]] = {}
    for c in tu.cursor.walk_preorder():
        try:
            loc = c.location
            if not (loc and loc.file):
                continue
            if loc.file.name not in source_files:
                continue
            if c.kind not in (CursorKind.CLASS_DECL, CursorKind.STRUCT_DECL):
                continue
            name = c.spelling
            if not name or name.startswith("_") or name.startswith("Q") or name.startswith("q"):
                continue
            bases: list[str] = []
            for child in c.get_children():
                if child.kind == CursorKind.CXX_BASE_SPECIFIER:
                    bases.append(child.type.spelling)
            if name in classes:
                # Forward declaration seen first (no bases); real definition has bases
                if not classes[name] and bases:
                    classes[name] = bases
            else:
                classes[name] = bases
        except Exception:
            continue
    return classes
def _extract_qt_classes(tu, source_files: set[str]) -> dict[str, list[str]]:
    """Extract Qt class name → direct base classes.

    Qt headers use 'class QFoo : public QBar' pattern.
    """
    classes: dict[str, list[str]] = {}
    for c in tu.cursor.walk_preorder():
        try:
            loc = c.location
            if not (loc and loc.file):
                continue
            if loc.file.name not in source_files:
                continue
            if c.kind not in (CursorKind.CLASS_DECL, CursorKind.STRUCT_DECL):
                continue
            name = c.spelling
            if not name:
                continue
            if not name.startswith("Q"):
                continue
            if name in classes:
                continue
            bases: list[str] = []
            for child in c.get_children():
                if child.kind == CursorKind.CXX_BASE_SPECIFIER:
                    bases.append(child.type.spelling)
            classes[name] = bases
        except Exception:
            continue
    return classes


def _classify(name: str, classes: dict[str, list[str]], memo: dict[str, str] | None = None) -> str:
    """Walk inheritance chain to classify a class.

    Returns 'interactive', 'decorative', 'layout', or 'unknown'.
    """
    if memo is None:
        memo = {}

    if name in memo:
        return memo[name]

    # DTK overrides first (handles QWidget-based interactive widgets)
    if name in DTK_CATEGORY_OVERRIDES:
        memo[name] = DTK_CATEGORY_OVERRIDES[name]
        return DTK_CATEGORY_OVERRIDES[name]

    if name in QT_INTERACTIVE_ROOTS:
        memo[name] = "interactive"
        return "interactive"
    if name in QT_DECORATIVE_ROOTS:
        memo[name] = "decorative"
        return "decorative"
    if name in QT_LAYOUT_ROOTS:
        memo[name] = "layout"
        return "layout"

    bases = classes.get(name, [])
    if not bases:
        memo[name] = "unknown"
        return "unknown"

    for base_spec in bases:
        for b in base_spec.replace(",", " ").split():
            b = b.strip()
            if not b:
                continue
            b = b.strip("; ")
            if not b:
                continue
            if "::" in b:
                b = b.split("::")[-1]
            result = _classify(b, classes, memo)
            if result != "unknown":
                memo[name] = result
                return result

    memo[name] = "unknown"
    return "unknown"

def _find_root(name: str, classes: dict[str, list[str]], memo: dict[str, str] | None = None) -> str:
    """Find the nearest Qt root ancestor for a class."""
    if memo is None:
        memo = {}

    if name in memo:
        return memo[name]

    if name in ALL_QT_ROOTS:
        memo[name] = name
        return name

    bases = classes.get(name, [])
    if not bases:
        memo[name] = ""
        return ""

    for base_spec in bases:
        for b in base_spec.replace(",", " ").split():
            b = b.strip()
            if not b:
                continue
            b = b.strip("; ")
            if not b:
                continue
            if "::" in b:
                b = b.split("::")[-1]
            result = _find_root(b, classes, memo)
            if result:
                memo[name] = result
                return result

    memo[name] = ""
    return ""


def generate_type_db(
    dtk_headers: list[str] | None = None,
    qt_headers: list[str] | None = None,
    output: str | None = None,
) -> dict:
    """Generate the type database JSON."""
    if not _LIBCLANG_READY:
        print("ERROR: libclang not available", file=sys.stderr)
        sys.exit(1)

    index = Index.create()

    # --- Phase 1: Parse DTK headers ---
    print("Parsing DTK DWidget headers...")
    if dtk_headers is None:
        dtk_headers = _find_dtk_headers()
    print(f"  Found {len(dtk_headers)} DTK headers")

    dtk_source = _build_include_all_source(dtk_headers)
    dtk_source_files = set(dtk_headers)

    with tempfile.NamedTemporaryFile(suffix=".cpp", mode="w", delete=False) as f:
        f.write(dtk_source)
        tmp_path = f.name

    include_flags = _detect_include_flags()
    try:
        tu = index.parse(tmp_path, args=include_flags)
        dtk_classes = _extract_classes(tu, dtk_source_files)
    finally:
        os.unlink(tmp_path)

    print(f"  Extracted {len(dtk_classes)} DTK classes")

    # --- Phase 2: Parse Qt headers ---
    print("Parsing Qt6 QtWidgets headers...")
    if qt_headers is None:
        qt_headers = _find_qt_headers()
    print(f"  Found {len(qt_headers)} Qt headers")

    qt_source = _build_include_all_source(qt_headers)
    qt_source_files = set(qt_headers)

    with tempfile.NamedTemporaryFile(suffix=".cpp", mode="w", delete=False) as f:
        f.write(qt_source)
        tmp_path = f.name
    try:
        tu = index.parse(tmp_path, args=include_flags)
        qt_classes = _extract_qt_classes(tu, qt_source_files)
    finally:
        os.unlink(tmp_path)
    print(f"  Extracted {len(qt_classes)} Qt classes")

    # --- Phase 2.5: Parse DTK typedefs ---
    print("Parsing DTK typedefs...")
    dtk_typedefs = _parse_dtk_typedefs()
    print(f"  Found {len(dtk_typedefs)} typedef aliases")

    # --- Phase 3: Merge and classify ---
    all_classes: dict[str, list[str]] = {}
    all_classes.update(qt_classes)
    all_classes.update(dtk_classes)
    # Add typedef aliases (e.g. DPushButton -> QPushButton)
    for dst, src in dtk_typedefs.items():
        if dst not in all_classes:
            all_classes[dst] = [src]

    print("Classifying...")
    classified: dict[str, dict] = {}
    for name in sorted(all_classes):
        bases = all_classes[name]
        category = _classify(name, all_classes)
        root = _find_root(name, all_classes)
        classified[name] = {
            "bases": bases,
            "category": category,
            "root": root,
        }

    # Count by category
    counts: dict[str, int] = {}
    for info in classified.values():
        cat = info["category"]
        counts[cat] = counts.get(cat, 0) + 1

    print(f"  Interactive: {counts.get('interactive', 0)}")
    print(f"  Decorative:  {counts.get('decorative', 0)}")
    print(f"  Layout:      {counts.get('layout', 0)}")
    print(f"  Unknown:     {counts.get('unknown', 0)}")

    # --- Phase 4: Build output ---
    db = {
        "version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "qt_roots": {
            "interactive": sorted(QT_INTERACTIVE_ROOTS),
            "decorative": sorted(QT_DECORATIVE_ROOTS),
            "layout": sorted(QT_LAYOUT_ROOTS),
        },
        "classes": classified,
    }

    if output:
        out_path = Path(output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(db, f, indent=2, sort_keys=True)
        print(f"\nWritten: {out_path}")

    return db


def main():
    parser = argparse.ArgumentParser(
        description="Generate AT-SPI type database from DTK/Qt headers"
    )
    parser.add_argument(
        "--output",
        default=str(Path(__file__).resolve().parent / "type_db.json"),
        help="Output JSON path (default: scripts/type_db.json)",
    )
    args = parser.parse_args()

    generate_type_db(output=args.output)


if __name__ == "__main__":
    main()