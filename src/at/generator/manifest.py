# SPDX-FileCopyrightText: 2026 Uniontech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only

"""Manifest generation and update for module-split pipeline."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


def make_module_entry(
    slug: str,
    cases: int,
    has_manual: bool = False,
) -> dict[str, Any]:
    return {
        "name": slug,
        "slug": slug,
        "status": "pending",
        "cases": cases,
        "mapped": 0,
        "selector_coverage": 0.0,
        "has_manual": has_manual,
        "last_error": None,
    }


def build_manifest(
    app: str,
    source: str,
    modules: list[dict[str, Any]],
) -> dict[str, Any]:
    total_cases = sum(m["cases"] for m in modules)
    return {
        "app": app,
        "source": source,
        "created_at": datetime.now().isoformat(),
        "modules": modules,
        "stats": {
            "total_cases": total_cases,
            "total_modules": len(modules),
            "mapped_cases": 0,
            "avg_coverage": 0.0,
        },
    }


def write_manifest(manifest: dict[str, Any], output_dir: str) -> Path:
    out = Path(output_dir) / "manifest.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    content = yaml.dump(
        manifest,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    )
    out.write_text(content, encoding="utf-8")
    return out


def load_manifest(path: str) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def update_module_status(
    manifest: dict[str, Any],
    slug: str,
    status: str,
    mapped: int | None = None,
    selector_coverage: float | None = None,
    last_error: str | None = None,
) -> dict[str, Any]:
    for m in manifest.get("modules", []):
        if m["slug"] == slug:
            m["status"] = status
            if mapped is not None:
                m["mapped"] = mapped
            if selector_coverage is not None:
                m["selector_coverage"] = selector_coverage
            if last_error is not None:
                m["last_error"] = last_error
            break
    _recompute_stats(manifest)
    return manifest


def _recompute_stats(manifest: dict[str, Any]) -> None:
    modules = manifest.get("modules", [])
    total_cases = sum(m["cases"] for m in modules)
    mapped_cases = sum(m.get("mapped", 0) for m in modules)
    coverages = [m.get("selector_coverage", 0.0) for m in modules if m.get("selector_coverage")]
    avg = sum(coverages) / len(coverages) if coverages else 0.0
    stats = manifest.setdefault("stats", {})
    stats["total_cases"] = total_cases
    stats["total_modules"] = len(modules)
    stats["mapped_cases"] = mapped_cases
    stats["avg_coverage"] = round(avg, 4)
