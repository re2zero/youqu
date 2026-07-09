# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only

"""Merge static C++ skeleton with runtime AT-SPI dump into unified at-tree.yaml."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


def _is_noise_leaf(node: dict) -> bool:
    if node.get("children"):
        return False
    return not node.get("name") and not node.get("object_name") and not node.get("accessible_id")


def filter_noise(tree: list[dict]) -> list[dict]:
    def _filter_recursive(nodes: list[dict]) -> list[dict]:
        result = []
        for node in nodes:
            if _is_noise_leaf(node):
                continue
            if "children" in node:
                node["children"] = _filter_recursive(node["children"])
            result.append(node)
        return result

    return _filter_recursive(tree)


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
    gaps = []
    for cls in classes:
        bases = cls.get("base_classes", [])
        if not bases:
            continue
        if cls.get("object_names") or cls.get("accessible_names"):
            continue
        gaps.append(
            {
                "class_name": cls.get("class_name", ""),
                "source_file": cls.get("source_file", ""),
                "base_classes": bases,
                "object_names": cls.get("object_names", []),
                "accessible_names": cls.get("accessible_names", []),
                "dtk_instantiations": cls.get("dtk_instantiations", []),
            }
        )
    total_ui = len([c for c in classes if c.get("base_classes")])
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


def _match_static_to_runtime(
    static_classes: list[dict], runtime_nodes: list[dict]
) -> dict[str, dict]:
    """Match static classes to runtime AT-SPI nodes.

    Matching strategy (ordered by reliability):
      1. accessible_names → runtime name
         setAccessibleName("X") maps to AT-SPI name="X" (DTK convention).
      2. class_name → runtime name
         DTK class names used as AT-SPI name (e.g. DMainWindow, DTitlebar).
      3. object_names → runtime name (fallback)
         Rare: app code may happen to set objectName matching an AT-SPI name.
    """
    matches: dict[str, dict] = {}
    runtime_flat = _flatten_runtime_tree(runtime_nodes)

    runtime_by_name: dict[str, dict] = {}
    for rn in runtime_flat:
        name = rn.get("name", "")
        if name:
            runtime_by_name[name] = rn

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

    return matches


def _enrich_runtime_nodes(runtime_nodes: list[dict], static_classes: list[dict]) -> None:
    for node in runtime_nodes:
        if "object_name" not in node:
            node["object_name"] = ""
        if "accessible_id" not in node:
            node["accessible_id"] = ""
        if "source" not in node:
            node["source"] = "runtime"
        if "children" in node:
            _enrich_runtime_nodes(node["children"], static_classes)


def _add_unmatched_static_nodes(
    runtime_nodes: list[dict], static_classes: list[dict], matches: dict[str, dict]
) -> None:
    matched_classes = set(id(c) for c in matches.values())
    for cls in static_classes:
        if id(cls) in matched_classes:
            continue
        names = cls.get("object_names", []) or [cls.get("class_name", "")]
        for on in names:
            if not on:
                continue
            node = {
                "id": "",
                "name": on,
                "role": "panel",
                "object_name": on,
                "accessible_id": (cls.get("accessible_names") or [""])[0],
                "source": "static",
                "class_name": cls.get("class_name", ""),
                "source_file": cls.get("source_file", ""),
                "match_status": "unresolved",
            }
            runtime_nodes.append(node)


def merge_trees(runtime_tree: list[dict], static_classes: list[dict]) -> list[dict]:
    if not runtime_tree and not static_classes:
        return []

    result = [dict(n) for n in runtime_tree]
    for node in result:
        if "children" in node:
            node["children"] = [dict(c) for c in node["children"]]

    _enrich_runtime_nodes(result, static_classes)

    if static_classes:
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
                    node["source_file"] = cls.get("source_file", "")
                    break

        _add_unmatched_static_nodes(result, static_classes, matches)
    else:
        _assign_ids(result)

    return result


def write_at_tree_yaml(merged_tree: list[dict], output_path: str, app_name: str = "") -> None:
    filtered = filter_noise(merged_tree)
    removed = len(merged_tree) - len(filtered)
    if removed:
        logger.info("Filter removed %d noise nodes from %d", removed, len(merged_tree))
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    doc: dict[str, Any] = {"version": "1.0", "app": app_name, "tree": filtered}
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(doc, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    logger.info("Wrote at-tree.yaml to %s (%d root nodes)", output_path, len(filtered))
