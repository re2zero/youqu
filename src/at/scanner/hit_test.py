# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only

"""Coordinate → AT-SPI element hit-test.

Given an (x, y) screen coordinate and the AT-SPI desktop root,
recursively find the deepest visible element whose bounding box
contains that point.  Reuses ``_SKIP_ROLES`` / ``_STATE_MAP`` /
``_get_node_attrs`` from :mod:`atspi_dumper` to stay consistent
with the tree-dump output schema.

An optional extents cache avoids full-tree traversal on every
click — rebuild it on ``window:activate`` or
``children-changed`` events.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import pyatspi

from src.at.scanner.atspi_dumper import (
    _MAX_NAME_LENGTH,
    _SKIP_ROLES,
    _STATE_MAP,
    _get_node_attrs,
)

logger = logging.getLogger(__name__)

_DESKTOP_COORDS = 0  # pyatspi.DESKTOP_COORDS


def _state_names(obj: Any) -> set[str]:
    """Return the set of AT-SPI state names for *obj*."""
    try:
        states = obj.getState().getStates()
        return {_STATE_MAP.get(s, str(s)) for s in states}
    except Exception:
        return set()


_CONTAINER_ROLES = frozenset({"desktop frame", "application", "filler"})


def _is_visible(obj: Any) -> bool:
    """Check whether *obj* is visible.

    Container roles (desktop frame, application) are structural elements
    that often have empty state sets — always treat them as visible so
    we can recurse into their children.
    """
    try:
        role_name = obj.get_role_name() or ""
    except Exception:
        role_name = ""
    if role_name in _CONTAINER_ROLES:
        return True
    names = _state_names(obj)
    return "visible" in names


def _get_extents(obj: Any) -> Optional[tuple[int, int, int, int]]:
    """Return ``(x, y, width, height)`` in desktop coords, or ``None``."""
    try:
        ext = obj.get_extents(_DESKTOP_COORDS)
        return (ext.x, ext.y, ext.width, ext.height)
    except Exception:
        return None


def _contains(ext: tuple[int, int, int, int], x: int, y: int) -> bool:
    """Check whether screen coordinate *(x, y)* falls inside *ext*."""
    ex, ey, ew, eh = ext
    return ex <= x <= ex + ew and ey <= y <= ey + eh


def _extract_hit_node(obj: Any) -> dict[str, Any]:
    """Extract a lightweight node dict for the hit element.

    Mirrors the schema produced by :func:`atspi_dumper._extract_node`
    but without recursing into children (the caller already knows
    this is the leaf we want).
    """
    try:
        role_name = obj.get_role_name() or "unknown"
        name = obj.get_name() or ""
        object_name, accessible_id = _get_node_attrs(obj)
    except Exception:
        return {"role": "unknown", "name": "", "source": "runtime"}

    try:
        state_names = sorted(_state_names(obj))
    except Exception:
        state_names = []

    try:
        description = obj.description or ""
    except Exception:
        description = ""

    try:
        index_in_parent = obj.getIndexInParent()
    except Exception:
        index_in_parent = -1

    return {
        "role": role_name,
        "name": name[:_MAX_NAME_LENGTH],
        "object_name": object_name,
        "accessible_id": accessible_id,
        "description": description,
        "states": state_names,
        "index_in_parent": index_in_parent,
        "source": "runtime",
    }


def hit_test(x: int, y: int, root: Any) -> Optional[dict[str, Any]]:
    """Recursively find the deepest visible AT-SPI element at *(x, y)*."""
    if root is None:
        return None

    if not _is_visible(root):
        return None

    ext = _get_extents(root)
    try:
        role_name = root.get_role_name() or ""
    except Exception:
        role_name = ""
    is_container = role_name in _CONTAINER_ROLES

    if ext is None:
        if not is_container:
            return None
    elif ext[2] == 0 or ext[3] == 0:
        if not is_container:
            return None
    elif not _contains(ext, x, y):
        return None

    # Recurse into children even for skip-role nodes (e.g. "filler" containers
    # hold real UI elements; skipping them would miss all descendants).
    try:
        child_count = root.get_child_count()
    except Exception:
        child_count = 0

    for i in range(child_count):
        try:
            child = root.get_child_at_index(i)
        except Exception:
            continue
        if child is None:
            continue
        result = hit_test(x, y, child)
        if result is not None:
            return result

    # Only return this node as result if it's not a skip-role.
    if role_name in _SKIP_ROLES:
        return None

    return _extract_hit_node(root)


class ExtentsCache:
    """Flat cache of ``(extents, accessible)`` pairs for fast hit-testing.

    Rebuild on ``window:activate`` or ``children-changed`` events
    to avoid full-tree traversal on every click.  The cache stores
    only visible, non-skip-role elements; ``lookup`` does a linear
    scan and returns the *smallest* enclosing element (proxy for
    "deepest" without tree recursion).
    """

    def __init__(self) -> None:
        self._entries: list[tuple[tuple[int, int, int, int], Any]] = []

    def build(self, root: Any) -> None:
        """Rebuild the cache by walking the full subtree of *root*."""
        self._entries.clear()
        self._walk(root)
        logger.debug("ExtentsCache rebuilt: %d entries", len(self._entries))

    def _walk(self, node: Any) -> None:
        if node is None:
            return
        if not _is_visible(node):
            return
        try:
            role_name = node.get_role_name() or ""
        except Exception:
            role_name = ""
        is_skip = role_name in _SKIP_ROLES
        if not is_skip:
            ext = _get_extents(node)
            if ext is not None and ext[2] > 0 and ext[3] > 0:
                self._entries.append((ext, node))
        # Always walk children — skip-role containers (e.g. "filler")
        # hold real UI elements that must be discovered.
        try:
            count = node.get_child_count()
        except Exception:
            count = 0
        for i in range(count):
            try:
                child = node.get_child_at_index(i)
            except Exception:
                continue
            self._walk(child)

    def lookup(self, x: int, y: int) -> Optional[dict[str, Any]]:
        """Return the smallest visible element containing *(x, y)*."""
        best: Optional[tuple[int, int, int, int]] = None
        best_area: float = float("inf")
        best_node: Any = None
        for ext, node in self._entries:
            if _contains(ext, x, y):
                area = ext[2] * ext[3]
                if area < best_area:
                    best_area = area
                    best = ext
                    best_node = node
        if best_node is None:
            return None
        return _extract_hit_node(best_node)

    def __len__(self) -> int:
        return len(self._entries)
