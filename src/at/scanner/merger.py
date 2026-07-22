# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only

"""Merge static C++ skeleton with runtime AT-SPI dump into unified at-tree.yaml."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import yaml

from src.at.scanner.clang_scanner import _ALL_UI_CLASSES

logger = logging.getLogger(__name__)

# Roles that are noise when they appear as leaf nodes (no children).
# Containers with these roles are kept if they have children (structural).
_NOISE_LEAF_ROLES: frozenset[str] = frozenset(
    {
        "panel",
        "form",
        "scroll pane",
        "viewport",
        "label",
        "table cell",
    }
)

# Name patterns that indicate auto-generated or non-interactive nodes.
_NOISE_NAME_PATTERNS: list[re.Pattern] = [
    re.compile(r"^Form_"),
    re.compile(r"^qt_"),
    re.compile(r"^\d+$"),
    re.compile(r"^DMainWindow$"),
    re.compile(r"^DTitlebar"),
]

_INTERACTIVE_ROLES: frozenset[str] = frozenset(
    {
        "push button",
        "check box",
        "radio button",
        "toggle button",
        "combo box",
        "entry",
        "text",
        "spin button",
        "slider",
        "list item",
        "menu item",
        "menu",
        "tab",
        "tree item",
        "tree",
        "link",
        "button",
        "page tab",
        "page tab list",
    }
)

# AT-SPI actions that are system-level, not user-facing.
# Nodes with only these actions are containers, not interactive controls.
_NON_USER_ACTIONS: frozenset[str] = frozenset(
    {
        "SetFocus",
        "SetSelected",
        "ClearSelection",
        "SelectAll",
        "DeselectAll",
        "GrabFocus",
        "Focus",
    }
)


def _is_noise_leaf(node: dict) -> bool:
    if node.get("children"):
        return False
    return not node.get("name") and not node.get("object_name") and not node.get("accessible_id")


def _is_noise_name(node: dict) -> bool:
    name = node.get("name", "")
    if not name:
        return False
    return any(p.match(name) for p in _NOISE_NAME_PATTERNS)


def _is_noise_node(node: dict) -> bool:
    """Determine if a node is noise (should be filtered from the tree)."""
    if _is_noise_leaf(node):
        return True
    role = node.get("role", "")
    if role in _NOISE_LEAF_ROLES and not node.get("children"):
        return True
    if _is_noise_name(node) and not node.get("children"):
        return True
    return False


def append_scan_entry(path: str, entry: dict) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write("---\n")
        yaml.dump(entry, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def filter_noise(tree: list[dict]) -> list[dict]:
    def _filter_recursive(nodes: list[dict]) -> list[dict]:
        result = []
        for node in nodes:
            if _is_noise_node(node):
                continue
            if "children" in node:
                node["children"] = _filter_recursive(node["children"])
                if not node["children"] and node.get("role", "") in _NOISE_LEAF_ROLES:
                    continue
            result.append(node)
        return result

    return _filter_recursive(tree)


def classify_nodes(tree: list[dict]) -> None:

    def _classify(node: dict) -> None:
        actions = node.get("actions", [])
        role = node.get("role", "")
        user_actions = [a for a in actions if a not in _NON_USER_ACTIONS]
        if user_actions or role in _INTERACTIVE_ROLES:
            node["classification"] = "interactive"
        else:
            node["classification"] = "container"
        for child in node.get("children", []):
            _classify(child)

    for node in tree:
        _classify(node)


def write_runtime_dump(
    runtime_tree: list[dict], path: str, app_name: str = "", state_label: str = ""
) -> None:
    data: dict[str, Any] = {
        "version": "1.0",
        "app": app_name,
        "type": "state" if state_label else "runtime",
    }
    if state_label:
        data["state_label"] = state_label
    data["tree"] = runtime_tree
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def write_static_dump(classes: list[dict], path: str) -> None:
    data = {"version": "1.0", "type": "static", "classes": classes}
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def generate_name_gaps_report(classes: list[dict], path: str, app_name: str = "") -> dict[str, Any]:
    ui_classes = [c for c in classes if _is_ui_widget(c)]
    gaps = []
    for cls in ui_classes:
        if cls.get("object_names") or cls.get("accessible_names"):
            continue
        gaps.append(
            {
                "class_name": cls.get("class_name", ""),
                "source_file": cls.get("source_file", ""),
                "base_classes": cls.get("base_classes", []),
                "object_names": cls.get("object_names", []),
                "accessible_names": cls.get("accessible_names", []),
                "dtk_instantiations": cls.get("dtk_instantiations", []),
            }
        )
    total_ui = len(ui_classes)
    report = {
        "version": "1.0",
        "app": app_name,
        "summary": {
            "total_ui_classes": total_ui,
            "classes_with_names": total_ui - len(gaps),
            "classes_missing_names": len(gaps),
        },
        "gaps": gaps,
    }
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(report, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    return report


def _assign_ids(nodes: list[dict], prefix: str = "n", counter: list[int] | None = None) -> None:
    if counter is None:
        counter = [0]
    for node in nodes:
        node["id"] = f"{prefix}{counter[0]}"
        counter[0] += 1
        if "children" in node:
            _assign_ids(node["children"], prefix, counter)


def _build_static_index(static_classes: list[dict]) -> dict[str, dict]:
    index: dict[str, dict] = {}
    for cls in static_classes:
        for on in cls.get("object_names", []):
            if on:
                index[on] = cls
    return index


def _flatten_runtime_tree(nodes: list[dict]) -> list[dict]:
    flat: list[dict] = []
    for node in nodes:
        flat.append(node)
        if "children" in node:
            flat.extend(_flatten_runtime_tree(node["children"]))
    return flat


_NODE_DEFAULTS: dict[str, Any] = {
    "role": "",
    "name": "",
    "object_name": "",
    "accessible_id": "",
    "description": "",
    "actions": [],
    "index_in_parent": -1,
    "states": [],
    "state_labels": [],
    "source": "runtime",
    "class_name": "",
    "comment": "",
    "annotation_status": "draft",
    "classification": "",
}

_NODE_KEY_ORDER = [
    "id",
    "role",
    "name",
    "object_name",
    "accessible_id",
    "description",
    "actions",
    "index_in_parent",
    "states",
    "state_labels",
    "source",
    "class_name",
    "children",
]


def _identity_key(node: dict) -> tuple[str, str, str, str]:
    return (
        node.get("role", ""),
        node.get("name", ""),
        node.get("object_name", ""),
        node.get("accessible_id", ""),
    )


def _has_name(node: dict) -> bool:
    return bool(node.get("name") or node.get("object_name") or node.get("accessible_id"))


def _merge_duplicate(base: dict, dup: dict) -> None:
    existing_states = set(base.get("states", []))
    for st in dup.get("states", []):
        if st not in existing_states:
            base.setdefault("states", []).append(st)
            existing_states.add(st)
    for sl in dup.get("state_labels", []):
        if sl not in base.setdefault("state_labels", []):
            base["state_labels"].append(sl)
    if "children" in dup:
        if "children" not in base:
            base["children"] = []
        _dedup_into(base["children"], dup["children"])


def _dedup_into(base_nodes: list[dict], new_nodes: list[dict]) -> None:
    for new_node in new_nodes:
        if not _has_name(new_node):
            base_nodes.append(new_node)
            continue
        key = _identity_key(new_node)
        for b in base_nodes:
            if _identity_key(b) == key and _has_name(b):
                _merge_duplicate(b, new_node)
                break
        else:
            base_nodes.append(new_node)


def dedup_runtime_tree(tree: list[dict]) -> list[dict]:
    """Merge root nodes with the same non-anonymous identity key.

    Only merges when the identity key has at least one non-empty identifying
    field (name, object_name, or accessible_id). Fully anonymous nodes are
    kept separate — the identity key cannot distinguish same-element
    duplicates from different unnamed elements.
    """
    result: list[dict] = []
    index: dict[tuple, int] = {}

    for node in tree:
        if not _has_name(node):
            result.append(node)
            continue
        key = _identity_key(node)
        if key not in index:
            result.append(node)
            index[key] = len(result) - 1
        else:
            _merge_duplicate(result[index[key]], node)

    return result


def _normalize_node(node: dict) -> None:
    for key, default in _NODE_DEFAULTS.items():
        if key not in node:
            node[key] = default
    if "children" in node:
        for child in node["children"]:
            _normalize_node(child)


def _normalize_tree(tree: list[dict]) -> None:
    for node in tree:
        _normalize_node(node)


def load_state_snapshots(states_dir: str) -> list[tuple[str, list[dict]]]:
    dir_path = Path(states_dir)
    if not dir_path.is_dir():
        return []

    snapshots: list[tuple[str, list[dict]]] = []
    for f in sorted(dir_path.glob("*.yaml")):
        with open(f, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        if data and "tree" in data:
            label = data.get("state_label", f.stem)
            snapshots.append((label, data["tree"]))
    return snapshots


def _merge_one_state(
    base_nodes: list[dict],
    state_nodes: list[dict],
    state_label: str,
) -> None:
    for s_node in state_nodes:
        s_key = _identity_key(s_node)
        matched = None
        for b_node in base_nodes:
            if _identity_key(b_node) == s_key:
                matched = b_node
                break

        if matched:
            if "state_labels" not in matched:
                matched["state_labels"] = []
            if state_label not in matched["state_labels"]:
                matched["state_labels"].append(state_label)
            existing_states = set(matched.get("states", []))
            for st in s_node.get("states", []):
                if st not in existing_states:
                    matched.setdefault("states", []).append(st)
                    existing_states.add(st)
            if "children" in s_node:
                if "children" not in matched:
                    matched["children"] = []
                _merge_one_state(matched["children"], s_node["children"], state_label)
        else:
            new_node = dict(s_node)
            if "children" in s_node:
                new_node["children"] = [dict(c) for c in s_node["children"]]
            new_node["state_labels"] = [state_label]
            base_nodes.append(new_node)


def merge_state_snapshots(
    base_tree: list[dict],
    state_snapshots: list[tuple[str, list[dict]]],
) -> list[dict]:
    result = [dict(n) for n in base_tree]
    for node in result:
        if "children" in node:
            node["children"] = [dict(c) for c in node["children"]]

    for state_label, state_tree in state_snapshots:
        _merge_one_state(result, state_tree, state_label)

    return result


def _match_static_to_runtime(
    static_classes: list[dict], runtime_nodes: list[dict]
) -> dict[str, dict]:
    """Match static classes to runtime AT-SPI nodes.

    Matching strategy (ordered by reliability):
      1. accessible_names → runtime name
         setAccessibleName("X") maps to AT-SPI name="X" (DTK convention).
      2. class_name → runtime name
         DTK class names used as AT-SPI name (e.g. DMainWindow, DTitlebar).
      3. object_names → runtime name (fallback, rarely matches)
         Rare: app code may happen to set objectName matching an AT-SPI name.
      4. object_names → runtime object_name
         setObjectName("X") maps to AT-SPI object-name attribute → object_name field.
      5. class_name → runtime object_name (less common)
         Some apps set objectName to the class name.
    """
    matches: dict[str, dict] = {}
    runtime_flat = _flatten_runtime_tree(runtime_nodes)

    runtime_by_name: dict[str, dict] = {}
    runtime_by_object_name: dict[str, dict] = {}
    for rn in runtime_flat:
        name = rn.get("name", "")
        if name:
            runtime_by_name[name] = rn
        on = rn.get("object_name", "")
        if on:
            runtime_by_object_name[on] = rn

    for cls in static_classes:
        matched = False

        # Pass 1: accessible_names → runtime name (primary)
        for an in cls.get("accessible_names", []):
            if not an:
                continue
            if an in runtime_by_name:
                rn = runtime_by_name[an]
                matches[rn["id"]] = cls
                matched = True
                break

        # Pass 2: class_name → runtime name (DTK class naming convention)
        if not matched:
            cn = cls.get("class_name", "")
            if cn and cn in runtime_by_name:
                rn = runtime_by_name[cn]
                matches[rn["id"]] = cls
                matched = True

        # Pass 3: object_names → runtime name (fallback, rarely matches)
        if not matched:
            for on in cls.get("object_names", []):
                if not on:
                    continue
                if on in runtime_by_name:
                    rn = runtime_by_name[on]
                    matches[rn["id"]] = cls
                    matched = True
                    break

        # Pass 4: object_names → runtime object_name
        if not matched:
            for on in cls.get("object_names", []):
                if not on:
                    continue
                if on in runtime_by_object_name:
                    rn = runtime_by_object_name[on]
                    matches[rn["id"]] = cls
                    matched = True
                    break

        # Pass 5: class_name → runtime object_name
        if not matched:
            cn = cls.get("class_name", "")
            if cn and cn in runtime_by_object_name:
                rn = runtime_by_object_name[cn]
                matches[rn["id"]] = cls
                matched = True

    return matches


def _enrich_runtime_nodes(runtime_nodes: list[dict], static_classes: list[dict]) -> None:
    for node in runtime_nodes:
        if "object_name" not in node:
            node["object_name"] = ""
        if "accessible_id" not in node:
            node["accessible_id"] = ""
        if "states" not in node:
            node["states"] = []
        if "source" not in node:
            node["source"] = "runtime"
        if "children" in node:
            _enrich_runtime_nodes(node["children"], static_classes)


def _dedup_static_classes(static_classes: list[dict]) -> list[dict]:
    """Merge duplicate class entries (same class_name) from multi-TU scans.

    clang may find the same class in multiple translation units with different
    base_classes completeness. Union object_names/accessible_names; prefer
    is_ui_widget=True.
    """
    by_name: dict[str, dict] = {}
    for cls in static_classes:
        cn = cls.get("class_name", "")
        if not cn:
            continue
        if cn not in by_name:
            by_name[cn] = dict(cls)
            continue
        existing = by_name[cn]
        for on in cls.get("object_names", []):
            if on and on not in existing.setdefault("object_names", []):
                existing["object_names"].append(on)
        for an in cls.get("accessible_names", []):
            if an and an not in existing.setdefault("accessible_names", []):
                existing["accessible_names"].append(an)
        if cls.get("is_ui_widget") and not existing.get("is_ui_widget"):
            existing["is_ui_widget"] = True
        if cls.get("base_classes") and not existing.get("base_classes"):
            existing["base_classes"] = cls["base_classes"]
    return list(by_name.values())


def _is_ui_widget(cls: dict) -> bool:
    """Check if a class is a UI widget using is_ui_widget flag, with base-class fallback."""
    val = cls.get("is_ui_widget")
    if val is not None:
        return val
    bases = cls.get("base_classes", [])
    return any(b in _ALL_UI_CLASSES for b in bases)


def _is_noise_static_class(cls: dict) -> bool:
    """True if a static class is not a UI widget (filter from merged tree)."""
    if cls.get("object_names") or cls.get("accessible_names"):
        return False
    return not _is_ui_widget(cls)


def _add_unmatched_static_nodes(
    runtime_nodes: list[dict], static_classes: list[dict], matches: dict[str, dict]
) -> None:
    matched_classes = set(id(c) for c in matches.values())
    for cls in static_classes:
        if id(cls) in matched_classes:
            continue
        if _is_noise_static_class(cls):
            continue
        cn = cls.get("class_name", "")
        names = cls.get("object_names", [])
        if not names and cn:
            names = [cn]
        children = []
        for on in names:
            if not on:
                continue
            children.append(
                {
                    "id": "",
                    "name": on,
                    "role": "panel",
                    "object_name": on,
                    "accessible_id": "",
                    "source": "static",
                    "class_name": cn,
                }
            )
        if not children:
            continue
        if len(children) == 1 and children[0]["name"] == cn:
            runtime_nodes.append(children[0])
        else:
            parent = {
                "id": "",
                "name": cn,
                "role": "panel",
                "object_name": "",
                "accessible_id": "",
                "source": "static",
                "class_name": cn,
                "children": children,
            }
            runtime_nodes.append(parent)


def merge_trees(runtime_tree: list[dict], static_classes: list[dict]) -> list[dict]:
    if not runtime_tree and not static_classes:
        return []

    result = [dict(n) for n in runtime_tree]
    for node in result:
        if "children" in node:
            node["children"] = [dict(c) for c in node["children"]]

    _enrich_runtime_nodes(result, static_classes)

    if static_classes:
        static_classes = _dedup_static_classes(static_classes)
        _assign_ids(result)
        matches = _match_static_to_runtime(static_classes, result)

        for rid, cls in matches.items():
            for node in _flatten_runtime_tree(result):
                if node.get("id") == rid:
                    if cls.get("object_names"):
                        node["object_name"] = cls["object_names"][0]
                    if cls.get("accessible_names"):
                        node["accessible_id"] = cls["accessible_names"][0]
                    node["source"] = "static+runtime"
                    node["class_name"] = cls.get("class_name", "")
                    break

        _add_unmatched_static_nodes(result, static_classes, matches)
    else:
        _assign_ids(result)

    return result


def write_at_tree_yaml(
    merged_tree: list[dict],
    output_path: str,
    app_name: str = "",
    transient_contexts: list[dict] | None = None,
) -> None:
    """Write the final at-tree.yaml.

    When *transient_contexts* is provided, writes version 2.0 with
    both ``tree`` (persistent layer) and ``transient_contexts`` fields.
    Otherwise writes version 1.0 (backward compatible).
    """
    filtered = filter_noise(merged_tree)
    removed = len(merged_tree) - len(filtered)
    if removed:
        logger.info("Filter removed %d noise nodes from %d", removed, len(merged_tree))
    classify_nodes(filtered)
    _normalize_tree(filtered)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if transient_contexts is not None:
        doc: dict[str, Any] = {
            "version": "2.0",
            "app": app_name,
            "tree": filtered,
            "transient_contexts": transient_contexts,
        }
    else:
        doc = {"version": "1.0", "app": app_name, "tree": filtered}

    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(doc, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    logger.info("Wrote at-tree.yaml to %s (%d root nodes)", output_path, len(filtered))


# ---------------------------------------------------------------------------
# Layered merge: persistent + transient + static injection
# ---------------------------------------------------------------------------


def load_record_session(record_dir: str | Path) -> dict[str, Any] | None:
    """Load record_session.yaml from a record output directory.

    Returns the parsed dict or ``None`` if the file doesn't exist.
    """
    record_path = Path(record_dir) / "record_session.yaml"
    if not record_path.is_file():
        return None
    with open(record_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data


def _load_state_snapshot(state_path: Path) -> list[dict] | None:
    """Load a single state snapshot YAML and return its tree."""
    if not state_path.is_file():
        return None
    with open(state_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if data and "tree" in data:
        return data["tree"]
    return None


def _anonymous_path_key(node: dict, parent_path: str = "") -> str:
    """Build a path-based identity key for anonymous nodes.

    Uses ``role:index_in_parent`` at each level from root to node,
    so two anonymous nodes at the same position in the tree are
    considered the same node.
    """
    role = node.get("role", "")
    idx = node.get("index_in_parent", -1)
    return f"{parent_path}/{role}:{idx}"


def _merge_persistent_state(
    base_nodes: list[dict],
    state_nodes: list[dict],
    state_label: str,
    parent_path: str = "",
) -> None:
    """Merge a state snapshot into base with last-wins for states.

    Unlike :func:`_merge_one_state` (which unions states), this function
    **overwrites** the states list with the latest snapshot's values.
    Anonymous nodes are matched by parent-chain path instead of
    identity key.
    """
    for s_node in state_nodes:
        s_key = _identity_key(s_node)
        s_anon_path = _anonymous_path_key(s_node, parent_path)
        matched = None

        for b_node in base_nodes:
            # Named nodes: match by identity key
            if _has_name(s_node) and _has_name(b_node):
                if _identity_key(b_node) == s_key:
                    matched = b_node
                    break
            # Anonymous nodes: match by parent-chain path
            elif not _has_name(s_node) and not _has_name(b_node):
                if _anonymous_path_key(b_node, parent_path) == s_anon_path:
                    matched = b_node
                    break

        if matched:
            # last-wins: overwrite states with latest observed values
            if s_node.get("states"):
                matched["states"] = list(s_node["states"])

            if "state_labels" not in matched:
                matched["state_labels"] = []
            if state_label and state_label not in matched["state_labels"]:
                matched["state_labels"].append(state_label)

            # Recurse into children
            if "children" in s_node:
                if "children" not in matched:
                    matched["children"] = []
                child_path = f"{s_anon_path}" if not _has_name(s_node) else s_anon_path
                _merge_persistent_state(
                    matched["children"],
                    s_node["children"],
                    state_label,
                    child_path,
                )
        else:
            # New node — add to base
            new_node = dict(s_node)
            if "children" in s_node:
                new_node["children"] = [dict(c) for c in s_node["children"]]
            if state_label:
                new_node["state_labels"] = [state_label]
            base_nodes.append(new_node)


def merge_persistent(
    base_tree: list[dict],
    session_data: dict[str, Any],
    record_dir: str | Path,
) -> list[dict]:
    """Merge persistent-layer snapshots (launch + window:activate) into base.

    States use **last-wins** (overwrite, not union).  Anonymous nodes
    are deduplicated by parent-chain path.  Transient snapshots
    (menu_open, window_create) are skipped — they go to the
    transient layer.
    """
    result = [dict(n) for n in base_tree]
    for node in result:
        if "children" in node:
            node["children"] = [dict(c) for c in node["children"]]

    record_dir = Path(record_dir)

    for segment in session_data.get("segments", []):
        trigger = segment.get("trigger") or {}
        trigger_type = trigger.get("type", "")

        # Only persistent snapshots: launch + window_activate
        if trigger_type not in ("launch", "window_activate"):
            continue

        state_label = segment.get("label", trigger_type)

        for state_ref in segment.get("states", []):
            state_path = record_dir / state_ref
            snapshot = _load_state_snapshot(state_path)
            if snapshot is None:
                logger.warning("State snapshot not found: %s", state_path)
                continue

            if not result:
                result = [dict(n) for n in snapshot]
            else:
                _merge_persistent_state(result, snapshot, state_label)

    return result


def extract_transient(session_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract transient contexts from a record session.

    Walks the session's segments and events, extracting:
    - ``menu_open`` events → ``right_click_menu_NNN``
    - ``window_create`` events → ``child_window_NNN``

    Transient contexts store trigger condition, items (for menus),
    and snapshot path reference.  They are NOT mixed into the main tree.
    """
    contexts: list[dict[str, Any]] = []
    menu_count = 0
    window_count = 0

    for segment in session_data.get("segments", []):
        seg_trigger = segment.get("trigger") or {}

        for event in segment.get("events", []):
            evt_type = event.get("type", "")

            if evt_type == "menu_open":
                contexts.append(
                    {
                        "id": f"right_click_menu_{menu_count:03d}",
                        "trigger": seg_trigger,
                        "items": event.get("menu_items", []),
                        "at_tree": event.get("at_tree", ""),
                    }
                )
                menu_count += 1

            elif evt_type == "window_create":
                contexts.append(
                    {
                        "id": f"child_window_{window_count:03d}",
                        "trigger": {
                            "type": "window_create",
                            "app": event.get("app", ""),
                            "element": event.get("element", {}),
                        },
                        "at_tree": event.get("at_tree", ""),
                    }
                )
                window_count += 1

    return contexts


def layered_merge(
    scan_classes: list[dict],
    record_dir: str | Path,
) -> tuple[list[dict], list[dict[str, Any]]]:
    """Full layered merge pipeline: persistent + transient + static injection.

    Parameters
    ----------
    scan_classes
        Static scan output (list of class dicts from clang_scanner).
    record_dir
        Directory containing ``record_session.yaml`` and ``states/*.yaml``.

    Returns
    -------
    (merged_tree, transient_contexts)
        The persistent tree (with static info injected) and the
        transient contexts list.
    """
    record_dir = Path(record_dir)
    session = load_record_session(record_dir)

    if session is None:
        # Fallback: old-style state snapshots (no record_session.yaml)
        states_dir = record_dir / "states"
        if not states_dir.is_dir():
            states_dir = record_dir / "dump" / "states"
        state_snapshots = load_state_snapshots(str(states_dir))
        if state_snapshots:
            base_tree = state_snapshots[0][1]
            for label, tree in state_snapshots[1:]:
                _merge_persistent_state(base_tree, tree, label)
        else:
            base_tree = []
        merged = merge_trees(base_tree, scan_classes)
        return merged, []

    # Build base tree from launch segment
    base_tree: list[dict] = []
    for segment in session.get("segments", []):
        trigger = segment.get("trigger") or {}
        if trigger.get("type") == "launch":
            for state_ref in segment.get("states", []):
                snapshot = _load_state_snapshot(record_dir / state_ref)
                if snapshot:
                    base_tree = snapshot
                    break
            break

    # Merge persistent snapshots (launch + window_activate)
    base_tree = merge_persistent(base_tree, session, record_dir)

    # Extract transient contexts
    transient = extract_transient(session)

    # Inject static scan info
    merged = merge_trees(base_tree, scan_classes)

    return merged, transient


def write_element_gaps(tree: list[dict], path: str, app_name: str = "") -> None:
    classify_nodes(tree)
    interactive_nodes = [
        n for n in _flatten_runtime_tree(tree) if n.get("classification") == "interactive"
    ]
    gaps = [
        {
            "id": n.get("id", ""),
            "name": n.get("name", ""),
            "role": n.get("role", ""),
            "class_name": n.get("class_name", ""),
            "suggestion": f'Add setAccessibleName("{n.get("name", "")}") in source code',
        }
        for n in interactive_nodes
        if not n.get("accessible_id") and not n.get("object_name")
    ]
    total = len(interactive_nodes)
    report = {
        "version": "1.0",
        "app": app_name,
        "summary": {
            "total_interactive": total,
            "with_accessible_id": total - len(gaps),
            "missing_accessible_id": len(gaps),
        },
        "gaps": gaps,
    }
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(report, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    logger.info("Wrote element_gaps.yaml to %s (%d gaps)", path, len(gaps))
