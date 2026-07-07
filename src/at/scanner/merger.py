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


def _match_static_to_runtime(static_classes: list[dict], runtime_nodes: list[dict]) -> dict[str, dict]:
    matches: dict[str, dict] = {}
    runtime_flat = _flatten_runtime_tree(runtime_nodes)

    runtime_by_name: dict[str, dict] = {}
    for rn in runtime_flat:
        name = rn.get("name", "")
        if name:
            runtime_by_name[name] = rn

    for cls in static_classes:
        matched = False
        for on in cls.get("object_names", []):
            if not on:
                continue
            if on in runtime_by_name:
                rn = runtime_by_name[on]
                matches[rn["id"]] = cls
                matched = True
                break
        if not matched:
            for an in cls.get("accessible_names", []):
                if not an:
                    continue
                for rn in runtime_flat:
                    if rn.get("accessible_id") == an:
                        matches[rn["id"]] = cls
                        matched = True
                        break
                if matched:
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


def _add_unmatched_static_nodes(runtime_nodes: list[dict], static_classes: list[dict], matches: dict[str, dict]) -> None:
    matched_classes = set(id(c) for c in matches.values())
    for cls in static_classes:
        if id(cls) in matched_classes:
            continue
        for on in cls.get("object_names", []):
            if on:
                node = {
                    "id": "",
                    "name": on,
                    "role": "panel",
                    "object_name": on,
                    "accessible_id": cls.get("accessible_names", [""])[0],
                    "source": "static",
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
                    break

        _add_unmatched_static_nodes(result, static_classes, matches)
    else:
        _assign_ids(result)

    return result


def write_at_tree_yaml(merged_tree: list[dict], output_path: str, app_name: str = "") -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    doc: dict[str, Any] = {"version": "1.0", "app": app_name, "tree": merged_tree}
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(doc, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    logger.info("Wrote at-tree.yaml to %s (%d root nodes)", output_path, len(merged_tree))
