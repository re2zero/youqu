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
        "suites": [
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

    def test_suite_config_suites_field(self):
        from src.at.parser.models import SuiteConfig

        data = {"name": "test", "suites": [{"id": "s1"}]}
        config = SuiteConfig.model_validate(data)
        assert len(config.suites) == 1

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

        assert len(HANDLERS) == 34
        for name, handler in HANDLERS.items():
            assert callable(handler), f"{name} not callable"

    def test_handler_session_start(self):
        import subprocess
        from src.at.executor import handlers
        from src.at.executor.handlers import handle_session_start
        from src.at.parser.models import SuiteActionStep

        step = SuiteActionStep(action="session_start", command="echo hello")
        ctx = {}
        with (
            unittest.mock.patch.object(handlers, "_kill_running_app"),
            unittest.mock.patch.object(handlers.time, "sleep"),
        ):
            handle_session_start(step, ctx)
        assert "app_process" in ctx

    def test_session_start_kills_existing_app_before_launch(self):
        from src.at.executor import handlers
        from src.at.executor.handlers import handle_session_start
        from src.at.parser.models import SuiteActionStep

        step = SuiteActionStep(action="session_start", command="deepin-music")
        killed = []
        with (
            unittest.mock.patch.object(
                handlers,
                "_kill_running_app",
                side_effect=lambda n: killed.append(n),
            ),
            unittest.mock.patch.object(handlers.time, "sleep"),
            unittest.mock.patch.object(
                handlers.subprocess, "Popen", return_value=unittest.mock.MagicMock()
            ),
        ):
            ctx = {}
            handle_session_start(step, ctx)
        assert killed == ["deepin-music"]
        assert "app_process" in ctx

    def test_session_start_strips_path_for_kill(self):
        from src.at.executor import handlers
        from src.at.executor.handlers import handle_session_start
        from src.at.parser.models import SuiteActionStep

        step = SuiteActionStep(action="session_start", command="/usr/bin/deepin-music --foo")
        killed = []
        with (
            unittest.mock.patch.object(
                handlers,
                "_kill_running_app",
                side_effect=lambda n: killed.append(n),
            ),
            unittest.mock.patch.object(handlers.time, "sleep"),
            unittest.mock.patch.object(
                handlers.subprocess, "Popen", return_value=unittest.mock.MagicMock()
            ),
        ):
            handle_session_start(step, {})
        assert killed == ["deepin-music"]

    def test_session_stop_uses_kill_helper(self):
        from src.at.executor import handlers
        from src.at.executor.handlers import handle_session_stop
        from src.at.parser.models import SuiteActionStep

        step = SuiteActionStep(action="session_stop")
        proc = unittest.mock.MagicMock()
        proc.poll.return_value = None
        killed = []
        with unittest.mock.patch.object(
            handlers,
            "_kill_running_app",
            side_effect=lambda n: killed.append(n),
        ):
            handle_session_stop(step, {"app": "deepin-music", "app_process": proc})
        proc.terminate.assert_called_once()
        assert killed == ["deepin-music"]

    def test_find_element_child_index(self):
        from src.at.executor.handlers import find_element

        parent = unittest.mock.MagicMock()
        child0 = unittest.mock.MagicMock(name="child0")
        child1 = unittest.mock.MagicMock(name="child1")
        parent.children = [child0, child1]
        fake_dog = unittest.mock.MagicMock()
        fake_dog.find_element_by_attr.return_value = parent
        result = find_element(fake_dog, {"name": "View_ImageList", "child_index": 1})
        assert result is child1

    def test_find_element_child_index_negative_last(self):
        from src.at.executor.handlers import find_element

        parent = unittest.mock.MagicMock()
        c0 = unittest.mock.MagicMock()
        c1 = unittest.mock.MagicMock()
        c2 = unittest.mock.MagicMock()
        parent.children = [c0, c1, c2]
        fake_dog = unittest.mock.MagicMock()
        fake_dog.find_element_by_attr.return_value = parent
        result = find_element(fake_dog, {"name": "lst", "child_index": -1})
        assert result is c2

    def test_find_element_child_role_filter(self):
        from src.at.executor.handlers import find_element

        parent = unittest.mock.MagicMock()
        c0 = unittest.mock.MagicMock()
        c0.roleName = "panel"
        c1 = unittest.mock.MagicMock()
        c1.roleName = "list item"
        c2 = unittest.mock.MagicMock()
        c2.roleName = "list item"
        parent.children = [c0, c1, c2]
        fake_dog = unittest.mock.MagicMock()
        fake_dog.find_element_by_attr.return_value = parent
        result = find_element(
            fake_dog, {"name": "lst", "child_role": "list item", "child_index": 1}
        )
        assert result is c2

    def test_find_element_child_index_out_of_range_raises(self):
        from src.at.executor.handlers import find_element

        parent = unittest.mock.MagicMock()
        parent.children = [unittest.mock.MagicMock()]
        fake_dog = unittest.mock.MagicMock()
        fake_dog.find_element_by_attr.return_value = parent
        with pytest.raises(BaseException, match="out of range"):
            find_element(fake_dog, {"name": "lst", "child_index": 5})

    def test_resolve_coordinates_child_index(self):
        from src.at.executor.handlers import resolve_coordinates

        child = unittest.mock.MagicMock()
        child.extents = (200, 300, 40, 40)
        parent = unittest.mock.MagicMock()
        parent.extents = (10, 20, 500, 500)
        parent.children = [unittest.mock.MagicMock(), child]
        fake_dog = unittest.mock.MagicMock()
        fake_dog.find_elements_by_attr.return_value = [parent]
        with (
            unittest.mock.patch("src.at.executor.handlers.get_dog", return_value=fake_dog),
            unittest.mock.patch("src.at.executor.handlers.ensure_window_focus"),
        ):
            x, y = resolve_coordinates(
                {"name": "View_ImageList", "child_index": 1}, {"app": "test-app"}
            )
        assert x == 220
        assert y == 320

    def test_assert_element_child_index_exists(self):
        from src.at.executor.handlers import handle_assert_element
        from src.at.parser.models import SuiteActionStep

        parent = unittest.mock.MagicMock()
        child = unittest.mock.MagicMock()
        parent.children = [child]
        fake_dog = unittest.mock.MagicMock()
        fake_dog.find_element_by_attr.return_value = parent
        step = SuiteActionStep(
            action="assert_element",
            selector={"name": "lst", "child_index": 0},
        )
        with unittest.mock.patch("src.at.executor.handlers.get_dog", return_value=fake_dog):
            handle_assert_element(step, {"app": "test-app"})

    def test_assert_element_child_index_not_found_raises(self):
        from src.at.executor.handlers import handle_assert_element
        from src.at.parser.models import SuiteActionStep

        parent = unittest.mock.MagicMock()
        parent.children = []
        fake_dog = unittest.mock.MagicMock()
        fake_dog.find_element_by_attr.return_value = parent
        step = SuiteActionStep(
            action="assert_element",
            selector={"name": "lst", "child_index": 0},
        )
        with unittest.mock.patch("src.at.executor.handlers.get_dog", return_value=fake_dog):
            with pytest.raises(AssertionError, match="子元素不存在"):
                handle_assert_element(step, {"app": "test-app"})

    def test_assert_not_exists_child_index_present_raises(self):
        from src.at.executor.handlers import handle_assert_not_exists
        from src.at.parser.models import SuiteActionStep

        parent = unittest.mock.MagicMock()
        child = unittest.mock.MagicMock()
        parent.children = [child]
        fake_dog = unittest.mock.MagicMock()
        fake_dog.find_element_by_attr.return_value = parent
        step = SuiteActionStep(
            action="assert_not_exists",
            selector={"name": "lst", "child_index": 0},
        )
        with unittest.mock.patch("src.at.executor.handlers.get_dog", return_value=fake_dog):
            with pytest.raises(AssertionError, match="不应存在"):
                handle_assert_not_exists(step, {"app": "test-app"})

    def test_assert_not_exists_child_index_absent_passes(self):
        from src.at.executor.handlers import handle_assert_not_exists
        from src.at.parser.models import SuiteActionStep

        parent = unittest.mock.MagicMock()
        parent.children = []
        fake_dog = unittest.mock.MagicMock()
        fake_dog.find_element_by_attr.return_value = parent
        step = SuiteActionStep(
            action="assert_not_exists",
            selector={"name": "lst", "child_index": 0},
        )
        with unittest.mock.patch("src.at.executor.handlers.get_dog", return_value=fake_dog):
            handle_assert_not_exists(step, {"app": "test-app"})

    def test_assert_element_without_child_index_uses_expr_path(self):
        from src.at.executor.handlers import handle_assert_element
        from src.at.parser.models import SuiteActionStep

        fake_dog = unittest.mock.MagicMock()
        fake_dog.find_elements_by_attr.return_value = [unittest.mock.MagicMock()]
        step = SuiteActionStep(action="assert_element", selector={"name": "OK"})
        with unittest.mock.patch("src.at.executor.handlers.get_dog", return_value=fake_dog):
            handle_assert_element(step, {"app": "test-app"})
        fake_dog.find_elements_by_attr.assert_called_once_with("$//OK/")

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

        with unittest.mock.patch(
            "src.at.executor.runner._parse_yaml", return_value={"bad": "data"}
        ):
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
            "suite": "/tmp/suite.suite.yaml",
            "status": "ok",
            "passed": 2,
            "failed": 0,
            "skipped": 0,
            "timeout": 0,
            "duration": 1.0,
            "specs": [],
        }
        with (
            unittest.mock.patch(
                "src.at.executor.runner._find_suite_files", return_value=[mock_path]
            ),
            unittest.mock.patch(
                "src.at.executor.runner._load_and_run_suite", return_value=ok_result
            ),
        ):
            rc = run_tests()
            assert rc == 0

    def test_has_failure_returns_one(self):
        from src.at.executor.runner import run_tests

        mock_path = unittest.mock.MagicMock()
        mock_path.__str__ = lambda self: "/tmp/suite.suite.yaml"
        fail_result = {
            "suite": "/tmp/suite.suite.yaml",
            "status": "ok",
            "passed": 1,
            "failed": 1,
            "skipped": 0,
            "timeout": 0,
            "duration": 2.0,
            "specs": [],
        }
        with (
            unittest.mock.patch(
                "src.at.executor.runner._find_suite_files", return_value=[mock_path]
            ),
            unittest.mock.patch(
                "src.at.executor.runner._load_and_run_suite", return_value=fail_result
            ),
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
            env_check=[
                EnvCheckItem(type="process", name="nonexistent_proc_xyz_123", expect="running")
            ],
            suites=[SuiteCase(id="s1", name="spec1")],
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
            env_check=[
                EnvCheckItem(type="process", name="nonexistent_proc_xyz_123", expect="running")
            ],
            suites=[SuiteCase(id="s1", name="spec1")],
        )
        with unittest.mock.patch("src.at.executor.executor.execute_steps", return_value=None):
            ex = AtSuiteExecutor(config)
            result = ex.run(skip_env_check=True)
        assert result.passed == 1

    def test_spec_skip_field(self):
        from src.at.executor.executor import AtSuiteExecutor
        from src.at.parser.models import SuiteConfig, SuiteCase

        config = SuiteConfig(
            name="test",
            app="test-app",
            suites=[SuiteCase(id="s1", name="spec1", skip="not implemented")],
        )
        ex = AtSuiteExecutor(config)
        result = ex.run()
        assert result.skipped == 1

    def test_spec_ids_filter(self):
        from src.at.executor.executor import AtSuiteExecutor
        from src.at.parser.models import SuiteConfig, SuiteCase

        config = SuiteConfig(
            name="test",
            app="test-app",
            suites=[SuiteCase(id="s1", name="a"), SuiteCase(id="s2", name="b")],
        )
        with unittest.mock.patch("src.at.executor.executor.execute_steps", return_value=None):
            ex = AtSuiteExecutor(config)
            result = ex.run(spec_ids="s2")
        assert result.total == 1

    def test_tags_filter(self):
        from src.at.executor.executor import AtSuiteExecutor
        from src.at.parser.models import SuiteConfig, SuiteCase

        config = SuiteConfig(
            name="test",
            app="test-app",
            suites=[
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
            name="test",
            app="test-app",
            fast_fail=True,
            suites=[
                SuiteCase(
                    id="s1",
                    name="fail",
                    steps=[
                        SuiteActionStep(action="session_start", command="__nonexistent_cmd_xyz__")
                    ],
                ),
                SuiteCase(id="s2", name="skip"),
            ],
        )
        with unittest.mock.patch(
            "src.at.executor.executor.execute_steps", return_value="action failed"
        ):
            ex = AtSuiteExecutor(config)
            result = ex.run()
        assert result.failed == 1
        assert result.skipped == 1


class TestGetDogBasename:
    def test_get_dog_uses_basename(self):
        from src.at.executor.handlers import get_dog

        captured_app = []
        with unittest.mock.patch(
            "src.dogtail_utils.DogtailUtils",
            side_effect=lambda app="": captured_app.append(app) or unittest.mock.MagicMock(),
        ):
            context = {"app": "test-app"}
            get_dog(context, "/usr/bin/deepin-terminal")
        assert captured_app, "DogtailUtils was never instantiated"
        assert captured_app[0] == "deepin-terminal", (
            f"Expected basename 'deepin-terminal', got '{captured_app[0]}'"
        )

    def test_get_dog_basename_with_args(self):
        from src.at.executor.handlers import get_dog

        captured_app = []
        with unittest.mock.patch(
            "src.dogtail_utils.DogtailUtils",
            side_effect=lambda app="": captured_app.append(app) or unittest.mock.MagicMock(),
        ):
            context = {"app": "test-app"}
            get_dog(context, "/usr/bin/deepin-terminal --foo bar")
        assert captured_app[0] == "deepin-terminal"

    def test_get_dog_no_path_uses_app_directly(self):
        from src.at.executor.handlers import get_dog

        captured_app = []
        with unittest.mock.patch(
            "src.dogtail_utils.DogtailUtils",
            side_effect=lambda app="": captured_app.append(app) or unittest.mock.MagicMock(),
        ):
            context = {"app": "test-app"}
            get_dog(context, "deepin-terminal")
        assert captured_app[0] == "deepin-terminal"


    def test_get_dog_rebinds_when_cached_dead(self):
        from src.at.executor.handlers import get_dog

        dead_dog = unittest.mock.MagicMock()
        dead_dog.obj.dead = True
        fresh_dog = unittest.mock.MagicMock()
        context = {"app": "test-app", "dog": dead_dog}
        with unittest.mock.patch(
            "src.at.executor.handlers._bind_dog",
            return_value=fresh_dog,
        ) as mock_bind:
            result = get_dog(context, "deepin-terminal")
        assert result is fresh_dog
        mock_bind.assert_called_once_with("deepin-terminal")

    def test_get_dog_rebinds_when_obj_is_none(self):
        from src.at.executor.handlers import get_dog

        broken_dog = unittest.mock.MagicMock()
        broken_dog.obj = None
        fresh_dog = unittest.mock.MagicMock()
        context = {"app": "test-app", "dog": broken_dog}
        with unittest.mock.patch(
            "src.at.executor.handlers._bind_dog",
            return_value=fresh_dog,
        ) as mock_bind:
            result = get_dog(context, "deepin-terminal")
        assert result is fresh_dog
        mock_bind.assert_called_once_with("deepin-terminal")

    def test_get_dog_keeps_fresh_cached_dog(self):
        from src.at.executor.handlers import get_dog

        alive_dog = unittest.mock.MagicMock()
        alive_dog.obj.dead = False
        context = {"app": "test-app", "dog": alive_dog}
        with unittest.mock.patch(
            "src.at.executor.handlers._bind_dog",
            return_value=unittest.mock.MagicMock(),
        ) as mock_bind:
            result = get_dog(context, "deepin-terminal")
        assert result is alive_dog
        mock_bind.assert_not_called()

    def test_get_dog_keeps_stale_when_rebind_fails(self):
        from src.at.executor.handlers import get_dog

        dead_dog = unittest.mock.MagicMock()
        dead_dog.obj.dead = True
        context = {"app": "test-app", "dog": dead_dog}
        with unittest.mock.patch(
            "src.at.executor.handlers._bind_dog",
            side_effect=RuntimeError("app not started"),
        ) as mock_bind:
            result = get_dog(context, "deepin-terminal")
        assert result is dead_dog
        mock_bind.assert_called_once_with("deepin-terminal")


class TestWaitForAndSmartWait:
    def test_wait_condition_model_defaults(self):
        from src.at.parser.models import WaitCondition

        wc = WaitCondition(selector={"name": "OK"})
        assert wc.timeout == 3000
        assert wc.interval == 200

    def test_suite_action_step_wait_for_field(self):
        from src.at.parser.models import SuiteActionStep, WaitCondition

        step = SuiteActionStep(
            action="element_click",
            wait_for=WaitCondition(selector={"name": "OK"}, timeout=5000),
        )
        assert step.wait_for is not None
        assert step.wait_for.timeout == 5000
        assert step.wait_for.selector == {"name": "OK"}

    def test_suite_action_step_wait_after_field(self):
        from src.at.parser.models import SuiteActionStep

        step = SuiteActionStep(action="keyboard_press", key="Return", wait_after=500)
        assert step.wait_after == 500

    def test_execute_steps_wait_for_times_out(self):
        from src.at.executor import executor as exec_mod
        from src.at.parser.models import SuiteActionStep, WaitCondition

        step = SuiteActionStep(
            action="keyboard_press",
            key="Return",
            wait_for=WaitCondition(selector={"name": "nonexistent"}, timeout=100, interval=50),
        )
        with unittest.mock.patch(
            "src.at.executor.executor.get_dog",
            return_value=unittest.mock.MagicMock(find_elements_by_attr=lambda e: []),
        ):
            err = exec_mod.execute_steps([step], {"app": "test-app"})
        assert err is not None
        assert "wait_for" in err
        assert "100" in err

    def test_execute_steps_wait_for_found_proceeds(self):
        from src.at.executor import executor as exec_mod
        from src.at.parser.models import SuiteActionStep, WaitCondition

        step = SuiteActionStep(
            action="keyboard_press",
            key="Return",
            wait_for=WaitCondition(selector={"name": "OK"}, timeout=5000, interval=50),
        )
        fake_dog = unittest.mock.MagicMock(find_elements_by_attr=lambda e: ["found"])
        fake_handler = unittest.mock.MagicMock()
        with (
            unittest.mock.patch("src.at.executor.executor.get_dog", return_value=fake_dog),
            unittest.mock.patch.dict(exec_mod.HANDLERS, {"keyboard_press": fake_handler}),
        ):
            err = exec_mod.execute_steps([step], {"app": "test-app"})
        assert err is None
        fake_handler.assert_called_once()

    def test_smart_wait_peeks_next_selector(self):
        from src.at.executor import executor as exec_mod
        from src.at.parser.models import SuiteActionStep

        step1 = SuiteActionStep(action="keyboard_press", key="Return", wait=2.0)
        step2 = SuiteActionStep(action="element_click", selector={"name": "Save"})
        fake_dog = unittest.mock.MagicMock()
        fake_dog.find_elements_by_attr.return_value = ["found"]
        fake_handler = unittest.mock.MagicMock()
        with (
            unittest.mock.patch("src.at.executor.executor.get_dog", return_value=fake_dog),
            unittest.mock.patch.dict(
                exec_mod.HANDLERS,
                {"keyboard_press": fake_handler, "element_click": unittest.mock.MagicMock()},
            ),
        ):
            err = exec_mod.execute_steps([step1, step2], {"app": "test-app"})
        assert err is None
        assert fake_dog.find_elements_by_attr.call_count > 0

    def test_smart_wait_falls_back_to_sleep_no_selector(self):
        from src.at.executor import executor as exec_mod
        from src.at.parser.models import SuiteActionStep

        step1 = SuiteActionStep(action="keyboard_press", key="Return", wait=0.01)
        step2 = SuiteActionStep(action="keyboard_press", key="Escape")
        fake_handler = unittest.mock.MagicMock()
        with (
            unittest.mock.patch("src.at.executor.executor.get_dog") as mock_get_dog,
            unittest.mock.patch.dict(exec_mod.HANDLERS, {"keyboard_press": fake_handler}),
        ):
            err = exec_mod.execute_steps([step1, step2], {"app": "test-app"})
        assert err is None
        mock_get_dog.assert_not_called()

    def test_wait_after_sleeps_ms(self):
        from src.at.executor import executor as exec_mod
        from src.at.parser.models import SuiteActionStep

        step = SuiteActionStep(action="keyboard_press", key="Return", wait_after=50)
        fake_handler = unittest.mock.MagicMock()
        with (
            unittest.mock.patch.dict(exec_mod.HANDLERS, {"keyboard_press": fake_handler}),
            unittest.mock.patch.object(exec_mod.time, "sleep") as mock_sleep,
        ):
            exec_mod.execute_steps([step], {"app": "test-app"})
        sleep_calls = [c for c in mock_sleep.call_args_list]
        assert len(sleep_calls) >= 1
        assert sleep_calls[-1] == unittest.mock.call(0.05)


class TestExecuteTeardownResilience:
    def test_teardown_continues_after_step_failure(self):
        from src.at.executor import executor as exec_mod
        from src.at.parser.models import SuiteActionStep

        step1 = SuiteActionStep(action="session_stop")
        step2 = SuiteActionStep(action="keyboard_press", key="Escape")
        handler1 = unittest.mock.MagicMock(side_effect=RuntimeError("boom"))
        handler2 = unittest.mock.MagicMock()
        with unittest.mock.patch.dict(
            exec_mod.HANDLERS, {"session_stop": handler1, "keyboard_press": handler2}
        ):
            exec_mod.execute_teardown_steps([step1, step2], {"app": "test-app"})
        handler1.assert_called_once()
        handler2.assert_called_once()

    def test_teardown_handles_all_steps_failing(self):
        from src.at.executor import executor as exec_mod
        from src.at.parser.models import SuiteActionStep

        steps = [
            SuiteActionStep(action="session_stop"),
            SuiteActionStep(action="keyboard_press", key="Escape"),
            SuiteActionStep(action="mouse_click", x=100, y=200),
        ]
        handlers = [
            unittest.mock.MagicMock(side_effect=RuntimeError(f"fail-{i}")) for i in range(3)
        ]
        with unittest.mock.patch.dict(
            exec_mod.HANDLERS,
            {
                "session_stop": handlers[0],
                "keyboard_press": handlers[1],
                "mouse_click": handlers[2],
            },
        ):
            exec_mod.execute_teardown_steps(steps, {"app": "test-app"})
        for h in handlers:
            h.assert_called_once()

    def test_teardown_respects_wait_and_wait_after(self):
        from src.at.executor import executor as exec_mod
        from src.at.parser.models import SuiteActionStep

        step = SuiteActionStep(action="session_stop", wait=0.01, wait_after=20)
        fake_handler = unittest.mock.MagicMock()
        with (
            unittest.mock.patch.dict(exec_mod.HANDLERS, {"session_stop": fake_handler}),
            unittest.mock.patch("src.at.executor.executor.time") as mock_time,
        ):
            mock_time.sleep = unittest.mock.MagicMock()
            exec_mod.execute_teardown_steps([step], {"app": "test-app"})
        mock_time.sleep.assert_any_call(0.01)
        mock_time.sleep.assert_any_call(0.02)


class TestEnsureWindowFocus:
    def test_ensure_window_focus_exists(self):
        from src.at.executor import handlers

        assert hasattr(handlers, "ensure_window_focus")

    def test_ensure_window_focus_called_in_resolve_coordinates(self):
        import inspect
        from src.at.executor.handlers import resolve_coordinates

        source = inspect.getsource(resolve_coordinates)
        assert "ensure_window_focus" in source

    def test_ensure_window_focus_called_in_keyboard_hot_key(self):
        import inspect
        from src.at.executor.handlers import handle_keyboard_hot_key

        source = inspect.getsource(handle_keyboard_hot_key)
        assert "ensure_window_focus" in source


class TestResolveCoordinatesFallback:
    def test_resolve_coordinates_empty_attrs_raises(self):
        from src.at.executor.handlers import resolve_coordinates

        with (
            unittest.mock.patch("src.at.executor.handlers.get_dog"),
            unittest.mock.patch("src.at.executor.handlers.ensure_window_focus"),
        ):
            with pytest.raises(BaseException, match="no locator"):
                resolve_coordinates({}, {"app": "test-app"})

    def test_resolve_coordinates_locator_not_found_raises(self):
        from src.at.executor.handlers import resolve_coordinates

        fake_dog = unittest.mock.MagicMock()
        fake_dog.find_elements_by_attr.return_value = []
        with (
            unittest.mock.patch("src.at.executor.handlers.get_dog", return_value=fake_dog),
            unittest.mock.patch("src.at.executor.handlers.ensure_window_focus"),
        ):
            with pytest.raises(BaseException, match="not found"):
                resolve_coordinates({"name": "nonexistent"}, {"app": "test-app"})

    def test_resolve_coordinates_prefers_element_center(self):
        from src.at.executor.handlers import resolve_coordinates

        attrs = {"x": 10, "y": 20}
        with (
            unittest.mock.patch("src.at.executor.handlers.get_dog") as mock_get_dog,
            unittest.mock.patch("src.at.executor.handlers.ensure_window_focus"),
        ):
            x, y = resolve_coordinates(attrs, {"app": "test-app"})
        assert (x, y) == (10, 20)
        mock_get_dog.assert_not_called()

    def test_resolve_coordinates_uses_xy_when_no_element(self):
        from src.at.executor.handlers import resolve_coordinates

        attrs = {"x": 50, "y": 60}
        with (
            unittest.mock.patch("src.at.executor.handlers.get_dog") as mock_get_dog,
            unittest.mock.patch("src.at.executor.handlers.ensure_window_focus"),
        ):
            x, y = resolve_coordinates(attrs, {"app": "test-app"})
        assert (x, y) == (50, 60)
        mock_get_dog.assert_not_called()


class TestTimeoutValues:
    def test_step_timeout_is_15s(self):
        from src.at.executor import executor as exec_mod

        assert exec_mod._STEP_TIMEOUT == 15

    def test_spec_timeout_is_60s(self):
        from src.at.executor import executor as exec_mod

        assert exec_mod._SPEC_TIMEOUT == 60

    def test_execute_steps_respects_expired_deadline(self):
        import time as _time
        from src.at.executor import executor as exec_mod
        from src.at.parser.models import SuiteActionStep

        step = SuiteActionStep(action="keyboard_press", key="Return")
        past_deadline = _time.monotonic() - 1
        err = exec_mod.execute_steps([step], {"app": "test-app"}, deadline=past_deadline)
        assert err is not None
        assert "timed out" in err

    def test_execute_steps_no_deadline_by_default(self):
        from src.at.executor import executor as exec_mod
        from src.at.parser.models import SuiteActionStep

        step = SuiteActionStep(action="keyboard_press", key="Return")
        fake_handler = unittest.mock.MagicMock()
        with unittest.mock.patch.dict(exec_mod.HANDLERS, {"keyboard_press": fake_handler}):
            err = exec_mod.execute_steps([step], {"app": "test-app"})
        assert err is None
        fake_handler.assert_called_once()


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


class TestExecutorHardening:
    """Tests for AT executor code patches (accessible_id, hierarchy, fail-fast,
    do whitelist, smart_wait warning)."""

    def test_find_element_accessible_id(self):
        from src.at.executor.handlers import find_element

        fake_element = unittest.mock.MagicMock()
        fake_dog = unittest.mock.MagicMock()
        fake_dog.find_elements_by_accessible_id.return_value = [fake_element]
        result = find_element(fake_dog, {"accessible_id": "search_input"})
        assert result is fake_element
        fake_dog.find_elements_by_accessible_id.assert_called_once_with("search_input")

    def test_find_element_accessible_id_falls_back_to_name(self):
        from src.at.executor.handlers import find_element

        fake_element = unittest.mock.MagicMock()
        fake_dog = unittest.mock.MagicMock()
        fake_dog.find_elements_by_accessible_id.return_value = []
        fake_dog.find_element_by_attr.return_value = fake_element
        result = find_element(fake_dog, {"accessible_id": "missing", "name": "fallback_name"})
        assert result is fake_element
        fake_dog.find_element_by_attr.assert_called_once()

    def test_find_element_hierarchy_with_parent(self):
        from src.at.executor import handlers

        fake_element = unittest.mock.MagicMock()
        with unittest.mock.patch.object(
            handlers, "_find_by_hierarchy", return_value=fake_element
        ) as mock_hier:
            result = handlers.find_element(
                unittest.mock.MagicMock(),
                {"parent": "panel", "name": "find"},
            )
        assert result is fake_element
        mock_hier.assert_called_once()

    def test_find_element_hierarchy_not_found_raises(self):
        from src.at.executor.handlers import find_element

        fake_dog = unittest.mock.MagicMock()
        fake_dog.find_elements_by_attr.return_value = []
        with pytest.raises(BaseException, match="hierarchy"):
            find_element(fake_dog, {"parent": "missing", "name": "child"})

    def test_resolve_coordinates_accessible_id(self):
        from src.at.executor.handlers import resolve_coordinates

        fake_node = unittest.mock.MagicMock()
        fake_node.extents = (100, 200, 50, 60)
        fake_dog = unittest.mock.MagicMock()
        fake_dog.find_elements_by_accessible_id.return_value = [fake_node]
        with (
            unittest.mock.patch("src.at.executor.handlers.get_dog", return_value=fake_dog),
            unittest.mock.patch("src.at.executor.handlers.ensure_window_focus"),
        ):
            x, y = resolve_coordinates({"accessible_id": "btn_ok"}, {"app": "test-app"})
        assert x == 125
        assert y == 230

    def test_element_action_unknown_do_raises(self):
        from src.at.executor.handlers import handle_element_action
        from src.at.parser.models import SuiteActionStep

        fake_element = unittest.mock.MagicMock()
        fake_dog = unittest.mock.MagicMock()
        fake_dog.find_elements_by_accessible_id.return_value = [fake_element]
        step = SuiteActionStep(
            action="element_action",
            selector={"accessible_id": "btn_ok"},
            do="hover",
        )
        with (
            unittest.mock.patch("src.at.executor.handlers.get_dog", return_value=fake_dog),
        ):
            with pytest.raises(ValueError, match="Unknown element action"):
                handle_element_action(step, {"app": "test-app"})

    def test_element_action_click_uses_atspi_action_first(self):
        from src.at.executor.handlers import handle_element_action
        from src.at.parser.models import SuiteActionStep

        fake_element = unittest.mock.MagicMock()
        fake_dog = unittest.mock.MagicMock()
        fake_dog.find_element_by_attr.return_value = fake_element
        step = SuiteActionStep(
            action="element_action",
            selector={"name": "SomeBtn", "role": "push button"},
            do="click",
        )
        with unittest.mock.patch("src.at.executor.handlers.get_dog", return_value=fake_dog):
            handle_element_action(step, {"app": "test-app"})
        # 方案 A: AT-SPI action 优先触发，不依赖坐标（规避 DTK 对话框假通过）
        fake_element.doActionNamed.assert_called()
        fake_element.click.assert_not_called()

    def test_element_action_click_falls_back_to_coordinates(self):
        from src.at.executor.handlers import handle_element_action
        from src.at.parser.models import SuiteActionStep

        fake_element = unittest.mock.MagicMock()
        fake_element.doActionNamed.side_effect = RuntimeError("no action")
        fake_element.extents = (10, 10, 50, 30)
        fake_dog = unittest.mock.MagicMock()
        fake_dog.find_element_by_attr.return_value = fake_element
        step = SuiteActionStep(
            action="element_action",
            selector={"name": "SomeBtn", "role": "push button"},
            do="click",
        )
        with unittest.mock.patch("src.at.executor.handlers.get_dog", return_value=fake_dog):
            handle_element_action(step, {"app": "test-app"})
        # AT-SPI action 不可用 → 回退坐标点击（带坐标守卫）
        fake_element.click.assert_called_once()

    def test_smart_wait_timeout_logs_warning(self, caplog):
        import logging

        from src.at.executor import executor as exec_mod
        from src.at.parser.models import SuiteActionStep

        step1 = SuiteActionStep(action="keyboard_press", key="Return", wait=1)
        step2 = SuiteActionStep(action="mouse_click", selector={"name": "nonexistent"})
        fake_handler = unittest.mock.MagicMock()
        fake_dog = unittest.mock.MagicMock()
        fake_dog.find_elements_by_attr.return_value = []
        with (
            unittest.mock.patch.dict(
                exec_mod.HANDLERS,
                {"keyboard_press": fake_handler, "mouse_click": unittest.mock.MagicMock()},
            ),
            unittest.mock.patch("src.at.executor.executor.get_dog", return_value=fake_dog),
            unittest.mock.patch("src.at.executor.executor.time.sleep"),
        ):
            with caplog.at_level(logging.WARNING):
                exec_mod.execute_steps(
                    [step1, step2],
                    {"app": "test-app"},
                )
        assert any("smart_wait timed out" in r.message for r in caplog.records)

class TestMainMenuButtonAlias:
    """dtk_main_menu should honor selector.name as a custom main-menu button
    alias (apps may override AccessibleName of the DTK titlebar option button)."""

    def test_dtk_main_menu_passes_selector_name_as_button_alias(self):
        from src.at.executor.handlers import handle_dtk_main_menu
        from src.at.parser.models import SuiteActionStep

        with unittest.mock.patch("src.at.executor.menu_nav.AtMenuNavigator") as nav_cls:
            step = SuiteActionStep(
                action="dtk_main_menu",
                selector={"name": "OptionMenu", "role": "menu"},
                items=["设置"],
            )
            handle_dtk_main_menu(step, {"app": "test-app"})
        nav_cls.assert_called_once_with("test-app", button_name="OptionMenu")
        inst = nav_cls.return_value
        inst.open_main_menu.assert_called_once()
        inst.select.assert_called_once_with(["设置"])

    def test_open_main_menu_tries_custom_name_then_default(self, monkeypatch):
        from src.at.executor.menu_nav import AtMenuNavigator

        mk_inst = unittest.mock.MagicMock()
        dog_inst = unittest.mock.MagicMock()
        dog_inst.find_elements_by_attr.return_value = []
        fake_mk_mod = unittest.mock.MagicMock()
        fake_mk_mod.MouseKey = unittest.mock.MagicMock(return_value=mk_inst)
        fake_dog_mod = unittest.mock.MagicMock()
        fake_dog_mod.DogtailUtils = unittest.mock.MagicMock(return_value=dog_inst)
        monkeypatch.setitem(sys.modules, "src.mouse_key", fake_mk_mod)
        monkeypatch.setitem(sys.modules, "src.dogtail_utils", fake_dog_mod)

        nav = AtMenuNavigator("test-app", button_name="OptionMenu")
        nav.open_main_menu()
        calls = [c.args[0] for c in dog_inst.find_elements_by_attr.call_args_list]
        assert calls == ["$//OptionMenu/", "$//DTitlebarDWindowOptionButton/"]

    def test_open_main_menu_stops_at_custom_name_when_found(self, monkeypatch):
        from src.at.executor.menu_nav import AtMenuNavigator

        mk_inst = unittest.mock.MagicMock()
        btn = unittest.mock.MagicMock()
        btn.actions = {"Press": object()}
        dog_inst = unittest.mock.MagicMock()
        dog_inst.find_elements_by_attr.return_value = [btn]
        fake_mk_mod = unittest.mock.MagicMock()
        fake_mk_mod.MouseKey = unittest.mock.MagicMock(return_value=mk_inst)
        fake_dog_mod = unittest.mock.MagicMock()
        fake_dog_mod.DogtailUtils = unittest.mock.MagicMock(return_value=dog_inst)
        monkeypatch.setitem(sys.modules, "src.mouse_key", fake_mk_mod)
        monkeypatch.setitem(sys.modules, "src.dogtail_utils", fake_dog_mod)

        nav = AtMenuNavigator("test-app", button_name="OptionMenu")
        nav.open_main_menu()
        calls = [c.args[0] for c in dog_inst.find_elements_by_attr.call_args_list]
        assert calls == ["$//OptionMenu/"]
        btn.doActionNamed.assert_called_once_with("Press")

    def test_open_main_menu_default_only_without_alias(self, monkeypatch):
        from src.at.executor.menu_nav import AtMenuNavigator

        mk_inst = unittest.mock.MagicMock()
        dog_inst = unittest.mock.MagicMock()
        dog_inst.find_elements_by_attr.return_value = []
        fake_mk_mod = unittest.mock.MagicMock()
        fake_mk_mod.MouseKey = unittest.mock.MagicMock(return_value=mk_inst)
        fake_dog_mod = unittest.mock.MagicMock()
        fake_dog_mod.DogtailUtils = unittest.mock.MagicMock(return_value=dog_inst)
        monkeypatch.setitem(sys.modules, "src.mouse_key", fake_mk_mod)
        monkeypatch.setitem(sys.modules, "src.dogtail_utils", fake_dog_mod)

        nav = AtMenuNavigator("test-app")
        nav.open_main_menu()
        calls = [c.args[0] for c in dog_inst.find_elements_by_attr.call_args_list]
        assert calls == ["$//DTitlebarDWindowOptionButton/"]
