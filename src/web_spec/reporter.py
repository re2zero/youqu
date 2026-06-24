# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only
"""JSON and HTML report generation for Web spec runs."""

from __future__ import annotations

import html as html_mod
import json
from datetime import datetime
from pathlib import Path

from web_spec.result import RunRecord, RunStatus, StepStatus, SuiteRecord, to_dict


def save_spec_report(record: RunRecord) -> None:
    """Save report.json and report.html for one spec record."""
    if not record.report_dir:
        raise ValueError("record.report_dir 不能为空")
    report_dir = Path(record.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "report.json").write_text(
        json.dumps(to_dict(record), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (report_dir / "report.html").write_text(_generate_spec_html(record), encoding="utf-8")


def save_suite_summary(suite: SuiteRecord, output_dir: str | Path) -> None:
    """Save summary.json and summary.html for a suite run."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary = {
        "suite_id": suite.suite_id,
        "suite_name": suite.suite_name,
        "module": suite.module,
        "tags": suite.tags,
        "source": suite.source,
        "fast_fail": suite.fast_fail,
        "timeout": suite.timeout,
        "error": suite.error,
        "start_time": suite.start_time,
        "end_time": suite.end_time,
        "total": suite.total,
        "passed": suite.passed,
        "failed": suite.failed,
        "blocked": suite.blocked,
        "cancelled": suite.cancelled,
        "duration_seconds": suite.duration_seconds,
        "specs": [to_dict(record) for record in suite.specs],
    }
    (out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out / "summary.html").write_text(_generate_summary_html(suite), encoding="utf-8")


def print_suite_summary(suite: SuiteRecord) -> None:
    """Print a compact suite or standalone cases summary to terminal."""
    title = f"{suite.suite_id} {suite.suite_name}".strip()
    if title:
        print(f"Web spec suite result: {title}")
    else:
        print("Web spec cases result:")
    for record in suite.specs:
        print(
            f"  {record.spec_id:30s} {record.status.value:15s} "
            f"{record.duration_seconds:.2f}s {record.spec_title}"
        )
    print(
        f"Total: {suite.total}, Passed: {suite.passed}, Failed: {suite.failed}, "
        f"Blocked: {suite.blocked}, Cancelled: {suite.cancelled}, "
        f"Duration: {suite.duration_seconds:.2f}s"
    )


def _generate_spec_html(record: RunRecord) -> str:
    suite_meta = ""
    if record.suite_id:
        suite_meta = (
            "<section class='meta'>"
            f"<p>Suite: {html_mod.escape(record.suite_id)} "
            f"{html_mod.escape(record.suite_name)}</p>"
            f"<p>Module: {html_mod.escape(record.suite_module)} "
            f"Tags: {html_mod.escape(','.join(record.suite_tags))}</p>"
            f"<p>Order: {record.suite_order} "
            f"Suite source: {html_mod.escape(record.suite_source or '-')} "
            f"Spec source: {html_mod.escape(record.spec_source or '-')}</p>"
            "</section>"
        )
    step_html = []
    for step in record.steps:
        actions = "".join(
            f"<li class='{_ok_cls(a.success)}'>action {html_mod.escape(a.type)}"
            f"{_error(a.error)} ({a.duration_ms}ms)</li>"
            for a in step.actions
        )
        assertions = "".join(
            f"<li class='{_ok_cls(a.success)}'>assert {html_mod.escape(a.type)} "
            f"expect={html_mod.escape(str(a.expected))} actual={html_mod.escape(str(a.actual))}"
            f"{_error(a.error)} ({a.duration_ms}ms)</li>"
            for a in step.assertions
        )
        screenshot = ""
        if step.screenshot_path:
            screenshot = (
                f"<details><summary>Screenshot</summary>"
                f"<img src='{html_mod.escape(Path(step.screenshot_path).name)}' /></details>"
            )
        step_html.append(
            f"<section class='step {step.status.value}'>"
            f"<h2>Step {step.order}: {html_mod.escape(step.description)}</h2>"
            f"<p>Status: <b>{step.status.value}</b> Duration: {step.duration_ms}ms</p>"
            f"<ul>{actions}{assertions}</ul>{screenshot}</section>"
        )

    return _HTML_TEMPLATE.format(
        title=html_mod.escape(f"{record.spec_id} - {record.spec_title}"),
        body=(
            f"<h1>{html_mod.escape(record.spec_id)} - {html_mod.escape(record.spec_title)}</h1>"
            f"<p>Status: <b class='{record.status.value}'>{record.status.value}</b> "
            f"Duration: {record.duration_seconds:.2f}s</p>"
            f"{suite_meta}"
            f"{_error(record.error)}"
            f"{''.join(step_html)}"
        ),
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


def _generate_summary_html(suite: SuiteRecord) -> str:
    rows = []
    for index, record in enumerate(suite.specs, start=1):
        link_dir = Path(record.report_dir).name if record.report_dir else record.spec_id
        link = f"{html_mod.escape(link_dir)}/report.html"
        order = record.suite_order or index
        suite_label = _suite_label(record)
        rows.append(
            "<tr>"
            f"<td>{order}</td>"
            f"<td>{suite_label}</td>"
            f"<td><a href='{link}'>{html_mod.escape(record.spec_id)}</a></td>"
            f"<td>{html_mod.escape(record.spec_title)}</td>"
            f"<td class='{record.status.value}'>{record.status.value}</td>"
            f"<td>{record.duration_seconds:.2f}s</td>"
            f"<td>{html_mod.escape(record.spec_source or '-')}</td>"
            f"<td>{html_mod.escape(record.error or '-')}</td>"
            "</tr>"
        )
    suite_title = suite.suite_name or suite.suite_id or "Web Spec Summary"
    meta = (
        "<section class='meta'>"
        f"<p>Suite: {html_mod.escape(suite.suite_id)} "
        f"Module: {html_mod.escape(suite.module)} "
        f"Tags: {html_mod.escape(','.join(suite.tags))}</p>"
        f"<p>Source: {html_mod.escape(suite.source or '-')} "
        f"Fast fail: {suite.fast_fail} Timeout: {suite.timeout or '-'}s "
        f"Duration: {suite.duration_seconds:.2f}s</p>"
        f"{_error(suite.error)}"
        "</section>"
    )
    body = (
        f"<h1>{html_mod.escape(suite_title)}</h1>"
        f"{meta}"
        f"<p>Total: {suite.total}, Passed: {suite.passed}, Failed: {suite.failed}, "
        f"Blocked: {suite.blocked}, Cancelled: {suite.cancelled}</p>"
        "<table><thead><tr><th>Order</th><th>Suite</th><th>ID</th><th>Title</th><th>Status</th>"
        "<th>Duration</th><th>Source</th><th>Error</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )
    return _HTML_TEMPLATE.format(
        title=html_mod.escape(suite_title),
        body=body,
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


def _suite_label(record: RunRecord) -> str:
    if not record.suite_id:
        return "-"
    label = record.suite_id
    if record.suite_name:
        label = f"{label} {record.suite_name}"
    return html_mod.escape(label)


def _ok_cls(success: bool) -> str:
    return "ok" if success else "fail"


def _error(error: str | None) -> str:
    if not error:
        return ""
    return f" <span class='error'>{html_mod.escape(error)}</span>"


_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 24px; background: #0f172a; color: #e2e8f0; }}
a {{ color: #38bdf8; }}
table {{ border-collapse: collapse; width: 100%; background: #1e293b; }}
th, td {{ border: 1px solid #334155; padding: 8px 10px; text-align: left; }}
.step {{ background: #1e293b; border: 1px solid #334155; border-left: 4px solid #22c55e; border-radius: 6px; padding: 12px; margin: 12px 0; }}
.step.failed {{ border-left-color: #ef4444; }}
.step.skipped {{ border-left-color: #f59e0b; opacity: .75; }}
.ok, .passed {{ color: #22c55e; }}
.fail, .failed, .failed_product, .failed_script {{ color: #ef4444; }}
.blocked_env, .cancelled, .skipped {{ color: #f59e0b; }}
.error {{ color: #ef4444; }}
img {{ max-width: 100%; border-radius: 4px; margin-top: 8px; }}
.footer {{ color: #94a3b8; margin-top: 32px; font-size: 12px; }}
</style>
</head>
<body>
{body}
<div class="footer">Generated by YouQu Web Spec at {timestamp}</div>
</body>
</html>
"""
