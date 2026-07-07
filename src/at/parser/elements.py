# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml


class ElementRef:
    def __init__(self, elements_path: str | Path):
        self._elements = self._load(Path(elements_path))

    @staticmethod
    def _load(path: Path) -> dict[str, dict[str, Any]]:
        if not path.is_file():
            return {}
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data.get("elements", {})

    def resolve(self, ref: str) -> dict[str, Any] | None:
        return self._elements.get(ref)

    def resolve_selector(self, ref: str) -> dict[str, Any] | None:
        entry = self.resolve(ref)
        if entry is None:
            return None
        selector = {}
        for key in ("name", "role", "name_pattern"):
            if key in entry:
                selector[key] = entry[key]
        return selector or None
