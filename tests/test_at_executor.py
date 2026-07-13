# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only

import os
import sys
import types
from pathlib import Path
import unittest.mock

import pytest

_src_root = Path(__file__).resolve().parent.parent / "src"


def _fix_src():
    if str(_src_root) not in sys.path:
        sys.path.insert(0, str(_src_root))

    if "src" in sys.modules and not getattr(sys.modules["src"], "__spec__", None):
        mod = types.ModuleType("src")
        mod.__path__ = [str(_src_root)]
        mod.__package__ = "src"
        mod.__file__ = str(_src_root / "__init__.py")
        sys.modules["src"] = mod


_fix_src()


def _make_fake_suite_dict():
    return {
        "name": "test-suite",
        "app": "test-app",
        "specs": [
            {
                "id": "spec-001",
                "name": "open and close",
                "steps": [
                    {"action": "keyboard_press", "key": "Return"},
                    {"action": "wait", "wait": 500},
                ],
                "tags": ["smoke"],
            },
        ],
    }


class TestParserModels:
    def test_env_check_item(self):
        from src.at.parser.models import EnvCheckItem
        item = EnvCheckItem(type="process", name="dde-file-manager", expect="not_running")
        assert item.type == "process"

    def test_suite_case_extended_fields(self):
        from src.at.parser.models import SuiteCase, SuiteActionStep
        case = SuiteCase(
            id="test-001",
            name="test case",
            tags=["L1"],
            skip="skip reason",
            timeout=10,
            assert_steps=[SuiteActionStep(action="wait", wait=100)],
        )
        assert case.tags == ["L1"]
        assert case.skip == "skip reason"
        assert case.timeout == 10
        assert len(case.assert_steps) == 1

    def test_suite_config_extended_fields(self):
        from src.at.parser.models import SuiteConfig, EnvCheckItem
        config = SuiteConfig(
            name="test",
            app="test-app",
            tags=["smoke"],
            skip="not ready",
            fast_fail=True,
            env_check=[EnvCheckItem(type="process", name="x", expect="not_running")],
        )
        assert config.fast_fail is True
        assert config.skip == "not ready"
        assert len(config.env_check) == 1

    def test_suite_config_specs_not_suites(self):
        from src.at.parser.models import SuiteConfig
        data = {"name": "test", "specs": [{"id": "s1"}]}
        config = SuiteConfig.model_validate(data)
        assert len(config.specs) == 1

    def test_suite_action_step_value_field(self):
        from src.at.parser.models import SuiteActionStep
        step = SuiteActionStep(action="mouse_scroll", value=3)
        assert step.value == 3


class TestExecutorModels:
    def test_spec_result_default_passed(self):
        from src.at.executor.models import AtSpecResult, SpecStatus
        r = AtSpecResult(id="s1")
        assert r.status == SpecStatus.PASSED

    def test_suite_result(self):
        from src.at.executor.models import AtSuiteResult, AtSpecResult, SpecStatus
        r = AtSuiteResult(suite_name="x")
        r.specs.append(AtSpecResult(id="s1", status=SpecStatus.FAILED))
        assert r.failed == 0
        assert len(r.specs) == 1

    def test_spec_result_from_dict(self):
        from src.at.executor.models import AtSpecResult
        r = AtSpecResult.model_validate({"id": "s1", "status": "skipped", "error": "env"})
        assert r.status.value == "skipped"


class TestCrashMonitor:
    def test_initial_state_inactive(self):
        from src.at.executor.crash_monitor import CrashMonitor
        cm = CrashMonitor()
        assert not cm.active
        assert cm.check()
        assert cm.crash_reason == ""

    def test_start_and_check_alive(self):
        from src.at.executor.crash_monitor import CrashMonitor
        cm = CrashMonitor()
        cm.start("test-app", os.getpid())
        assert cm.active
        assert cm.check()

    def test_check_dead_process(self):
        from src.at.executor.crash_monitor import CrashMonitor
        cm = CrashMonitor()
        cm.start("ghost-app", 99999)
        result = cm.check()
        assert not result
        assert not cm.active
        assert "ghost-app" in cm.crash_reason
        assert "99999" in cm.crash_reason

    def test_stop(self):
        from src.at.executor.crash_monitor import CrashMonitor
        cm = CrashMonitor()
        cm.start("test-app", os.getpid())
        cm.stop()
        assert not cm.active

    def test_negative_pid_always_alive(self):
        from src.at.executor.crash_monitor import CrashMonitor
        cm = CrashMonitor()
        cm.start("test-app", -1)
        assert cm.check()

    def test_check_after_crash_stays_inactive(self):
        from src.at.executor.crash_monitor import CrashMonitor
        cm = CrashMonitor()
        cm.start("ghost", 99999)
        cm.check()
        second = cm.check()
        assert not second
        assert not cm.active


class TestHandlers:
    def test_all_handlers_callable(self):
        from src.at.executor.handlers import HANDLERS
        assert len(HANDLERS) == 31
        for name, handler in HANDLERS.items():
            assert callable(handler), f"{name} not callable"

    def test_handler_session_start(self):
        import subprocess
        from src.at.executor.handlers import handle_session_start
        from src.at.parser.models import SuiteActionStep
        step = SuiteActionStep(action="session_start", command="echo hello")
        ctx = {}
        handle_session_start(step, ctx)
        assert "app_process" in ctx

    def test_handler_wait_noop(self):
        from src.at.executor.handlers import handle_wait
        from src.at.parser.models import SuiteActionStep
        step = SuiteActionStep(action="wait", wait=100)
        handle_wait(step, {})

    def test_resolve_ref(self):
        from src.at.executor.handlers import resolve_ref
        elements = {"ok_btn": {"name": "OK", "role": "push button"}}
        result = resolve_ref("ok_btn", elements)
        assert result["name"] == "OK"

    def test_resolve_ref_missing_raises(self):
        from src.at.executor.handlers import resolve_ref
        with pytest.raises(ValueError, match="not found"):
            resolve_ref("nonexistent", {})

    def test_resolve_step_attrs_with_ref(self):
        from src.at.executor.handlers import resolve_step_attrs
        from src.at.parser.models import SuiteActionStep
        elements = {"btn": {"name": "OK", "x": 100, "y": 200}}
        step = SuiteActionStep(action="mouse_click", ref="btn")
        attrs = resolve_step_attrs(step, elements)
        assert attrs["name"] == "OK"

    def test_resolve_step_attrs_no_ref(self):
        from src.at.executor.handlers import resolve_step_attrs
        from src.at.parser.models import SuiteActionStep
        step = SuiteActionStep(action="mouse_click", x=50, y=60)
        attrs = resolve_step_attrs(step, {})
        assert attrs["x"] == 50
        assert attrs["y"] == 60


class TestRunnerFindSuites:
    def test_finds_suite_files(self, tmp_path):
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "test.suite.yaml").write_text("{}")
        (tmp_path / "readme.txt").write_text("")
        from src.at.executor.runner import _find_suite_files
        result = _find_suite_files(str(tmp_path))
        assert len(result) == 1
        assert result[0].name == "test.suite.yaml"

    def test_filter_by_suite_name(self, tmp_path):
        (tmp_path / "menu.suite.yaml").write_text("{}")
        (tmp_path / "play.suite.yaml").write_text("{}")
        from src.at.executor.runner import _find_suite_files
        result = _find_suite_files(str(tmp_path), suite_name="menu")
        assert len(result) == 1

    def test_nonexistent_dir_returns_empty(self):
        from src.at.executor.runner import _find_suite_files
        result = _find_suite_files("/nonexistent/path")
        assert result == []


class TestRunnerLoadAndRun:
    def test_load_invalid_yaml(self, tmp_path):
        bad = tmp_path / "bad.suite.yaml"
        bad.write_bytes(b"\x00\x01")
        from src.at.executor.runner import _load_and_run_suite
        r = _load_and_run_suite(bad)
        assert r["status"] == "error"

    def test_load_valid_suite(self):
        yaml_data = _make_fake_suite_dict()
        mock_path = unittest.mock.MagicMock()
        mock_path.__str__ = lambda self: "/tmp/test.suite.yaml"
        mock_path.parent = Path("/tmp")

        from src.at.executor.runner import _load_and_run_suite

        with (
            unittest.mock.patch("src.at.executor.runner._parse_yaml", return_value=yaml_data),
            unittest.mock.patch("src.at.executor.executor.execute_steps", return_value=None),
        ):
            r = _load_and_run_suite(mock_path)
            assert r["status"] == "ok"
            assert r["passed"] == 1

    def test_load_invalid_schema(self):
        mock_path = unittest.mock.MagicMock()
        mock_path.__str__ = lambda self: "/tmp/bad.suite.yaml"
        from src.at.executor.runner import _load_and_run_suite
        with unittest.mock.patch("src.at.executor.runner._parse_yaml", return_value={"bad": "data"}):
            r = _load_and_run_suite(mock_path)
            assert r["status"] == "error"


class TestRunTests:
    def test_no_suites_returns_zero(self, tmp_path):
        from src.at.executor.runner import run_tests
        with unittest.mock.patch("src.at.executor.runner._find_suite_files", return_value=[]):
            rc = run_tests(test_dir=str(tmp_path))
            assert rc == 0

    def test_all_passed_returns_zero(self):
        from src.at.executor.runner import run_tests
        mock_path = unittest.mock.MagicMock()
        mock_path.__str__ = lambda self: "/tmp/suite.suite.yaml"
        ok_result = {
            "suite": "/tmp/suite.suite.yaml", "status": "ok",
            "passed": 2, "failed": 0, "skipped": 0, "timeout": 0,
            "duration": 1.0, "specs": [],
        }
        with (
            unittest.mock.patch("src.at.executor.runner._find_suite_files", return_value=[mock_path]),
            unittest.mock.patch("src.at.executor.runner._load_and_run_suite", return_value=ok_result),
        ):
            rc = run_tests()
            assert rc == 0

    def test_has_failure_returns_one(self):
        from src.at.executor.runner import run_tests
        mock_path = unittest.mock.MagicMock()
        mock_path.__str__ = lambda self: "/tmp/suite.suite.yaml"
        fail_result = {
            "suite": "/tmp/suite.suite.yaml", "status": "ok",
            "passed": 1, "failed": 1, "skipped": 0, "timeout": 0,
            "duration": 2.0, "specs": [],
        }
        with (
            unittest.mock.patch("src.at.executor.runner._find_suite_files", return_value=[mock_path]),
            unittest.mock.patch("src.at.executor.runner._load_and_run_suite", return_value=fail_result),
        ):
            rc = run_tests()
            assert rc == 1


class TestExecutorFlow:
    def test_env_check_skip_all(self):
        from src.at.executor.executor import AtSuiteExecutor
        from src.at.parser.models import SuiteConfig, EnvCheckItem, SuiteCase

        config = SuiteConfig(
            name="test",
            app="test-app",
            env_check=[EnvCheckItem(type="process", name="nonexistent_proc_xyz_123", expect="running")],
            specs=[SuiteCase(id="s1", name="spec1")],
        )
        ex = AtSuiteExecutor(config)
        result = ex.run(skip_env_check=False)
        assert result.total == 1
        assert result.skipped == 1

    def test_skip_env_check_flag(self):
        from src.at.executor.executor import AtSuiteExecutor
        from src.at.parser.models import SuiteConfig, EnvCheckItem, SuiteCase

        config = SuiteConfig(
            name="test",
            app="test-app",
            env_check=[EnvCheckItem(type="process", name="nonexistent_proc_xyz_123", expect="running")],
            specs=[SuiteCase(id="s1", name="spec1")],
        )
        with unittest.mock.patch("src.at.executor.executor.execute_steps", return_value=None):
            ex = AtSuiteExecutor(config)
            result = ex.run(skip_env_check=True)
        assert result.passed == 1

    def test_spec_skip_field(self):
        from src.at.executor.executor import AtSuiteExecutor
        from src.at.parser.models import SuiteConfig, SuiteCase

        config = SuiteConfig(
            name="test", app="test-app",
            specs=[SuiteCase(id="s1", name="spec1", skip="not implemented")],
        )
        ex = AtSuiteExecutor(config)
        result = ex.run()
        assert result.skipped == 1

    def test_spec_ids_filter(self):
        from src.at.executor.executor import AtSuiteExecutor
        from src.at.parser.models import SuiteConfig, SuiteCase

        config = SuiteConfig(
            name="test", app="test-app",
            specs=[SuiteCase(id="s1", name="a"), SuiteCase(id="s2", name="b")],
        )
        with unittest.mock.patch("src.at.executor.executor.execute_steps", return_value=None):
            ex = AtSuiteExecutor(config)
            result = ex.run(spec_ids="s2")
        assert result.total == 1

    def test_tags_filter(self):
        from src.at.executor.executor import AtSuiteExecutor
        from src.at.parser.models import SuiteConfig, SuiteCase

        config = SuiteConfig(
            name="test", app="test-app",
            specs=[
                SuiteCase(id="s1", name="a", tags=["L1"]),
                SuiteCase(id="s2", name="b", tags=["L2"]),
            ],
        )
        with unittest.mock.patch("src.at.executor.executor.execute_steps", return_value=None):
            ex = AtSuiteExecutor(config)
            result = ex.run(tags="L2")
        assert result.total == 1
        assert result.specs[0].id == "s2"

    def test_fast_fail(self):
        from src.at.executor.executor import AtSuiteExecutor
        from src.at.parser.models import SuiteConfig, SuiteCase, SuiteActionStep

        config = SuiteConfig(
            name="test", app="test-app", fast_fail=True,
            specs=[
                SuiteCase(id="s1", name="fail", steps=[SuiteActionStep(action="session_start", command="__nonexistent_cmd_xyz__")]),
                SuiteCase(id="s2", name="skip"),
            ],
        )
        with unittest.mock.patch("src.at.executor.executor.execute_steps", return_value="action failed"):
            ex = AtSuiteExecutor(config)
            result = ex.run()
        assert result.failed == 1
        assert result.skipped == 1


class TestNoYamlTestImport:
    def test_executor_modules_no_yaml_test_import(self):
        import ast
        import importlib

        modules_to_check = [
            "src.at.executor.runner",
            "src.at.executor.executor",
            "src.at.executor.handlers",
            "src.at.executor.menu_nav",
            "src.at.executor.models",
        ]
        for mod_name in modules_to_check:
            mod = importlib.import_module(mod_name)
            source = ast.parse(open(mod.__file__).read())
            for node in ast.walk(source):
                if isinstance(node, ast.ImportFrom) and node.module and "yaml_test" in node.module:
                    pytest.fail(f"{mod_name} imports from src.yaml_test: {node.module}")
