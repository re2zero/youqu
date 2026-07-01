# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only
"""Unit tests for cli/dev.py — suite management CLI."""

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from src.yaml_test.suite.models import SpecResult, SuiteResult


# --- helper: create a mock dev-yaml/ dir with a suite file ---
def _make_dev_yaml(tmp_path, suite_content: str = None):
    dev_dir = tmp_path / "dev-yaml"
    dev_dir.mkdir()
    if suite_content:
        sp = dev_dir / "test-suite.suite.yaml"
        sp.write_text(suite_content, encoding="utf-8")
    return dev_dir


_MINIMAL_SUITE = """\
name: "test"
specs:
  - id: s1
    name: "op1"
    steps:
      - action: wait
        wait: 0.1
"""


class TestFindDevYamlDir:
    def test_finds_dev_yaml_in_cwd(self, tmp_path):
        dev_dir = _make_dev_yaml(tmp_path)
        orig_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            from youqu.cli.dev import _find_dev_yaml_dir
            found = _find_dev_yaml_dir()
            assert found is not None
            assert found.name == "dev-yaml"
        finally:
            os.chdir(orig_cwd)


class TestCmdInit:
    def test_init_creates_dir(self, tmp_path):
        from youqu.cli.dev import cmd_init

        orig_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            args = type("Args", (), {})()
            cmd_init(args)
            assert (tmp_path / "dev-yaml").is_dir()
            assert (tmp_path / "dev-yaml" / ".gitkeep").exists()
        finally:
            os.chdir(orig_cwd)


class TestCmdMake:
    def test_make_creates_skeleton(self, tmp_path):
        from youqu.cli.dev import cmd_make

        orig_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            args = type("Args", (), {"name": "my-suite", "force": False})()
            cmd_make(args)
            suite_path = tmp_path / "dev-yaml" / "my-suite.suite.yaml"
            assert suite_path.exists()
            content = suite_path.read_text(encoding="utf-8")
            assert "name: \"my-suite\"" in content
            assert "specs:" in content
        finally:
            os.chdir(orig_cwd)

    def test_make_force_overwrite(self, tmp_path):
        from youqu.cli.dev import cmd_make

        orig_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            args = type("Args", (), {"name": "my-suite", "force": False})()
            cmd_make(args)
            args2 = type("Args", (), {"name": "my-suite", "force": True})()
            cmd_make(args2)
            suite_path = tmp_path / "dev-yaml" / "my-suite.suite.yaml"
            assert suite_path.exists()
        finally:
            os.chdir(orig_cwd)


class TestCmdList:
    def test_list_no_dir(self):
        from youqu.cli.dev import cmd_list

        with patch("youqu.cli.dev._find_dev_yaml_dir", return_value=None):
            cmd_list(type("Args", (), {"name": ""})())

    def test_list_no_suites(self, tmp_path):
        from youqu.cli.dev import cmd_list

        dev_dir = _make_dev_yaml(tmp_path)
        with patch("youqu.cli.dev._find_dev_yaml_dir", return_value=dev_dir):
            cmd_list(type("Args", (), {"name": ""})())

    def test_list_with_suites(self, tmp_path):
        from youqu.cli.dev import cmd_list

        dev_dir = _make_dev_yaml(tmp_path, _MINIMAL_SUITE)
        with patch("youqu.cli.dev._find_dev_yaml_dir", return_value=dev_dir):
            cmd_list(type("Args", (), {"name": ""})())

    def test_list_with_name(self, tmp_path):
        from youqu.cli.dev import cmd_list

        dev_dir = _make_dev_yaml(tmp_path, _MINIMAL_SUITE)
        with patch("youqu.cli.dev._find_dev_yaml_dir", return_value=dev_dir):
            cmd_list(type("Args", (), {"name": "test-suite"})())


class TestSubdirectorySuites:
    def test_list_suites_finds_subdirectory_suites(self, tmp_path):
        from youqu.cli.dev import _list_suites

        dev_dir = _make_dev_yaml(tmp_path)
        mod_dir = dev_dir / "菜单"
        mod_dir.mkdir()
        sp = mod_dir / "主菜单.suite.yaml"
        sp.write_text(_MINIMAL_SUITE, encoding="utf-8")
        sp2 = mod_dir / "右键菜单.suite.yaml"
        sp2.write_text(_MINIMAL_SUITE, encoding="utf-8")

        suites = _list_suites(dev_dir)
        stems = [s[0] for s in suites]
        assert "主菜单" in stems
        assert "右键菜单" in stems
        assert len(suites) == 2

    def test_find_suite_path_by_stem_in_subdirectory(self, tmp_path):
        from youqu.cli.dev import _find_suite_path

        dev_dir = _make_dev_yaml(tmp_path)
        mod_dir = dev_dir / "菜单"
        mod_dir.mkdir()
        sp = mod_dir / "主菜单.suite.yaml"
        sp.write_text(_MINIMAL_SUITE, encoding="utf-8")

        with patch("youqu.cli.dev._find_dev_yaml_dir", return_value=dev_dir):
            result = _find_suite_path("主菜单")
            assert result is not None
            assert result.name == "主菜单.suite.yaml"
            assert result.parent.name == "菜单"

    def test_find_suite_path_by_module_dir_name(self, tmp_path):
        from youqu.cli.dev import _find_suite_path

        dev_dir = _make_dev_yaml(tmp_path)
        mod_dir = dev_dir / "搜索"
        mod_dir.mkdir()
        sp = mod_dir / "搜索.suite.yaml"
        sp.write_text(_MINIMAL_SUITE, encoding="utf-8")

        with patch("youqu.cli.dev._find_dev_yaml_dir", return_value=dev_dir):
            result = _find_suite_path("搜索")
            assert result is not None
            assert result.name == "搜索.suite.yaml"

    def test_find_suite_path_flat_still_works(self, tmp_path):
        from youqu.cli.dev import _find_suite_path

        dev_dir = _make_dev_yaml(tmp_path, _MINIMAL_SUITE)
        with patch("youqu.cli.dev._find_dev_yaml_dir", return_value=dev_dir):
            result = _find_suite_path("test-suite")
            assert result is not None
            assert result.name == "test-suite.suite.yaml"

    def test_find_suite_path_multiple_suites_same_module(self, tmp_path):
        from youqu.cli.dev import _find_suite_path, _list_suites

        dev_dir = _make_dev_yaml(tmp_path)
        mod_dir = dev_dir / "文件操作"
        mod_dir.mkdir()
        for op_name in ("文件打开", "文件保存", "文件关闭"):
            sp = mod_dir / f"{op_name}.suite.yaml"
            sp.write_text(_MINIMAL_SUITE, encoding="utf-8")

        suites = _list_suites(dev_dir)
        assert len(suites) == 3

        with patch("youqu.cli.dev._find_dev_yaml_dir", return_value=dev_dir):
            for op_name in ("文件打开", "文件保存", "文件关闭"):
                result = _find_suite_path(op_name)
                assert result is not None
                assert result.parent.name == "文件操作"


class TestPrintResult:
    def test_print_all_passed(self, capsys):
        from youqu.cli.dev import _print_result

        r = SuiteResult(
            suite_name="test",
            passed=3,
            failed=0,
            skipped=0,
            total=3,
            specs=[
                SpecResult(id="s1", name="A", status="passed", duration=0.5),
                SpecResult(id="s2", name="B", status="passed", duration=0.3),
                SpecResult(id="s3", name="C", status="passed", duration=0.4),
            ],
            duration=1.2,
        )
        _print_result(r)
        captured = capsys.readouterr()
        assert "[passed]" in captured.out

    def test_print_with_errors(self, capsys):
        from youqu.cli.dev import _print_result

        r = SuiteResult(
            suite_name="test",
            passed=1,
            failed=1,
            skipped=1,
            total=3,
            specs=[
                SpecResult(id="s1", name="A", status="passed", duration=0.5),
                SpecResult(id="s2", name="B", status="failed",
                           error="action 'click' failed", duration=0.3),
                SpecResult(id="s3", name="C", status="skipped",
                           error="env_check failed", duration=0.0),
            ],
        )
        _print_result(r)
        captured = capsys.readouterr()
        assert "[passed]" in captured.out
        assert "[failed]" in captured.out
        assert "[skipped]" in captured.out
