# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only

import sys
import types

import pytest
from unittest.mock import MagicMock, patch

_src_mock = sys.modules.get("src")
if not _src_mock or not getattr(_src_mock, "__spec__", None):
    sys.modules["src"] = types.ModuleType("src")
    sys.modules["src"].__path__ = ["/home/zero/work/research/youqu/src"]
    sys.modules["src"].__package__ = "src"
    sys.modules["src"].__file__ = "/home/zero/work/research/youqu/src/__init__.py"
if not isinstance(sys.modules.get("pyatspi"), types.ModuleType):
    sys.modules["pyatspi"] = MagicMock()


def test_build_map_prompt():
    from src.at.generator.mapper import _build_map_prompt

    prompt = _build_map_prompt("cases text", "at-tree text")
    assert "UI element mapping expert" in prompt
    assert "cases text" in prompt
    assert "at-tree text" in prompt
    assert "dtk_main_menu" in prompt
    assert "element_action" in prompt


def test_write_mappings_yaml():
    from src.at.generator.mapper import _write_mappings
    from src.at.parser.models import ElementMappingsDoc, MappingEntry

    doc = ElementMappingsDoc(
        mappings=[
            MappingEntry(
                case_id="test_001",
                step_index=0,
                description="click button",
                step_type="action",
                element_ref="btn1",
                selector={"name": "OK", "role": "push button"},
            )
        ]
    )
    _write_mappings(doc, "/tmp/test_at_mapper_write.yaml")
    content = open("/tmp/test_at_mapper_write.yaml", encoding="utf-8").read()
    assert "OK" in content


def test_write_mappings_json_fallback():
    from src.at.generator.mapper import _write_mappings
    from src.at.parser.models import ElementMappingsDoc

    doc = ElementMappingsDoc()
    with patch("builtins.__import__", side_effect=ImportError):
        _write_mappings(doc, "/tmp/test_at_mapper_write.json")
    content = open("/tmp/test_at_mapper_write.json", encoding="utf-8").read()
    assert '"mappings"' in content


def test_map_elements_success():
    from src.at.generator.mapper import map_elements

    cases_yaml = "suites:\n  - id: s1\n    steps:\n      - description: click play\n        step_type: action\n"
    tree_yaml = "nodes:\n  - id: n1\n    name: play\n    role: push button\n"
    llm_response = '{"metadata": {"generated_at": "x", "at_tree_source": ""}, "mappings": [{"case_id": "s1", "step_index": 0, "description": "click play", "step_type": "action", "element_ref": "n1", "selector": {"name": "play", "role": "push button"}, "status": "mapped"}]}'

    with patch("src.at.generator.case_parser.call_llm", return_value=llm_response):
        with patch("pathlib.Path.read_text", side_effect=[cases_yaml, tree_yaml]):
            map_elements("/tmp/fake/tree.yaml", "/tmp/fake/cases.yaml", "/tmp/test_at_mapper_out.yaml")

    content = open("/tmp/test_at_mapper_out.yaml", encoding="utf-8").read()
    assert "n1" in content


def test_map_elements_empty_llm_response():
    from src.at.generator.mapper import map_elements

    cases_yaml = "suites:\n  - id: s1\n"
    tree_yaml = "nodes:\n"
    with patch("src.at.generator.case_parser.call_llm", return_value=""):
        with patch("pathlib.Path.read_text", side_effect=[cases_yaml, tree_yaml]):
            map_elements("/t/tree.yaml", "/t/cases.yaml", "/tmp/test_at_mapper_empty.yaml")

    content = open("/tmp/test_at_mapper_empty.yaml", encoding="utf-8").read()
    assert "mappings: []" in content


def test_map_elements_invalid_schema():
    from src.at.generator.mapper import map_elements

    cases_yaml = "suites:\n  - id: s1\n"
    tree_yaml = "nodes:\n"
    with patch("src.at.generator.case_parser.call_llm", return_value='{"bad": "data"}'):
        with patch("pathlib.Path.read_text", side_effect=[cases_yaml, tree_yaml]):
            map_elements("/t/tree.yaml", "/t/cases.yaml", "/tmp/test_at_mapper_invalid.yaml")

    content = open("/tmp/test_at_mapper_invalid.yaml", encoding="utf-8").read()
    assert "mappings: []" in content
