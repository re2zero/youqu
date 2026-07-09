# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only

"""Runtime AT-SPI tree dumper using pyatspi2.

Independent implementation — does not import from src/dogtail_utils.py.
Outputs structured dicts matching AtTreeNode schema (id field omitted;
assigned later by merger.py).

Reference: src/atspi_inspector.py (noise filtering), src/depends/dogtail/tree.py (pyatspi API).
"""

from __future__ import annotations

import logging
import time
from typing import Any

import pyatspi

logger = logging.getLogger(__name__)

_SKIP_ROLES: frozenset[str] = frozenset(
    {
        "unknown",
        "invalid",
        "scroll bar",
        "scroll bar horizontal",
        "scroll bar vertical",
        "separator",
        "divider",
        "filler",
    }
)

_MAX_DEPTH = 15
_MAX_CHILDREN_PER_NODE = 100
_MAX_NAME_LENGTH = 100

# Build reverse map: state int → name (e.g. STATE_SHOWING → "showing")
_STATE_MAP: dict[int, str] = {
    getattr(pyatspi, attr): attr.replace("STATE_", "").lower()
    for attr in dir(pyatspi)
    if attr.startswith("STATE_") and isinstance(getattr(pyatspi, attr), int)
}


def _get_node_attrs(obj: pyatspi.Accessible) -> tuple[str, str]:
    """Extract object_name and accessible_id from AT-SPI object attributes.

    AT-SPI attributes are a semicolon-separated ``"key:value"`` string
    (Qt/DTK apps expose ``object-name`` for QWidget.objectName and
    ``accessible-id`` there).

    Returns (object_name, accessible_id).
    """
    object_name = ""
    accessible_id = ""
    try:
        raw = obj.get_attributes()
        if not raw:
            return object_name, accessible_id
        for attr in raw.split(";"):
            kv = attr.strip().split(":", 1)
            if len(kv) != 2:
                continue
            key, value = kv[0].strip(), kv[1].strip()
            if key == "object-name":
                object_name = value
            elif key == "accessible-id":
                accessible_id = value
    except Exception:
        pass
    return object_name, accessible_id


def _extract_node(obj: pyatspi.Accessible, depth: int, stats: dict[str, int]) -> dict[str, Any]:
    """Recursively extract one AT-SPI node into a dict matching AtTreeNode schema (no id)."""
    stats["total"] += 1

    try:
        role_name = obj.get_role_name() or "unknown"
        name = obj.get_name() or ""
        object_name, accessible_id = _get_node_attrs(obj)
    except Exception:
        stats["errors"] += 1
        return {"role": "unknown", "name": "", "source": "runtime"}

    try:
        state_set = obj.getState()
        state_names = sorted(
            _STATE_MAP.get(s, str(s)) for s in state_set.getStates()
        )
    except Exception:
        state_names = []

    try:
        description = obj.description or ""
    except Exception:
        description = ""

    try:
        action_iface = obj.queryAction()
        actions = [
            action_iface.getName(i)
            for i in range(action_iface.nActions)
            if action_iface.getName(i)
        ]
    except Exception:
        actions = []

    try:
        index_in_parent = obj.getIndexInParent()
    except Exception:
        index_in_parent = -1

    node: dict[str, Any] = {
        "role": role_name,
        "name": name[:_MAX_NAME_LENGTH],
        "object_name": object_name,
        "accessible_id": accessible_id,
        "description": description,
        "actions": actions,
        "index_in_parent": index_in_parent,
        "states": state_names,
        "source": "runtime",
    }

    if depth < _MAX_DEPTH:
        children: list[dict[str, Any]] = []
        try:
            child_count = obj.get_child_count()
            limit = min(child_count, _MAX_CHILDREN_PER_NODE)
            for i in range(limit):
                try:
                    child = obj.get_child_at_index(i)
                    if child is None:
                        continue
                    child_role = child.get_role_name() or ""
                    if child_role in _SKIP_ROLES:
                        stats["skipped"] += 1
                        continue
                    children.append(_extract_node(child, depth + 1, stats))
                except Exception:
                    stats["errors"] += 1
                    continue
        except Exception:
            stats["errors"] += 1

        if children:
            node["children"] = children

    return node


def dump_at_spi_tree(app_name: str) -> list[dict[str, Any]]:
    """Dump the AT-SPI tree for a running app. Returns list of window dicts (AtTreeNode schema, no id)."""
    stats: dict[str, int] = {
        "total": 0,
        "skipped": 0,
        "errors": 0,
    }
    t0 = time.monotonic()

    desktop = pyatspi.Registry.getDesktop(0)
    windows: list[dict[str, Any]] = []

    try:
        app_count = desktop.get_child_count()
    except Exception:
        logger.error("Failed to query desktop child count")
        return windows

    for i in range(app_count):
        try:
            app = desktop.get_child_at_index(i)
        except Exception:
            continue

        if app is None or app.get_name() != app_name:
            continue

        logger.info("Found application '%s' (desktop index %d)", app_name, i)

        try:
            window_count = app.get_child_count()
        except Exception:
            window_count = 0

        for j in range(min(window_count, _MAX_CHILDREN_PER_NODE)):
            try:
                child = app.get_child_at_index(j)
                if child is None:
                    continue
                child_role = child.get_role_name() or ""
                if child_role in _SKIP_ROLES:
                    continue
                windows.append(_extract_node(child, depth=0, stats=stats))
            except Exception:
                stats["errors"] += 1
                continue

        break

    elapsed = time.monotonic() - t0
    if windows:
        logger.info(
            "Dumped %d window(s), %d nodes total (%d skipped, %d errors) in %.2fs",
            len(windows),
            stats["total"],
            stats["skipped"],
            stats["errors"],
            elapsed,
        )
    else:
        logger.warning("Application '%s' not found in AT-SPI tree", app_name)

    return windows
