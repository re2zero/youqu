# SPDX-FileCopyrightText: 2026 Uniontech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only

"""Import deepin-manual docs for an app, split by ## sections.

Path pattern:
  /usr/share/deepin-manual/manual-assets/application/<app_id>/<doc_id>/<locale>/d_<doc_id>.md

If no manual found, silently skip (does not block pipeline).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_LOCALE_PRIORITY = ("zh_CN", "zh_TW", "en_US")


def _find_manual_dir(app_id: str) -> Path | None:
    base = Path("/usr/share/deepin-manual/manual-assets/application") / app_id
    if not base.exists():
        return None

    for doc_dir in sorted(base.iterdir()):
        if not doc_dir.is_dir():
            continue
        for locale in _LOCALE_PRIORITY:
            locale_dir = doc_dir / locale
            if locale_dir.exists():
                for md in locale_dir.glob("d_*.md"):
                    return md
    return None


def _split_sections(content: str) -> list[tuple[str, str]]:
    """Split markdown by ## headings. Returns [(title, body), ...]."""
    sections: list[tuple[str, str]] = []
    current_title = ""
    current_body: list[str] = []

    for line in content.splitlines():
        if line.startswith("## ") or line.startswith("# "):
            if current_title:
                sections.append((current_title, "\n".join(current_body).strip()))
            current_title = line.lstrip("# ").strip()
            current_body = []
        else:
            current_body.append(line)

    if current_title:
        sections.append((current_title, "\n".join(current_body).strip()))

    return sections


def _slugify(title: str) -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", title).strip("_")
    return cleaned.lower()[:64] or "misc"


def import_manual(app_id: str, output_dir: str) -> dict:
    """Import deepin-manual for app_id, split into docs/modules/<slug>.md.

    Returns {"imported": int, "skipped": bool, "path": str, "reason": str}.
    """
    manual_path = _find_manual_dir(app_id)
    if not manual_path:
        return {
            "imported": 0,
            "skipped": True,
            "reason": f"no manual found for {app_id}",
        }

    content = manual_path.read_text(encoding="utf-8")
    sections = _split_sections(content)

    out = Path(output_dir) / "docs" / "modules"
    out.mkdir(parents=True, exist_ok=True)

    imported = 0
    for title, body in sections:
        slug = _slugify(title)
        md_path = out / f"{slug}.md"
        md_content = f"# {title}\n\n{body}\n"
        md_path.write_text(md_content, encoding="utf-8")
        imported += 1

    return {
        "imported": imported,
        "skipped": False,
        "path": str(out),
        "source": str(manual_path),
    }


def cmd_docs(args) -> None:
    result = import_manual(args.app, args.output)
    if result["skipped"]:
        print(f"  skipped: {result['reason']}")
        return
    print(
        f"  imported {result['imported']} sections from {result['source']}"
        f" -> {result['path']}"
    )
