# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only
"""Unit tests for src.web_spec.runner helpers."""

from web_spec.config import WebSpecConfig
from web_spec.models import TestSpec
from web_spec.result import RunRecord, RunStatus
from web_spec.runner import WebSpecRunner


class WaitPage:
    def __init__(self):
        self.waits = []

    def wait_for_timeout(self, timeout_ms):
        self.waits.append(timeout_ms)


def test_entry_url_joins_base_url_and_route():
    runner = WebSpecRunner(WebSpecConfig(base_url="http://example.test/app", entry_route="/chat"))
    spec = TestSpec.model_validate({
        "id": "case",
        "title": "Case",
        "steps": [{
            "description": "检查",
            "assertions": [{"type": "visible", "locator": {"strategy": "text", "value": "ok"}}],
        }],
    })

    assert runner._entry_url(spec) == "http://example.test/app/chat"


def test_spec_entry_url_wins():
    runner = WebSpecRunner(WebSpecConfig(base_url="http://example.test", entry_route="/chat"))
    spec = TestSpec.model_validate({
        "id": "case",
        "title": "Case",
        "entry_url": "http://other.test/start",
        "steps": [{
            "description": "检查",
            "assertions": [{"type": "visible", "locator": {"strategy": "text", "value": "ok"}}],
        }],
    })

    assert runner._entry_url(spec) == "http://other.test/start"


def test_wait_after_navigation_uses_configured_timeout():
    runner = WebSpecRunner(WebSpecConfig(navigation_wait_after_ms=120))
    page = WaitPage()

    runner._wait_after_navigation(page)

    assert page.waits == [120]


def test_wait_after_navigation_can_be_disabled():
    runner = WebSpecRunner(WebSpecConfig(navigation_wait_after_ms=0))
    page = WaitPage()

    runner._wait_after_navigation(page)

    assert page.waits == []


def test_run_all_emits_standalone_cases_scope(tmp_path, monkeypatch):
    events = []
    runner = WebSpecRunner(WebSpecConfig(report_dir=str(tmp_path)), reporter=events.append)
    spec = TestSpec.model_validate({
        "id": "first",
        "title": "First",
        "steps": [{
            "description": "检查",
            "assertions": [{"type": "visible", "locator": {"strategy": "text", "value": "ok"}}],
        }],
    })
    monkeypatch.setattr(runner, "_start_browser", lambda: None)
    monkeypatch.setattr(runner, "_stop_browser", lambda: None)

    def fake_run_spec(spec, report_root=None, spec_index=1, total_specs=1):
        record = RunRecord(spec_id=spec.id, spec_title=spec.title, report_dir=str(tmp_path / spec.id))
        record.finalize()
        return record

    monkeypatch.setattr(runner, "run_spec", fake_run_spec)

    runner.run_all([spec], report_dir=tmp_path)

    assert events[0].kind == "suite_start"
    assert events[0].payload["scope"] == "cases"
    assert events[-1].kind == "suite_end"
    assert events[-1].payload["scope"] == "cases"


def test_run_all_blocks_only_remaining_specs_on_environment_error(tmp_path, monkeypatch):
    runner = WebSpecRunner(WebSpecConfig(report_dir=str(tmp_path)))
    specs = [
        TestSpec.model_validate({
            "id": "first",
            "title": "First",
            "steps": [{
                "description": "检查",
                "assertions": [{"type": "visible", "locator": {"strategy": "text", "value": "ok"}}],
            }],
        }),
        TestSpec.model_validate({
            "id": "second",
            "title": "Second",
            "steps": [{
                "description": "检查",
                "assertions": [{"type": "visible", "locator": {"strategy": "text", "value": "ok"}}],
            }],
        }),
    ]

    monkeypatch.setattr(runner, "_start_browser", lambda: None)
    monkeypatch.setattr(runner, "_stop_browser", lambda: None)

    def fake_run_spec(spec, report_root=None, spec_index=1, total_specs=1):
        if spec.id == "second":
            raise EnvironmentError("browser lost")
        record = RunRecord(spec_id=spec.id, spec_title=spec.title, report_dir=str(tmp_path / spec.id))
        record.finalize()
        return record

    monkeypatch.setattr(runner, "run_spec", fake_run_spec)

    suite = runner.run_all(specs, report_dir=tmp_path)

    assert [record.spec_id for record in suite.specs] == ["first", "second"]
    assert suite.specs[0].status == RunStatus.PASSED
    assert suite.specs[1].status == RunStatus.BLOCKED_ENV
