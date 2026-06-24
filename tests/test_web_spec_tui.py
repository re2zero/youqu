# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only
"""Unit tests for src.web_spec.tui."""

from web_spec.tui import RunnerEvent, SpecProgressReporter


def test_progress_reporter_prints_standalone_cases_scope(capsys):
    reporter = SpecProgressReporter()

    reporter(RunnerEvent("suite_start", {"scope": "cases", "total_specs": 2, "report_dir": "report"}))
    reporter(RunnerEvent("spec_start", {"index": 1, "total": 2, "spec_id": "case_a", "title": "独立用例", "total_steps": 3}))
    reporter(RunnerEvent("step_start", {"step_index": 1, "total_steps": 3, "order": 1, "description": "打开页面"}))
    reporter(RunnerEvent("step_end", {"step_index": 1, "total_steps": 3, "status": "passed", "duration_ms": 120}))
    reporter(RunnerEvent("spec_end", {"spec_id": "case_a", "status": "passed", "duration_seconds": 1.23}))
    reporter(RunnerEvent("suite_end", {"scope": "cases", "total": 2, "passed": 1, "failed": 0, "blocked": 0, "cancelled": 1, "duration_seconds": 1.23, "report_dir": "report"}))

    captured = capsys.readouterr()
    assert "RUN-CASES total=2" in captured.out
    assert "▶ CASE [1/2] case_a | 独立用例 | steps=3" in captured.out
    assert "→ STEP [1/3] 1 | 打开页面" in captured.out
    assert "✓ CASE case_a passed duration=1.2s" in captured.out
    assert "END-CASES total=2 passed=1 failed=0 blocked=0 cancelled=1" in captured.out
    assert "RUN-SUITE" not in captured.out


def test_progress_reporter_adds_blank_line_between_cases(capsys):
    reporter = SpecProgressReporter()

    reporter(RunnerEvent("spec_start", {"index": 1, "total": 2, "spec_id": "case_a", "title": "A", "total_steps": 1}))
    reporter(RunnerEvent("spec_end", {"spec_id": "case_a", "status": "passed", "duration_seconds": 1}))
    reporter(RunnerEvent("spec_start", {"index": 2, "total": 2, "spec_id": "case_b", "title": "B", "total_steps": 1}))

    captured = capsys.readouterr()
    assert "✓ CASE case_a passed duration=1.0s\n\n▶ CASE [2/2] case_b | B | steps=1" in captured.out


def test_progress_reporter_prints_explicit_suite_title(capsys):
    reporter = SpecProgressReporter()

    reporter(RunnerEvent("suite_start", {"scope": "suite", "suite_id": "smoke", "title": "冒烟套件", "total_specs": 1, "report_dir": "report"}))
    reporter(RunnerEvent("spec_end", {"spec_id": "case_b", "status": "failed_product", "duration_seconds": 2, "error": "断言失败"}))
    reporter(RunnerEvent("suite_end", {"scope": "suite", "total": 1, "passed": 0, "failed": 1, "blocked": 0, "cancelled": 0, "duration_seconds": 2, "report_dir": "report"}))

    captured = capsys.readouterr()
    assert "RUN-SUITE smoke 冒烟套件 total=1" in captured.out
    assert "✗ CASE case_b failed_product duration=2.0s error=断言失败" in captured.out
    assert "END-SUITE total=1 passed=0 failed=1 blocked=0 cancelled=0" in captured.out
