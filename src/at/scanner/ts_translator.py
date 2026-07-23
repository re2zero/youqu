# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only

"""Qt .ts translation file parser.

Parses Qt translation files (.ts) and provides lookup from
(source_text, context) → translated_text for target language.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TsTranslation:
    """A translation entry from a .ts file."""

    context: str  # <name> element (usually class name)
    source: str  # <source> element (original text)
    translation: str  # <translation> element (translated text)
    location: str  # <location filename="..." line="..."/>


def parse_ts_file(ts_path: str) -> list[TsTranslation]:
    """Parse a .ts file and extract all translation entries.

    Args:
        ts_path: Path to the .ts file.

    Returns:
        List of TsTranslation entries. Empty list on parse failure.
    """
    import xml.etree.ElementTree as ET

    path = Path(ts_path)
    if not path.is_file():
        return []

    try:
        tree = ET.parse(str(path))
        root = tree.getroot()
    except ET.ParseError as e:
        logger.warning("Failed to parse %s: %s", ts_path, e)
        return []

    translations = []

    for context in root.findall("context"):
        name_elem = context.find("name")
        context_name = name_elem.text if name_elem is not None else ""

        for message in context.findall("message"):
            source_elem = message.find("source")
            trans_elem = message.find("translation")
            loc_elem = message.find("location")

            if source_elem is None or not source_elem.text:
                continue

            source_text = source_elem.text.strip()
            translation_text = ""

            if trans_elem is not None and trans_elem.text:
                translation_text = trans_elem.text.strip()

            location = ""
            if loc_elem is not None:
                filename = loc_elem.get("filename", "")
                line = loc_elem.get("line", "")
                location = f"{filename}:{line}" if filename else ""

            translations.append(
                TsTranslation(
                    context=context_name,
                    source=source_text,
                    translation=translation_text,
                    location=location,
                )
            )

    return translations


class TsTranslator:
    """Translation lookup from .ts files.

    Usage:
        translator = TsTranslator("/path/to/translations", target_lang="zh_CN")
        translated = translator.translate("Close tab", context="TabBar")
        # Returns "关闭标签页" or "Close tab" if not found
    """

    def __init__(self, translations_dir: str, target_lang: str = "zh_CN"):
        self.translations_dir = Path(translations_dir)
        self.target_lang = target_lang
        self._entries: list[TsTranslation] = []
        self._index: dict[tuple[str, str], str] = {}  # (context, source) → translation

        self._load()

    def _load(self):
        """Load all .ts files matching the target language."""
        if not self.translations_dir.is_dir():
            logger.warning(
                "Translations directory not found: %s", self.translations_dir
            )
            return

        # Find .ts files matching target language (e.g., *_zh_CN.ts)
        pattern = f"*_{self.target_lang}.ts"
        ts_files = list(self.translations_dir.glob(pattern))

        if not ts_files:
            logger.warning(
                "No .ts files found for %s in %s",
                self.target_lang,
                self.translations_dir,
            )
            return

        for ts_file in ts_files:
            entries = parse_ts_file(str(ts_file))
            self._entries.extend(entries)
            for entry in entries:
                self._index[(entry.context, entry.source)] = entry.translation

        logger.info(
            "Loaded %d translations from %d .ts files",
            len(self._entries),
            len(ts_files),
        )

    def translate(self, source_text: str, context: str = "") -> str:
        """Translate source text using the loaded .ts entries.

        Args:
            source_text: Original English text from tr()
            context: Context (usually class name) for disambiguation

        Returns:
            Translated text, or original source_text if not found.
        """
        # Try with context first
        key = (context, source_text)
        if key in self._index:
            return self._index[key]

        # Try without context (some entries may not have specific context)
        key_no_ctx = ("", source_text)
        if key_no_ctx in self._index:
            return self._index[key_no_ctx]

        # Fallback: search all entries with matching source
        for entry in self._entries:
            if entry.source == source_text and entry.translation:
                return entry.translation

        # Not found — return original
        return source_text

    def get_entries(self) -> list[dict[str, Any]]:
        """Get all translation entries as dicts."""
        return [
            {
                "context": e.context,
                "source": e.source,
                "translation": e.translation,
                "location": e.location,
            }
            for e in self._entries
        ]


def find_ts_files(src_dir: str, target_lang: str = "zh_CN") -> list[str]:
    """Find .ts translation files in a source directory.

    Searches:
    - <src_dir>/translations/*_<lang>.ts
    - <src_dir>/*_<lang>.ts
    - <src_dir>/../translations/*_<lang>.ts (parent directory)
    - <src_dir>/**/*_<lang>.ts (excluding build dirs)

    Args:
        src_dir: Root directory to search.
        target_lang: Language code (e.g., "zh_CN").

    Returns:
        List of .ts file paths.
    """
    root = Path(src_dir)
    if not root.is_dir():
        return []

    ts_files = []
    skip_dirs = {"build", "CMakeFiles", ".cmake", "_build"}
    pattern = f"*_{target_lang}.ts"

    # Check translations directory in src_dir
    trans_dir = root / "translations"
    if trans_dir.is_dir():
        for f in trans_dir.glob(pattern):
            ts_files.append(str(f))

    # Check parent directory's translations (common for src/ subdirectory)
    parent_trans = root.parent / "translations"
    if parent_trans.is_dir() and parent_trans != trans_dir:
        for f in parent_trans.glob(pattern):
            ts_files.append(str(f))

    # Also search recursively (excluding build dirs)
    for f in root.rglob(pattern):
        if any(part in skip_dirs for part in f.parts):
            continue
        if str(f) not in ts_files:
            ts_files.append(str(f))

    return ts_files
