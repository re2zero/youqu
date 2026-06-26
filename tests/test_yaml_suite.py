# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only
"""Unit tests for src.yaml_test.suite — parser, models, executor."""

from src.yaml_test.suite.models import (
    EnvCheckItem,
    SpecResult,
    SuiteResult,
    SuiteSpec,
    SuiteSpecItem,
)
from src.yaml_test.suite.parser import SuiteValidationError, parse_suite


_MINIMAL_SUITE_YAML = """\
name: "最小套件"
specs:
  - id: spec1
    name: "操作一"
    steps:
      - action: wait
        wait: 0.1
"""


_FULL_SUITE_YAML = """\
name: "键盘快捷键自测"
app: "deepin-reader"
module: "键盘"
env_check:
  - type: process
    name: "deepin-reader"
    expect: "not_running"
setup:
  - action: session_start
    command: "deepin-reader"
specs:
  - id: shortcut_copy
    name: "Ctrl+C 复制"
    tags: ["shortcut"]
    steps:
      - action: keyboard_hot_key
        keys: "Ctrl+C"
      - action: wait
        wait: 0.3
  - id: shortcut_paste
    name: "Ctrl+V 粘贴"
    tags: ["shortcut", "clipboard"]
    skip: "需文档已打开"
    steps:
      - action: keyboard_hot_key
        keys: "Ctrl+V"
teardown:
  - action: session_stop
"""


class TestSuiteSpecModel:
    def test_minimal_suite(self):
        suite = SuiteSpec.model_validate({
            "name": "test",
            "specs": [{"id": "s1", "steps": [{"action": "wait", "wait": 0.1}]}],
        })
        assert suite.name == "test"
        assert len(suite.specs) == 1
        assert suite.specs[0].id == "s1"

    def test_full_suite_with_env_check(self):
        suite = SuiteSpec.model_validate({
            "name": "键盘快捷键自测",
            "app": "deepin-reader",
            "module": "键盘",
            "env_check": [{"type": "process", "name": "deepin-reader", "expect": "not_running"}],
            "setup": [{"action": "session_start", "command": "deepin-reader"}],
            "specs": [
                {"id": "s1", "name": "Ctrl+C", "tags": ["shortcut"],
                 "steps": [{"action": "keyboard_hot_key", "keys": "Ctrl+C"}]},
                {"id": "s2", "name": "Ctrl+V", "skip": "需文档已打开",
                 "steps": [{"action": "keyboard_hot_key", "keys": "Ctrl+V"}]},
            ],
            "teardown": [{"action": "session_stop"}],
        })
        assert len(suite.specs) == 2
        assert suite.specs[0].id == "s1"
        assert suite.specs[1].skip == "需文档已打开"
        assert suite.specs[0].tags == ["shortcut"]

    def test_suite_spec_item_extra_fields(self):
        item = SuiteSpecItem.model_validate({
            "id": "x1", "steps": [{"action": "wait", "wait": 0.1}],
            "custom_field": "anything",
        })
        assert item.id == "x1"

    def test_suite_spec_extra_fields(self):
        suite = SuiteSpec.model_validate({
            "name": "test",
            "description": "desc",
            "tags": ["dev", "L1"],
            "fast_fail": True,
            "specs": [{"id": "s1", "steps": [{"action": "wait", "wait": 0.1}]}],
        })
        assert suite.fast_fail is True
        assert "dev" in suite.tags

    def test_env_check_model(self):
        item = EnvCheckItem(type="process", name="myapp", expect="not_running")
        assert item.type == "process"
        assert item.name == "myapp"
        assert item.expect == "not_running"


class TestSuiteParser:
    def test_parse_minimal(self, tmp_path):
        p = tmp_path / "test.suite.yaml"
        p.write_text(_MINIMAL_SUITE_YAML, encoding="utf-8")
        suite = parse_suite(p)
        assert suite.name == "最小套件"
        assert len(suite.specs) == 1
        assert suite.specs[0].id == "spec1"

    def test_parse_full(self, tmp_path):
        p = tmp_path / "full.suite.yaml"
        p.write_text(_FULL_SUITE_YAML, encoding="utf-8")
        suite = parse_suite(p)
        assert suite.name == "键盘快捷键自测"
        assert suite.app == "deepin-reader"
        assert suite.module == "键盘"
        assert len(suite.env_check) == 1
        assert suite.env_check[0].type == "process"
        assert len(suite.setup) == 1
        assert suite.setup[0]["action"] == "session_start"
        assert len(suite.specs) == 2
        assert suite.specs[0].name == "Ctrl+C 复制"
        assert suite.specs[1].skip == "需文档已打开"
        assert len(suite.teardown) == 1

    def test_parse_empty_file(self, tmp_path):
        p = tmp_path / "empty.suite.yaml"
        p.write_text("", encoding="utf-8")
        try:
            parse_suite(p)
            assert False, "should raise"
        except SuiteValidationError as e:
            assert "empty" in str(e) or "parse failed" in str(e)

    def test_parse_no_specs(self, tmp_path):
        p = tmp_path / "no_specs.suite.yaml"
        p.write_text("name: test\n", encoding="utf-8")
        try:
            parse_suite(p)
            assert False, "should raise"
        except SuiteValidationError as e:
            assert "specs" in str(e)

    def test_parse_empty_specs_list(self, tmp_path):
        p = tmp_path / "empty_specs.suite.yaml"
        p.write_text("name: test\nspecs: []\n", encoding="utf-8")
        try:
            parse_suite(p)
            assert False, "should raise"
        except SuiteValidationError as e:
            assert "specs" in str(e)

    def test_parse_not_a_mapping(self, tmp_path):
        p = tmp_path / "bad_root.suite.yaml"
        p.write_text("- just\na list\n", encoding="utf-8")
        try:
            parse_suite(p)
            assert False, "should raise"
        except SuiteValidationError as e:
            assert "mapping" in str(e).lower()

    def test_parse_file_not_found(self, tmp_path):
        try:
            parse_suite(tmp_path / "nonexistent.suite.yaml")
            assert False, "should raise"
        except FileNotFoundError:
            pass


class TestSuiteResultModel:
    def test_empty_result(self):
        r = SuiteResult()
        assert r.passed == 0
        assert r.total == 0
        assert r.specs == []

    def test_result_with_specs(self):
        r = SuiteResult(
            suite_name="test",
            passed=2,
            failed=1,
            skipped=0,
            total=3,
            specs=[
                SpecResult(id="s1", name="A", status="passed"),
                SpecResult(id="s2", name="B", status="passed"),
                SpecResult(id="s3", name="C", status="failed", error="crash"),
            ],
            duration=1.5,
        )
        assert r.passed == 2
        assert r.failed == 1
        assert r.specs[2].status == "failed"
        assert r.specs[2].error == "crash"


class TestSuiteExecutorUnit:
    """Unit tests for SuiteExecutor with mocked step execution.

    These test filter logic, skip logic, and result aggregation
    without requiring a desktop environment.
    """

    def test_filter_spec_ids(self):
        from src.yaml_test.suite.executor import SuiteExecutor

        suite = SuiteSpec.model_validate({
            "name": "test",
            "specs": [
                {"id": "s1", "steps": [{"action": "wait", "wait": 0.1}]},
                {"id": "s2", "steps": [{"action": "wait", "wait": 0.1}]},
                {"id": "s3", "steps": [{"action": "wait", "wait": 0.1}]},
            ],
        })
        executor = SuiteExecutor(suite)
        filtered = executor._filter_specs("s1,s3", None)
        assert len(filtered) == 2
        assert filtered[0].id == "s1"
        assert filtered[1].id == "s3"

    def test_filter_spec_tags(self):
        from src.yaml_test.suite.executor import SuiteExecutor

        suite = SuiteSpec.model_validate({
            "name": "test",
            "specs": [
                {"id": "s1", "tags": ["shortcut"], "steps": [{"action": "wait", "wait": 0.1}]},
                {"id": "s2", "tags": ["clipboard"], "steps": [{"action": "wait", "wait": 0.1}]},
                {"id": "s3", "tags": ["shortcut", "clipboard"], "steps": [{"action": "wait", "wait": 0.1}]},
            ],
        })
        executor = SuiteExecutor(suite)
        filtered = executor._filter_specs(None, "shortcut")
        assert len(filtered) == 2
        assert filtered[0].id == "s1"
        assert filtered[1].id == "s3"

    def test_filter_spec_ids_and_tags(self):
        from src.yaml_test.suite.executor import SuiteExecutor

        suite = SuiteSpec.model_validate({
            "name": "test",
            "specs": [
                {"id": "s1", "tags": ["shortcut"], "steps": [{"action": "wait", "wait": 0.1}]},
                {"id": "s2", "tags": ["clipboard"], "steps": [{"action": "wait", "wait": 0.1}]},
            ],
        })
        executor = SuiteExecutor(suite)
        filtered = executor._filter_specs("s1", "shortcut")
        assert len(filtered) == 1
        assert filtered[0].id == "s1"

    def test_skip_reason_marks_skipped(self):
        from src.yaml_test.suite.executor import SuiteExecutor

        suite = SuiteSpec.model_validate({
            "name": "test",
            "specs": [
                {"id": "s1", "steps": [{"action": "wait", "wait": 0.1}]},
                {"id": "s2", "skip": "硬件依赖", "steps": [{"action": "wait", "wait": 0.1}]},
            ],
        })
        executor = SuiteExecutor(suite)
        result = executor.run(skip_env_check=True)
        assert result.passed == 1
        assert result.skipped == 1
        assert result.failed == 0

    def test_empty_specs_list(self):
        from src.yaml_test.suite.executor import SuiteExecutor

        suite = SuiteSpec.model_validate({
            "name": "empty", "specs": [],
        })
        executor = SuiteExecutor(suite)
        result = executor.run()
        assert result.total == 0
        assert result.passed == 0
