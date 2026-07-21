# SPDX-FileCopyrightText: 2026 Uniontech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only

"""Extract a subtree from at-tree-annotated.yaml matching module keywords.

Goal: each module's subtree contains only the nodes it needs, reducing
sub-agent context.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml


def _iter_nodes(nodes: list[dict]):
    for node in nodes:
        yield node
        for child in _iter_nodes(node.get("children", [])):
            yield child


def _collect_keywords(descriptions: list[str]) -> list[str]:
    """Extract meaningful keywords from case descriptions."""
    keywords: set[str] = set()
    for desc in descriptions:
        cleaned = re.sub(r"[\d.、，,。.\s]+", " ", desc)
        for word in cleaned.split():
            if len(word) >= 2:
                keywords.add(word.lower())
    return sorted(keywords)


def _node_matches(node: dict, keywords: list[str]) -> bool:
    name = (node.get("name") or "").lower()
    comment = (node.get("comment") or "").lower()
    role = (node.get("role") or "").lower()
    accessible_id = (node.get("accessible_id") or "").lower()
    text = f"{name} {comment} {role} {accessible_id}"
    return any(kw in text for kw in keywords)


def _find_parent_chain(
    nodes: list[dict],
    target_id: str,
    path: list[dict] | None = None,
) -> list[dict] | None:
    path = path or []
    for node in nodes:
        current_path = path + [node]
        if node.get("id") == target_id:
            return current_path
        children = node.get("children", [])
        if children:
            result = _find_parent_chain(children, target_id, current_path)
            if result:
                return result
    return None


def _collect_ancestor_ids(
    nodes: list[dict],
    matched_ids: set[str],
) -> set[str]:
    """Collect all ancestor node IDs for matched nodes."""
    ancestor_ids: set[str] = set()
    for mid in matched_ids:
        chain = _find_parent_chain(nodes, mid)
        if chain:
            ancestor_ids.update(n.get("id", "") for n in chain)
    return ancestor_ids


def extract_subtree(
    at_tree_path: str,
    descriptions: list[str],
    output_path: str,
) -> dict[str, Any]:
    """Extract a subtree matching descriptions from at-tree-annotated.yaml.

    Returns stats dict with node counts.
    """
    raw = Path(at_tree_path).read_text(encoding="utf-8")
    tree_data = yaml.safe_load(raw)
    if not tree_data or not isinstance(tree_data, dict):
        _write_subtree(output_path, {"version": "1.0", "tree": []})
        return {"total_nodes": 0, "subtree_nodes": 0, "coverage": 0.0}

    tree_nodes = tree_data.get("tree", [])
    if not isinstance(tree_nodes, list):
        tree_nodes = []

    total_count = sum(1 for _ in _iter_nodes(tree_nodes))
    keywords = _collect_keywords(descriptions)

    matched_ids: set[str] = set()
    for node in _iter_nodes(tree_nodes):
        if _node_matches(node, keywords):
            matched_ids.add(node.get("id", ""))

    ancestor_ids = _collect_ancestor_ids(tree_nodes, matched_ids)
    keep_ids = matched_ids | ancestor_ids

    def _filter(nodes: list[dict]) -> list[dict]:
        result = []
        for node in nodes:
            nid = node.get("id", "")
            children = node.get("children", [])
            filtered_children = _filter(children) if children else []
            if nid in keep_ids or filtered_children:
                filtered = {k: v for k, v in node.items() if k != "children"}
                if filtered_children:
                    filtered["children"] = filtered_children
                result.append(filtered)
        return result

    subtree = _filter(tree_nodes)
    subtree_count = sum(1 for _ in _iter_nodes(subtree))
    coverage = (subtree_count / total_count) if total_count else 0.0

    _write_subtree(output_path, {"version": "1.0", "tree": subtree})
    return {
        "total_nodes": total_count,
        "subtree_nodes": subtree_count,
        "coverage": round(coverage, 4),
    }


def _write_subtree(output_path: str, data: dict[str, Any]) -> None:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    content = yaml.dump(
        data,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    )
    out.write_text(content, encoding="utf-8")
