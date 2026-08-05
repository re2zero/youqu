#!/usr/bin/env python3
"""Menu structure extractor — finds transient AT-SPI elements (menus) in source.

Runtime AT-SPI dumps (dogtail/youqu at dump) CANNOT see transient elements:
context menus, dropdown menus, and main menus only exist while visible.
This scanner statically extracts them from C++ source code:

  1. libclang AST scan: QMenu::addAction()/addMenu() calls + tr() display text
  2. .ts translation merge: (file, line) → Chinese translation for test matching
  3. Output: menu_structure.yaml with English + Chinese names per item

Transient vs persistent coverage:
  - Persistent (at dump): normal widgets — handled by scan_gaps.py
  - Transient (menu_extractor): QMenu/QAction built at runtime —
    m_menu->addAction(tr("Copy")) has no variable name, invisible to dump

Usage:
    menu_extractor.py --src <dir> --compile-commands <cc.json>
        [--ts-dir <translations_dir>] [--ts-lang zh_CN] [--output <dir>]

Output (in <output_dir>):
    menu_structure.yaml — menu tree with EN/ZH text and line locations
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("menu_extractor")

# ---------------------------------------------------------------------------
# libclang bootstrap — same pattern as scan_gaps.py
# ---------------------------------------------------------------------------

_LIBCLANG_CANDIDATES = [
    "/usr/lib/x86_64-linux-gnu", "/usr/lib64", "/usr/lib",
    "/usr/lib/llvm-18/lib", "/usr/lib/llvm-17/lib", "/usr/lib/llvm-19/lib",
]

_libclang_libpath: str | None = None
for _base in _LIBCLANG_CANDIDATES:
    if not Path(_base).is_dir():
        continue
    try:
        for _f in Path(_base).iterdir():
            if "libclang" in _f.name and _f.suffix in (".so", ".so.1"):
                _libclang_libpath = _base
                break
    except OSError:
        continue
    if _libclang_libpath:
        break

if _libclang_libpath:
    _key = "LD_LIBRARY_PATH"
    _old = os.environ.get(_key, "")
    if _libclang_libpath not in _old:
        os.environ[_key] = f"{_libclang_libpath}:{_old}" if _old else _libclang_libpath
    from clang.cindex import Config
    Config.set_library_path(_libclang_libpath)
    _LIBCLANG_READY = True
else:
    _LIBCLANG_READY = False

try:
    from clang.cindex import CursorKind, Index
    _LIBCLANG_IMPORT_OK = True
except ImportError:
    CursorKind = None  # type: ignore
    _LIBCLANG_IMPORT_OK = False


# ---------------------------------------------------------------------------
# .ts translation file parsing
# ---------------------------------------------------------------------------


def load_ts_translations(ts_path: str | Path) -> dict[tuple[str, int], tuple[str, str]]:
    """Parse a Qt Linguist .ts file.

    Returns {(rel_file, line): (source_en, translation_zh)}.
    ``filename`` in <location> is relative to the project root, e.g.
    "../src/views/termwidget.cpp" → "src/views/termwidget.cpp".
    """
    by_line: dict[tuple[str, int], tuple[str, str]] = {}
    try:
        tree = ET.parse(str(ts_path))
    except (ET.ParseError, OSError) as e:
        logger.warning("Failed to parse %s: %s", ts_path, e)
        return by_line

    for ctx in tree.getroot().findall("context"):
        for msg in ctx.findall("message"):
            source = msg.findtext("source", "")
            trans = msg.findtext("translation", "")
            if not source or not trans:
                continue
            for loc in msg.findall("location"):
                fn = loc.get("filename", "")
                if fn.startswith("../"):
                    fn = fn[3:]
                line = int(loc.get("line", 0) or 0)
                if line > 0:
                    by_line[(fn, line)] = (source, trans)
    return by_line


def find_ts_file(ts_dir: str | Path, lang: str) -> str | None:
    """Find the .ts file for a language in a translations directory."""
    d = Path(ts_dir)
    if not d.is_dir():
        return None
    # exact first: deepin-terminal_zh_CN.ts
    for f in sorted(d.glob(f"*_{lang}.ts")):
        return str(f)
    # language-only fallback: deepin-terminal_zh.ts
    lang_base = lang.split("_")[0]
    for f in sorted(d.glob(f"*_{lang_base}.ts")):
        return str(f)
    return None


# ---------------------------------------------------------------------------
# Source scanning (libclang)
# ---------------------------------------------------------------------------


def _parse_with_flags(cc_entry: dict):
    """Parse a translation unit with compile flags from compile_commands.json."""
    flags = []
    parts = cc_entry["command"].split()
    skip_next = False
    for p in parts:
        if skip_next:
            skip_next = False
            continue
        if p == "-c":
            continue
        if p in ("-o", "-MQ", "-MF", "-MT"):
            skip_next = True
            continue
        if p.startswith("-o") or p.endswith(".o") or p.endswith(".obj"):
            continue
        if p == cc_entry["file"] or p in ("-MD", "-MMD", "-MP"):
            continue
        flags.append(p)
    return Index.create().parse(cc_entry["file"], args=flags)


def _translate_text(cursor) -> str:
    """Resolve display text from a qApp->translate(ctx, TEXT) call.

    Child layout (libclang): [0]=receiver chain, [1]=context string,
    [2]=display text (string literal OR constexpr const char* constant).
    Collects all string/constant candidates, skips the FIRST (context),
    returns the next one found.
    """
    candidates: list[str] = []
    for ch in cursor.get_children():
        for s in ch.walk_preorder():
            try:
                if s.kind == CursorKind.STRING_LITERAL:
                    candidates.append(s.spelling.strip('"'))
                elif s.kind == CursorKind.DECL_REF_EXPR and s.spelling:
                    ref = s.referenced
                    if ref:
                        # resolve constexpr constant: value may be nested
                        # (VAR_DECL → UNEXPOSED_EXPR → STRING_LITERAL)
                        for gc in ref.walk_preorder():
                            if gc.kind == CursorKind.STRING_LITERAL:
                                candidates.append(gc.spelling.strip('"'))
                                break
            except Exception:
                pass
    # candidates: [receiver-instance(no str), context, display-text, ...]
    # drop receiver noise, skip first real string (context), take next
    real = [c for c in candidates if c]
    return real[1] if len(real) >= 2 else ""


def _has_tr_call(child_cursor) -> str | None:
    """If child_cursor's subtree contains a tr() call, return its string literal.

    Handles both resolved (CALL_EXPR spelling='tr') and unresolved
    (OVERLOADED_DECL_REF 'tr' inside UNEXPOSED_EXPR) forms.
    """
    try:
        for c in child_cursor.walk_preorder():
            # Pattern A: fully resolved — CALL_EXPR with spelling="tr"
            if c.kind == CursorKind.CALL_EXPR and c.spelling == "tr":
                for sib in c.get_children():
                    if sib.kind == CursorKind.STRING_LITERAL:
                        t = sib.spelling.strip('"')
                        if t:
                            return t
            # Pattern B: unresolved/incomplete type —
            # OVERLOADED_DECL_REF "tr" with STRING_LITERAL sibling
            if c.kind == CursorKind.OVERLOADED_DECL_REF and c.spelling == "tr":
                # The STRING_LITERAL is a sibling at the same level
                # as the tr() reference, not nested inside it.
                # Collect all strings in this subtree and return the first.
                for gc in child_cursor.walk_preorder():
                    if gc.kind == CursorKind.STRING_LITERAL:
                        t = gc.spelling.strip('"')
                        if t:
                            return t
    except Exception:
        pass
    return None


def _get_first_nested_string(child_cursor) -> str | None:
    """Return the first string literal nested in child_cursor, or None."""
    try:
        for gc in child_cursor.walk_preorder():
            if gc.kind == CursorKind.STRING_LITERAL:
                t = gc.spelling.strip('"')
                if t:
                    return t
    except Exception:
        pass
    return None


def _string_literal(cursor) -> str:
    """Extract display text from a CALL_EXPR (e.g. addAction).

    Strategy: iterate through each direct child (each argument to the call).
    Return the first string argument that is wrapped in tr(), or the first
    plain-string argument.  Never returns an icon path or other non-text arg.
    """
    # Priority 1: translate(ctx, TEXT) — resolve its 2nd arg
    try:
        for c in cursor.walk_preorder():
            if c.kind == CursorKind.CALL_EXPR and (c.spelling or "").endswith("translate"):
                t = _translate_text(c)
                if t:
                    return t
    except Exception:
        pass

    # Priority 2: for each direct child (argument position), check for tr() text.
    # Return the FIRST argument that contains tr() — this is the display text,
    # regardless of argument position.
    for child in cursor.get_children():
        t = _has_tr_call(child)
        if t:
            return t

    # Priority 3: first direct-child STRING_LITERAL (plain string argument)
    for c in cursor.get_children():
        if c.kind == CursorKind.STRING_LITERAL:
            t = c.spelling.strip('"')
            if t:
                return t

    # Priority 4: first nested string in first child (fallback)
    for c in cursor.get_children():
        t = _get_first_nested_string(c)
        if t:
            return t

    return ""


def _has_string_literal(cursor) -> bool:
    """Whether the cursor subtree contains any string literal."""
    for c in cursor.walk_preorder():
        try:
            if c.kind == CursorKind.STRING_LITERAL:
                return True
        except Exception:
            pass
    return False


def _receiver_of(member_ref) -> str:
    """Receiver variable of a member call: m_menu->addAction(...) → m_menu."""
    for ch in member_ref.get_children():
        if ch.kind == CursorKind.UNEXPOSED_EXPR:
            for gc in ch.walk_preorder():
                if gc.kind in (CursorKind.MEMBER_REF_EXPR, CursorKind.DECL_REF_EXPR) and gc.spelling:
                    return gc.spelling
    return ""


class MenuItem:
    """A single addAction/addMenu/addSeparator call on a QMenu."""

    __slots__ = ("file", "line", "receiver", "method", "text_en", "arg_var")

    def __init__(self, file: str, line: int, receiver: str, method: str,
                 text_en: str, arg_var: str = ""):
        self.file = file
        self.line = line
        self.receiver = receiver
        self.method = method          # addAction | addMenu | addSeparator
        self.text_en = text_en
        self.arg_var = arg_var        # for addMenu: the submenu variable


def _scan_file_menus(tu, src_name: str) -> list[MenuItem]:
    """Extract addAction/addMenu calls from a parsed translation unit."""
    items: list[MenuItem] = []

    def walk(cursor, parent=None, depth: int = 0):
        if depth > 60:
            return
        try:
            loc = cursor.location
            f = loc.file.name if loc and loc.file else ""
            if f and not f.endswith(src_name):
                return
            line = loc.line if loc else 0

            # Pattern A: addMenu with real spelling (m_menu->addMenu(search))
            if cursor.kind == CursorKind.CALL_EXPR and (cursor.spelling or "") == "addMenu":
                mems = [ch for ch in cursor.get_children()
                        if ch.kind == CursorKind.MEMBER_REF_EXPR]
                recv = _receiver_of(mems[0]) if mems else ""
                arg = ""
                for ch in cursor.get_children():
                    for gc in ch.walk_preorder():
                        if gc.kind == CursorKind.DECL_REF_EXPR and gc.spelling:
                            arg = gc.spelling
                            break
                    if arg:
                        break
                # local alias (QMenu *menu = m_menu) → same receiver, skip self-ref
                if arg and arg != recv:
                    items.append(MenuItem(src_name, line, recv, "addMenu",
                                          _string_literal(cursor), arg))

            # Pattern B: addAction via empty MEMBER_REF_EXPR (incomplete type)
            #   m_menu->addAction(tr("Copy"), ...) parses as:
            #   MEMBER_REF_EXPR(empty) → UNEXPOSED(m_menu) + OVERLOADED_DECL_REF(addAction)
            if cursor.kind == CursorKind.MEMBER_REF_EXPR and not (cursor.spelling or ""):
                kids = list(cursor.get_children())
                if len(kids) == 2:
                    method = ""
                    for k in kids:
                        if k.kind == CursorKind.OVERLOADED_DECL_REF:
                            method = k.spelling or ""
                    if method == "addAction":
                        recv = _receiver_of(cursor)
                        # Only NEW menu items: the call must contain a string
                        # literal (text or tr()). addAction(actionVar) adds an
                        # existing QAction — not a menu item — skip it.
                        if parent is not None and _has_string_literal(parent):
                            text = _string_literal(parent)
                            items.append(MenuItem(src_name, line, recv, "addAction", text, ""))

            # Pattern C: addAction with real spelling (fully resolved types)
            if cursor.kind == CursorKind.CALL_EXPR and (cursor.spelling or "") == "addAction":
                mems = [ch for ch in cursor.get_children()
                        if ch.kind == CursorKind.MEMBER_REF_EXPR]
                recv = _receiver_of(mems[0]) if mems else ""
                # only NEW menu items (has text literal); addAction(actionVar)
                # on QActionGroup or menus adds existing actions — skip
                if _has_string_literal(cursor):
                    items.append(MenuItem(src_name, line, recv, "addAction",
                                          _string_literal(cursor), ""))
        except Exception:
            pass

        for ch in cursor.get_children():
            walk(ch, cursor, depth + 1)

    walk(tu.cursor)
    return items


# ---------------------------------------------------------------------------
# Translation merge
# ---------------------------------------------------------------------------


def translate_item(it: MenuItem, ts_by_line: dict) -> str:
    """Look up Chinese translation for a menu item via (file, line) + text check.

    Matching strategy (in order):
      1. Exact (file, line) match.
      2. Path-suffix match: item.file ends with ts filename, same line + source text.
      3. Same line + same source text (last resort, cross-file collision possible).
    """
    if not it.text_en or not it.line:
        return ""

    # 1. Exact match
    hit = ts_by_line.get((it.file, it.line))
    if hit and hit[0] == it.text_en:
        return hit[1]

    # 2. Path-suffix match: item.file="src/views/w.cpp", ts key fn="views/w.cpp" → ends with
    for (fn, ln), (src_en, trans) in ts_by_line.items():
        if ln == it.line and src_en == it.text_en:
            if fn.endswith(it.file) or it.file.endswith(fn):
                return trans

    # 3. Last resort: same line + same text (cross-file collision possible)
    for (fn, ln), (src_en, trans) in ts_by_line.items():
        if ln == it.line and src_en == it.text_en:
            return trans

    return ""


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Extract transient menu structure (EN+ZH) from C++ Qt/DTK source",
    )
    parser.add_argument("--src", required=True, help="Source directory (must be repo root)")
    parser.add_argument("--compile-commands", required=True,
                        help="Path to compile_commands.json")
    parser.add_argument("--ts-dir", help="Translations directory containing .ts files")
    parser.add_argument("--ts-lang", default="zh_CN", help="Target language (default: zh_CN)")
    parser.add_argument("--output", "-o", default=".", help="Output directory")
    args = parser.parse_args()

    if not (_LIBCLANG_READY and _LIBCLANG_IMPORT_OK):
        logger.error("libclang not available. Install: sudo apt install python3-clang-18 libclang-18-dev")
        return 1

    cc_path = Path(args.compile_commands)
    if not cc_path.is_file():
        logger.error("compile_commands.json not found: %s", cc_path)
        return 1
    entries = json.loads(cc_path.read_text())

    ts_by_line: dict = {}
    if args.ts_dir:
        ts_file = find_ts_file(args.ts_dir, args.ts_lang)
        if ts_file:
            ts_by_line = load_ts_translations(ts_file)
            logger.info("Loaded translations: %s (%d entries)", ts_file, len(ts_by_line))
        else:
            logger.warning("No .ts file for language %s in %s", args.ts_lang, args.ts_dir)

    src_root = Path(args.src).resolve()
    all_items: list[MenuItem] = []
    for entry in entries:
        file_path = entry.get("file", "")
        if not file_path.endswith((".cpp", ".cxx", ".cc")):
            continue
        try:
            rel = Path(file_path).resolve().relative_to(src_root)
        except ValueError:
            continue
        try:
            tu = _parse_with_flags(entry)
        except Exception as e:
            logger.warning("Parse failed %s: %s", file_path, e)
            continue
        items = _scan_file_menus(tu, str(rel))
        if items:
            logger.info("%s: %d menu calls", rel, len(items))
            all_items.extend(items)

    if not all_items:
        logger.warning("No menu calls found in %s", args.src)

    # Group by receiver variable
    by_receiver: dict[str, list[MenuItem]] = {}
    for it in all_items:
        by_receiver.setdefault(it.receiver, []).append(it)

    # submenu parent links: addMenu(arg) → parent receiver
    submenu_of: dict[str, str] = {}
    for it in all_items:
        if it.method == "addMenu" and it.arg_var:
            submenu_of[it.arg_var] = it.receiver

    data = {
        "version": "1.0",
        "generated_by": "menu_extractor.py",
        "summary": {
            "menu_calls": len(all_items),
            "translation_lang": args.ts_lang,
            "translation_entries": len(ts_by_line),
        },
        "menus": [],
    }

    total_items = 0
    with_zh = 0
    for recv, recv_items in sorted(by_receiver.items()):
        entries_out = []
        for it in sorted(recv_items, key=lambda x: (x.file, x.line)):
            if it.method == "addSeparator":
                entries_out.append({"type": "separator", "text_en": "", "text_zh": "", "line": it.line})
                continue
            zh = translate_item(it, ts_by_line)
            total_items += 1
            if zh:
                with_zh += 1
            entries_out.append({
                "type": it.method,          # addAction | addMenu
                "text_en": it.text_en,
                "text_zh": zh,
                "file": it.file,
                "line": it.line,
            })
        data["menus"].append({
            "menu_var": recv,
            "parent_var": submenu_of.get(recv, ""),
            "items": entries_out,
        })

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "menu_structure.yaml"
    try:
        import yaml
    except ImportError:
        logger.error("PyYAML not installed. Run: pip install pyyaml")
        return 1
    with open(out_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    logger.info("Written %s", out_path)
    print(f"  Menu structure: {len(data['menus'])} menus, {total_items} items, "
          f"{with_zh} with Chinese translation "
          f"({with_zh / total_items * 100:.0f}% if total_items else 0)")
    return 0


if __name__ == "__main__":
    sys.exit(main())