# SPDX-FileCopyrightText: 2026 Uniontech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only

"""Precandidate: pre-filter AT-SPI tree nodes for each step description.

Pure Python, zero LLM. Produces suite-cases.yaml with embedded candidates.
AI's job becomes "pick one candidate" instead of "write selector YAML".
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import yaml

from src.at.generator.action_rules import get_action_for_role, guess_role_from_description

TOP_K = 5
HIGH_CONFIDENCE_THRESHOLD = 2.0


def _tokenize(description: str) -> list[str]:
    """Simple Chinese-aware tokenizer (no jieba dependency)."""
    cleaned = re.sub(r"[\d.\s、，,。.!！？?：:;；()（）\[\]【】\"'“”‘’]+", " ", description)
    tokens = []
    for word in cleaned.split():
        if len(word) >= 2:
            tokens.append(word)
    return tokens


def _iter_interactive_nodes(nodes: list[dict], parent: dict | None = None):
    """Yield (node, parent) for all interactive nodes in the tree."""
    for node in nodes:
        classification = node.get("classification", "")
        if classification == "interactive" or not classification:
            yield node, parent
        children = node.get("children", [])
        if children:
            yield from _iter_interactive_nodes(children, node)


def _build_index(at_tree_path: str) -> list[dict[str, Any]]:
    """Build a flat index of interactive nodes from at-tree.yaml."""
    raw = Path(at_tree_path).read_text(encoding="utf-8")
    tree_data = yaml.safe_load(raw)
    if not tree_data or not isinstance(tree_data, dict):
        return []

    tree_nodes = tree_data.get("tree", [])
    if not isinstance(tree_nodes, list):
        return []

    index = []
    for node, parent in _iter_interactive_nodes(tree_nodes):
        entry = {
            "id": node.get("id", ""),
            "name": node.get("name", ""),
            "role": node.get("role", ""),
            "comment": node.get("comment", ""),
            "accessible_id": node.get("accessible_id", ""),
            "classification": node.get("classification", ""),
            "parent_id": parent.get("id", "") if parent else "",
        }
        index.append(entry)
    return index


def _score_node(description: str, tokens: list[str], node: dict) -> float:
    """Compute matching score between description and a tree node."""
    score = 0.0
    name = (node.get("name") or "").lower()
    comment = (node.get("comment") or "").lower()
    role = (node.get("role") or "").lower()
    desc_lower = description.lower()

    # name exact match
    if name and name == desc_lower:
        score += 3.0

    # name substring match
    if name and name in desc_lower:
        score += 2.0
    elif name and desc_lower in name:
        score += 1.5
    else:
        # token-level name match
        for token in tokens:
            if token.lower() in name:
                score += 1.5
                break

    # comment contains description keywords
    for token in tokens:
        if token.lower() in comment:
            score += 1.0

    # role keyword match
    guessed_role = guess_role_from_description(description)
    if guessed_role and guessed_role in role:
        score += 1.5

    # accessible_id match
    acc_id = (node.get("accessible_id") or "").lower()
    if acc_id and acc_id in desc_lower:
        score += 2.0

    return score


def _find_candidates(
    description: str,
    index: list[dict[str, Any]],
    top_k: int = TOP_K,
) -> list[dict[str, Any]]:
    """Find top-K candidate nodes for a step description."""
    tokens = _tokenize(description)
    scored = []
    for node in index:
        score = _score_node(description, tokens, node)
        if score > 0:
            scored.append((score, node))

    scored.sort(key=lambda x: x[0], reverse=True)

    candidates = []
    for score, node in scored[:top_k]:
        action_config = get_action_for_role(node.get("role", ""))
        candidate = {
            "id": node["id"],
            "name": node.get("name", ""),
            "role": node.get("role", ""),
            "comment": node.get("comment", ""),
            "score": round(score, 2),
        }
        if action_config.get("requires"):
            candidate["requires"] = action_config["requires"]
        candidates.append(candidate)

    return candidates


def _classify_confidence(candidates: list[dict]) -> str:
    if not candidates:
        return "unsupported"
    top_score = candidates[0].get("score", 0)
    if top_score >= HIGH_CONFIDENCE_THRESHOLD:
        return "high"
    return "low"


def _build_suite_case(
    case: dict,
    index: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a suite-case entry with embedded candidates for each step."""
    suite_steps = []
    for step in case.get("steps", []):
        if not isinstance(step, dict):
            continue
        description = step.get("description", "")
        step_type = step.get("step_type", "action")
        candidates = _find_candidates(description, index)
        confidence = _classify_confidence(candidates)

        suite_step: dict[str, Any] = {
            "step_type": step_type,
            "description": description,
            "intent": None,
            "target_keyword": None,
            "candidates": candidates,
            "selected": None,
            "confidence": confidence,
        }

        if confidence == "unsupported":
            suite_step["status"] = "UNSUPPORTED"
            suite_step["reason"] = "无匹配节点"

        suite_steps.append(suite_step)

    return {
        "id": case.get("id", ""),
        "name": case.get("name", "") or case.get("description", ""),
        "module": case.get("module", ""),
        "description": case.get("description", ""),
        "status": case.get("status", "active"),
        "steps": suite_steps,
    }


def precandidate_from_cases(
    cases_path: str,
    at_tree_path: str,
    output_path: str,
) -> dict[str, Any]:
    """Generate suite-cases.yaml with embedded candidates.

    Returns summary stats.
    """
    cases_raw = yaml.safe_load(Path(cases_path).read_text(encoding="utf-8"))
    if not cases_raw or not isinstance(cases_raw, dict):
        print(f"Error: invalid cases format: {cases_path}", file=sys.stderr)
        sys.exit(1)

    cases = cases_raw.get("cases", [])
    if not cases:
        print(f"Error: no cases found in {cases_path}", file=sys.stderr)
        sys.exit(1)

    index = _build_index(at_tree_path)
    if not index:
        print(f"Error: no interactive nodes in {at_tree_path}", file=sys.stderr)
        sys.exit(1)

    suite_cases = []
    total_steps = 0
    high_conf = 0
    low_conf = 0
    unsupported = 0
    total_candidates = 0

    for case in cases:
        suite_case = _build_suite_case(case, index)
        suite_cases.append(suite_case)
        for step in suite_case["steps"]:
            total_steps += 1
            total_candidates += len(step.get("candidates", []))
            conf = step.get("confidence", "")
            if conf == "high":
                high_conf += 1
            elif conf == "low":
                low_conf += 1
            else:
                unsupported += 1

    output = {
        "version": "1.0",
        "cases": suite_cases,
    }

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    content = yaml.dump(
        output,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    )
    out.write_text(content, encoding="utf-8")

    avg_candidates = (total_candidates / total_steps) if total_steps else 0.0
    print(
        f"Precandidate: {len(suite_cases)} cases, {total_steps} steps\n"
        f"  high confidence: {high_conf}\n"
        f"  low confidence:  {low_conf}\n"
        f"  unsupported:     {unsupported}\n"
        f"  avg candidates/step: {avg_candidates:.1f}\n"
        f"  -> {out}"
    )

    return {
        "cases": len(suite_cases),
        "steps": total_steps,
        "high_confidence": high_conf,
        "low_confidence": low_conf,
        "unsupported": unsupported,
        "avg_candidates": round(avg_candidates, 2),
        "output": str(out),
    }


def precandidate_from_module(
    module_dir: str,
) -> dict[str, Any]:
    """Generate suite-cases.yaml for a single module directory.

    Reads cases.md from module_dir and at-tree-subtree.yaml.
    """
    module_path = Path(module_dir)
    cases_md = module_path / "cases.md"
    at_tree_subtree = module_path / "at-tree-subtree.yaml"

    if not cases_md.exists():
        print(f"Error: cases.md not found in {module_dir}", file=sys.stderr)
        sys.exit(1)
    if not at_tree_subtree.exists():
        print(f"Error: at-tree-subtree.yaml not found in {module_dir}", file=sys.stderr)
        sys.exit(1)

    # Convert cases.md back to cases format
    cases = _parse_cases_md(cases_md.read_text(encoding="utf-8"))
    cases_raw = {"metadata": {"source": str(cases_md)}, "cases": cases}

    # Write temp cases file
    temp_cases = module_path / "_cases_raw.yaml"
    temp_cases.write_text(
        yaml.dump(cases_raw, allow_unicode=True, default_flow_style=False),
        encoding="utf-8",
    )

    output_path = str(module_path / "suite-cases.yaml")
    try:
        return precandidate_from_cases(str(temp_cases), str(at_tree_subtree), output_path)
    finally:
        temp_cases.unlink(missing_ok=True)


def _parse_cases_md(content: str) -> list[dict[str, Any]]:
    """Parse cases.md markdown table back to case dicts."""
    lines = content.strip().splitlines()
    cases = []
    for line in lines[2:]:  # skip header + separator
        parts = line.split("|")
        if len(parts) < 5:
            continue
        cid = parts[1].strip()
        title = parts[2].strip()
        steps_text = parts[3].strip()
        expected_text = parts[4].strip()

        steps = []
        for step_line in steps_text.split("<br>"):
            step_line = step_line.strip()
            if step_line:
                steps.append({"step_type": "action", "description": step_line})
        for exp_line in expected_text.split("<br>"):
            exp_line = exp_line.strip()
            if exp_line:
                steps.append({"step_type": "assert", "description": exp_line})

        if steps:
            cases.append({
                "id": cid,
                "name": title,
                "module": "",
                "description": title,
                "status": "active",
                "steps": steps,
            })
    return cases
