# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only
"""Unit tests for src.web_spec.reporter."""

import json

from web_spec.reporter import print_suite_summary, save_spec_report, save_suite_summary
from web_spec.result import ActionRecord, RunRecord, StepRecord, SuiteRecord


def test_save_spec_report(tmp_path):
    report_dir = tmp_path / "spec"
    record = RunRecord(spec_id="login", spec_title="登录测试", report_dir=str(report_dir))
    record.steps.append(StepRecord(order=1, description="点击", actions=[ActionRecord(type="click")]))
    record.finalize()

    save_spec_report(record)

    data = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
    assert data["spec_id"] == "login"
    assert data["status"] == "passed"
    assert (report_dir / "report.html").exists()


def test_save_spec_report_includes_suite_metadata(tmp_path):
    report_dir = tmp_path / "spec"
    record = RunRecord(
        spec_id="login",
        spec_title="登录测试",
        report_dir=str(report_dir),
        suite_id="smoke",
        suite_name="冒烟套件",
        suite_module="认证",
        suite_tags=["smoke"],
        suite_source="smoke/suite.yaml",
        suite_order=2,
        spec_source="login.yaml",
    )
    record.finalize()

    save_spec_report(record)

    data = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
    assert data["suite_id"] == "smoke"
    assert data["suite_name"] == "冒烟套件"
    assert data["suite_order"] == 2
    assert data["suite_source"] == "smoke/suite.yaml"
    assert data["spec_source"] == "login.yaml"
    html = (report_dir / "report.html").read_text(encoding="utf-8")
    assert "冒烟套件" in html
    assert "login.yaml" in html


def test_print_suite_summary_distinguishes_suite_and_standalone_cases(capsys):
    suite = SuiteRecord(suite_id="smoke", suite_name="冒烟套件")
    suite.specs.append(RunRecord(spec_id="login", spec_title="登录测试"))
    suite.finalize()

    cases = SuiteRecord()
    cases.specs.append(RunRecord(spec_id="profile", spec_title="资料测试"))
    cases.finalize()

    print_suite_summary(suite)
    print_suite_summary(cases)

    captured = capsys.readouterr()
    assert "Web spec suite result: smoke 冒烟套件" in captured.out
    assert "Web spec cases result:" in captured.out
    assert "Web spec result:" not in captured.out


def test_save_suite_summary(tmp_path):
    suite = SuiteRecord(
        suite_id="smoke",
        suite_name="冒烟套件",
        module="认证",
        tags=["smoke"],
        source="smoke/suite.yaml",
        fast_fail=True,
        timeout=600,
    )
    suite.error = "suite teardown failed"
    record = RunRecord(
        spec_id="login",
        spec_title="登录测试",
        report_dir=str(tmp_path / "login"),
        suite_id="smoke",
        suite_name="冒烟套件",
        suite_order=1,
        spec_source="login.yaml",
    )
    record.finalize()
    suite.specs.append(record)
    suite.finalize()

    save_suite_summary(suite, tmp_path)

    data = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert data["suite_id"] == "smoke"
    assert data["suite_name"] == "冒烟套件"
    assert data["source"] == "smoke/suite.yaml"
    assert data["fast_fail"] is True
    assert data["timeout"] == 600
    assert data["error"] == "suite teardown failed"
    assert data["start_time"] > 0
    assert data["end_time"] > 0
    assert data["total"] == 1
    assert data["passed"] == 1
    html = (tmp_path / "summary.html").read_text(encoding="utf-8")
    assert "Fast fail: True" in html
    assert "smoke/suite.yaml" in html
    assert "suite teardown failed" in html
    assert "smoke 冒烟套件" in html
    assert "login.yaml" in html
