# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

import sys
import types
from pathlib import Path

_src_root = Path(__file__).resolve().parent.parent / "src"
if str(_src_root) not in sys.path:
    sys.path.insert(0, str(_src_root))
stub = sys.modules.get("src")
if stub is not None and getattr(stub, "__spec__", None) is None:
    sys.modules["src"] = types.ModuleType("src")
    sys.modules["src"].__path__ = [str(_src_root)]
    sys.modules["src"].__package__ = "src"
    sys.modules["src"].__file__ = str(_src_root / "__init__.py")

import pytest
from pydantic import ValidationError


class TestAtTreeModels:
    def test_minimal_at_tree(self):
        from src.at.parser.models import AtTree, AtTreeMetadata
        tree = AtTree(metadata=AtTreeMetadata(app="test"))
        assert tree.metadata.app == "test"
        assert tree.structure == {"windows": []}

    def test_at_tree_with_children(self):
        from src.at.parser.models import AtTree, AtTreeNode, AtTreeMetadata, SourceType
        node = AtTreeNode(
            id="win1", role="window", object_name="mainWindow", source=SourceType.static,
            children=[
                AtTreeNode(id="btn1", role="push button", name="OK", source=SourceType.static),
            ],
        )
        tree = AtTree(metadata=AtTreeMetadata(app="app1"), structure={"windows": [node]})
        assert len(tree.structure["windows"]) == 1
        assert tree.structure["windows"][0].children[0].name == "OK"

    def test_at_tree_serialization_round_trip(self):
        from src.at.parser.models import AtTree, AtTreeMetadata
        tree = AtTree(metadata=AtTreeMetadata(app="app1", source_commit="abc123"))
        data = tree.model_dump()
        restored = AtTree.model_validate(data)
        assert restored.metadata.source_commit == "abc123"


class TestCasesModels:
    def test_case_step_types(self):
        from src.at.parser.models import CaseStep, ElementHint, StepType
        step = CaseStep(step_type=StepType.action, description="click button")
        assert step.step_type == StepType.action
        step_navigate = CaseStep(
            step_type=StepType.navigate, description="open menu",
            element_hint=ElementHint.main_menu_comb, menu_path=["文件"],
        )
        assert step_navigate.element_hint == ElementHint.main_menu_comb

    def test_case_suite(self):
        from src.at.parser.models import CaseStep, CaseSuite, ElementHint, StepType
        suite = CaseSuite(
            id="s1", name="Menu Test", module="菜单",
            steps=[
                CaseStep(step_type=StepType.navigate, description="open file menu",
                          element_hint=ElementHint.main_menu_comb, menu_path=["文件"]),
                CaseStep(step_type=StepType.action, description="click new window"),
            ],
        )
        assert len(suite.steps) == 2
        assert suite.steps[0].menu_path == ["文件"]

    def test_cases_doc_validation(self):
        from src.at.parser.models import CaseSuite, CasesDoc
        doc = CasesDoc(suites=[CaseSuite(id="s1", name="S", module="M")])
        data = doc.model_dump()
        restored = CasesDoc.model_validate(data)
        assert len(restored.suites) == 1


class TestMappingModels:
    def test_mapped_entry(self):
        from src.at.parser.models import (
            MappingEntry, MappingSelector, MappingStatus, StepType,
        )
        entry = MappingEntry(
            case_id="s1", step_index=0, description="click play",
            step_type=StepType.action, element_ref="play_btn",
            selector=MappingSelector(name="播放", role="push button"),
            status=MappingStatus.mapped,
        )
        assert entry.status == MappingStatus.mapped

    def test_unmapped_entry(self):
        from src.at.parser.models import MappingEntry, MappingStatus, StepType
        entry = MappingEntry(
            case_id="s1", step_index=2, description="click export",
            step_type=StepType.action, status=MappingStatus.unmapped,
            reason="no matching element", fix_suggestion="add setAccessibleName",
        )
        assert entry.fix_suggestion == "add setAccessibleName"

    def test_mappings_doc(self):
        from src.at.parser.models import MappingEntry, ElementMappingsDoc, StepType
        doc = ElementMappingsDoc(
            mappings=[MappingEntry(case_id="s1", step_index=0, description="test",
                                   step_type=StepType.action)],
        )
        assert len(doc.mappings) == 1


class TestSuiteConfigModels:
    def test_suite_config_with_setup_teardown(self):
        from src.at.parser.models import SuiteActionStep, SuiteCase, SuiteConfig
        config = SuiteConfig(
            name="test_suite", app="app1",
            setup=[SuiteActionStep(action="session_start", command="app1", wait=3000)],
            suites=[
                SuiteCase(id="c1", steps=[
                    SuiteActionStep(action="element_action", ref="btn1", do="click"),
                ], assert_steps=[
                    SuiteActionStep(action="assert_element_exists", ref="btn1"),
                ]),
            ],
            teardown=[SuiteActionStep(action="session_stop")],
        )
        assert len(config.setup) == 1
        assert len(config.suites) == 1
        assert len(config.suites[0].assert_steps) == 1

    def test_suite_action_step_all_fields(self):
        from src.at.parser.models import SuiteActionStep
        step = SuiteActionStep(action="main_menu_comb", items=["文件", "新建窗口"])
        assert step.items == ["文件", "新建窗口"]

    def test_suite_config_serialization(self):
        from src.at.parser.models import SuiteConfig
        config = SuiteConfig(name="s", app="a")
        data = config.model_dump()
        restored = SuiteConfig.model_validate(data)
        assert restored.name == "s"


class TestElementHint:
    def test_all_hints(self):
        from src.at.parser.models import ElementHint
        hints = list(ElementHint)
        assert len(hints) == 25
        assert ElementHint.main_menu_comb in hints
        assert ElementHint.context_menu_comb in hints

    def test_invalid_hint(self):
        from src.at.parser.models import CaseStep, StepType
        with pytest.raises(ValidationError):
            CaseStep(step_type=StepType.action, description="test", element_hint="invalid_hint")


class TestVariableSubstitution:
    def test_basic_substitution(self):
        from src.at.parser.variables import substitute
        result = substitute("${PROJECT_ROOT}/test", {"PROJECT_ROOT": "/opt/app"})
        assert result == "/opt/app/test"

    def test_env_var_fallback(self):
        import os
        from src.at.parser.variables import substitute
        os.environ["YOUQU_CUSTOM_VAR"] = "env_value"
        result = substitute("${CUSTOM_VAR}/path", {})
        assert result == "env_value/path"
        del os.environ["YOUQU_CUSTOM_VAR"]

    def test_no_substitution(self):
        from src.at.parser.variables import substitute
        result = substitute("plain text", {})
        assert result == "plain text"

    def test_dict_substitution(self):
        from src.at.parser.variables import substitute_dict
        data = {"path": "${PROJECT_ROOT}/test", "nested": {"key": "${NAME}"}}
        result = substitute_dict(data, {"PROJECT_ROOT": "/opt", "NAME": "app"})
        assert result["path"] == "/opt/test"
        assert result["nested"]["key"] == "app"

    def test_list_substitution(self):
        from src.at.parser.variables import substitute_dict
        data = ["${A}", "${B}"]
        result = substitute_dict(data, {"A": "1", "B": "2"})
        assert result == ["1", "2"]

