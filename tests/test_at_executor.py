# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only

import os
import sys
import types
from pathlib import Path
import unittest.mock

import pytest

_original_src = None
_src_root = Path(__file__).resolve().parent.parent / "src"


def _fix_src():
    global _original_src
    import sys

    if str(_src_root) not in sys.path:
        sys.path.insert(0, str(_src_root))

    if "src" in sys.modules and not getattr(sys.modules["src"], "__spec__", None):
        _original_src = sys.modules["src"]
        mod = types.ModuleType("src")
        mod.__path__ = [str(_src_root)]
        mod.__package__ = "src"
        mod.__file__ = str(_src_root / "__init__.py")
        sys.modules["src"] = mod


_fix_src()


def _make_fake_suite_yaml():
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
        yaml_data = _make_fake_suite_yaml()
        mock_path = unittest.mock.MagicMock()
        mock_path.__str__ = lambda self: "/tmp/test.suite.yaml"

        from src.at.executor.runner import _load_and_run_suite

        with (
            unittest.mock.patch("src.at.executor.runner._parse_yaml", return_value=yaml_data),
            unittest.mock.patch("src.yaml_test.suite.executor.SuiteExecutor") as MockExecutor,
        ):
            mock_result = unittest.mock.MagicMock()
            mock_result.passed = 1
            mock_result.failed = 0
            mock_result.skipped = 1
            mock_result.timeout = 0
            mock_result.duration = 0.5
            mock_result.specs = [
                unittest.mock.MagicMock(id="spec-001", name="open", status="passed", error=None, duration=0.3),
                unittest.mock.MagicMock(id="spec-002", name="click", status="skipped", error="env_check failed", duration=0.1),
            ]
            instance = MockExecutor.return_value
            instance.run.return_value = mock_result

            r = _load_and_run_suite(mock_path)
            assert r["status"] == "ok"
            assert r["passed"] == 1
            assert r["skipped"] == 1


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
            unittest.mock.patch("src.at.executor.runner._find_suite_files", return_value=[mock_path]),
            unittest.mock.patch("src.at.executor.runner._load_and_run_suite", return_value=fail_result),
        ):
            rc = run_tests()
            assert rc == 1
