# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

import yaml

from src.at.parser.models import ElementMappingsDoc, MappingEntry, MappingStatus


def _load_yaml(path: str) -> dict | list | None:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _build_node_index(at_tree_data: dict) -> dict[str, dict]:
    nodes = at_tree_data.get("nodes", [])
    index: dict[str, dict] = {}
    for node in nodes:
        nid = node.get("id")
        if nid:
            index[nid] = node
    return index


def diff_update(
    old_at_tree_path: str,
    new_at_tree_path: str,
    old_mappings_path: str,
    output_path: str,
) -> None:
    old_tree_data = _load_yaml(old_at_tree_path)
    new_tree_data = _load_yaml(new_at_tree_path)

    old_index = _build_node_index(old_tree_data or {})
    new_index = _build_node_index(new_tree_data or {})

    old_mappings_data = _load_yaml(old_mappings_path)
    old_doc = ElementMappingsDoc.model_validate(old_mappings_data or {})

    old_ids = set(old_index)
    new_ids = set(new_index)
    deleted_ids = old_ids - new_ids
    added_ids = new_ids - old_ids
    common_ids = old_ids & new_ids

    def _collect_referenced_nodes(doc: ElementMappingsDoc) -> set[str]:
        refs: set[str] = set()
        for m in doc.mappings:
            if m.element_ref and m.status != "deprecated":
                refs.add(m.element_ref)
        return refs

    referenced = _collect_referenced_nodes(old_doc)
    changed_nodes: set[str] = set()
    for nid in common_ids:
        old_n = old_index[nid]
        new_n = new_index[nid]
        if old_n.get("name") != new_n.get("name") or old_n.get("role") != new_n.get("role"):
            changed_nodes.add(nid)

    updated_mappings: list[MappingEntry] = []
    for entry in old_doc.mappings:
        if entry.element_ref and entry.element_ref in deleted_ids:
            updated = entry.model_copy()
            updated.status = MappingStatus.deprecated
            updated.reason = "at-tree node deleted"
            updated_mappings.append(updated)
        elif entry.element_ref and entry.element_ref in changed_nodes:
            new_node = new_index[entry.element_ref]
            updated = entry.model_copy()
            if entry.selector:
                sel = entry.selector.model_copy()
                if new_node.get("name"):
                    sel.name = new_node["name"]
                if new_node.get("role"):
                    sel.role = new_node["role"]
                updated.selector = sel
            updated_mappings.append(updated)
        else:
            updated_mappings.append(entry)

    for nid in added_ids:
        if nid in referenced:
            node = new_index[nid]
            updated_mappings.append(
                MappingEntry(
                    case_id="",
                    step_index=0,
                    description=f"new element: {node.get('name', nid)}",
                    step_type="action",
                    element_ref=nid,
                    status=MappingStatus.unmapped,
                    reason="new element added to at-tree",
                )
            )

    new_doc = ElementMappingsDoc(
        metadata=old_doc.metadata.model_copy(),
        mappings=updated_mappings,
    )

    try:
        import yaml as pyyaml

        data = new_doc.model_dump(mode="json")
        with open(output_path, "w", encoding="utf-8") as f:
            pyyaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    except ImportError:
        with open(output_path, "w", encoding="utf-8") as f:
            import json

            json.dump(new_doc.model_dump(mode="json"), f, ensure_ascii=False, indent=2)

    total = len(new_doc.mappings)
    deprecated = sum(1 for m in new_doc.mappings if m.status == "deprecated")
    unmapped = sum(1 for m in new_doc.mappings if m.status == "unmapped")
    print(f"Wrote {output_path} ({total} mappings, {deprecated} deprecated, {unmapped} unmapped)")
