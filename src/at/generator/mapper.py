# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

import json
from pathlib import Path

import yaml
from pydantic import ValidationError

from src.at.generator.case_parser import _extract_json, _get_llm_config, call_llm
from src.at.generator.mapping_rules import HINT_ROLE_CONSTRAINTS, STEP_TYPE_MAP
from src.at.parser.models import ElementMappingsDoc, MappingsMetadata


SCHEMA_DESCRIPTION = """
element-mappings schema:
{
  "metadata": {"generated_at": "ISO datetime", "at_tree_source": "string"},
  "mappings": [
    {
      "case_id": "string",
      "step_index": 0,
      "description": "string",
      "step_type": "action|assert|navigate",
      "element_hint": "main_menu_comb|context_menu_comb|titlebar|toolbar|sidebar|tab_bar|dialog|tooltip|dock|null",
      "menu_path": ["item1", "item2"] or null,
      "element_ref": "string or null",
      "selector": {"name": "string", "role": "string", "name_pattern": "string"} or null,
      "status": "mapped|unmapped|deprecated",
      "reason": "string (only when status=unmapped)",
      "fix_suggestion": "string (only when status=unmapped)",
      "note": "string",
      "context": "string"
    }
  ]
}"""


def _build_map_prompt(cases_text: str, at_tree_text: str) -> str:
    constraints = json.dumps(HINT_ROLE_CONSTRAINTS, ensure_ascii=False, indent=2)
    step_map = json.dumps(STEP_TYPE_MAP, ensure_ascii=False, indent=2)
    return (
        "You are a UI element mapping expert.\n\n"
        "Input:\n"
        "1. cases.yaml (step descriptions + step_type + element_hint)\n"
        "2. at-tree.yaml (full element list with id/name/role/hierarchy)\n\n"
        "Task:\n"
        "- Match each step's description to an element in at-tree.yaml\n"
        "- Output element_ref + selector (name/role)\n"
        "- Failed matches: status=unmapped with reason + fix_suggestion\n\n"
        "Constraints:\n"
        f"- Follow role constraints: {constraints}\n"
        f"- Step type to operation: {step_map}\n"
        "- main_menu_comb / context_menu_comb use menu_path instead of fixed ref\n"
        "- fix_suggestion must be specific (e.g. add setAccessibleName('xxx') in source)\n\n"
        f"{SCHEMA_DESCRIPTION}\n\n"
        "Output valid JSON matching the schema above. No markdown, no explanation.\n\n"
        f"--- cases.yaml ---\n{cases_text}\n\n"
        f"--- at-tree.yaml ---\n{at_tree_text}\n"
    )


def _write_mappings(doc: ElementMappingsDoc, output_path: str) -> None:
    try:
        import yaml as pyyaml

        data = doc.model_dump(mode="json")
        with open(output_path, "w", encoding="utf-8") as f:
            pyyaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    except ImportError:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(doc.model_dump(mode="json"), f, ensure_ascii=False, indent=2)


def map_elements(at_tree_path: str, cases_path: str, output_path: str) -> None:
    cases_text = Path(cases_path).read_text(encoding="utf-8")
    at_tree_text = Path(at_tree_path).read_text(encoding="utf-8")

    config = _get_llm_config()
    prompt = _build_map_prompt(cases_text, at_tree_text)
    raw = call_llm(prompt, config)

    if not raw:
        doc = ElementMappingsDoc(
            metadata=MappingsMetadata(at_tree_source=at_tree_path),
            mappings=[],
        )
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        _write_mappings(doc, output_path)
        print(f"Wrote {output_path} (empty, LLM returned no response)")
        return

    parsed = _extract_json(raw)
    if not parsed:
        doc = ElementMappingsDoc(
            metadata=MappingsMetadata(at_tree_source=at_tree_path),
            mappings=[],
        )
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        _write_mappings(doc, output_path)
        print(f"Wrote {output_path} (empty, LLM output parse failed)")
        return

    try:
        doc = ElementMappingsDoc.model_validate(parsed)
    except ValidationError as e:
        doc = ElementMappingsDoc(
            metadata=MappingsMetadata(at_tree_source=at_tree_path),
            mappings=[],
        )
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        _write_mappings(doc, output_path)
        print(f"Wrote {output_path} (empty, schema validation failed: {e})")
        return

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    _write_mappings(doc, output_path)
    total = len(doc.mappings)
    mapped = sum(1 for m in doc.mappings if m.status == "mapped")
    unmapped = total - mapped
    print(f"Wrote {output_path} ({total} mappings, {mapped} mapped, {unmapped} unmapped)")
