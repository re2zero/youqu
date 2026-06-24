# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only
"""Rich TUI reporter for Web spec execution."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from web_spec.result import RunRecord, RunStatus, StepStatus, SuiteRecord


@dataclass(frozen=True)
class RunnerEvent:
    """Runner event for TUI consumption."""

    kind: str
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


RunnerEventHandler = Callable[[RunnerEvent], None]


def get_console() -> Console:
    return Console()


def print_spec_result(record: RunRecord) -> None:
    console = get_console()
    style = _status_style(record.status)
    label = record.status.value

    console.print()
    parts = [
        (f" {label} ", style),
        (f" {record.spec_id}: {record.spec_title}", "white"),
        (f" | {_fmt_duration(record.duration_seconds)}\n", "dim"),
    ]
    if record.error:
        parts.append((f" {record.error}\n", "dim"))

    console.print(Panel(Text.assemble(*parts), border_style=style.split()[-1]))


def print_suite_summary(suite: SuiteRecord) -> None:
    console = get_console()

    table = Table(title="执行结果", show_lines=True)
    table.add_column("ID", style="cyan")
    table.add_column("Title")
    table.add_column("Status", justify="center")
    table.add_column("Steps", justify="center")
    table.add_column("Duration", justify="right")

    for r in suite.specs:
        status_style = _status_style(r.status)
        passed_steps = sum(1 for s in r.steps if s.status == StepStatus.PASSED)
        total_steps = len(r.steps)
        table.add_row(
            r.spec_id,
            r.spec_title,
            f"[{status_style}]{r.status.value}[/{status_style}]",
            f"{passed_steps}/{total_steps}",
            _fmt_duration(r.duration_seconds),
        )

    console.print()
    console.print(table)

    summary = Text.assemble(
        (f" Total: {suite.total} ", "bold white"),
        (f" Passed: {suite.passed} ", "bold green"),
        (f" Failed: {suite.failed} ", "bold red"),
        (f" Blocked: {suite.blocked} ", "bold yellow"),
        (f" Cancelled: {suite.cancelled} ", "bold magenta"),
        (f" Duration: {_fmt_duration(suite.duration_seconds)} ", "dim"),
    )
    console.print(Panel(summary, border_style="blue"))
    console.print()


class SpecProgressReporter:
    """Real-time progress reporter for Web spec execution."""

    def __init__(self, verbose: bool = False, console: Console | None = None) -> None:
        self.verbose = verbose
        self._console = console or get_console()
        self._case_started = False

    def __call__(self, event: RunnerEvent) -> None:
        handler = getattr(self, f"_on_{event.kind}", None)
        if handler:
            handler(event.payload)

    def _on_suite_start(self, payload: dict[str, Any]) -> None:
        label = _run_scope_label(payload.get("scope"), start=True)
        title = _suite_title(payload)
        if title:
            title = f" {title}"
        self._print(
            f"{label}{title} total={payload.get('total_specs', 0)} report_dir={payload.get('report_dir', '')}"
        )

    def _on_suite_end(self, payload: dict[str, Any]) -> None:
        label = _run_scope_label(payload.get("scope"), start=False)
        self._print(
            f"{label} "
            f"total={payload.get('total', 0)} "
            f"passed={payload.get('passed', 0)} "
            f"failed={payload.get('failed', 0)} "
            f"blocked={payload.get('blocked', 0)} "
            f"cancelled={payload.get('cancelled', 0)} "
            f"duration={_fmt_duration(payload.get('duration_seconds', 0))} "
            f"report_dir={payload.get('report_dir', '')}"
        )

    def _on_spec_start(self, payload: dict[str, Any]) -> None:
        if self._case_started:
            self._print("")
        self._case_started = True
        self._print(
            f"▶ CASE [{payload.get('index', 1)}/{payload.get('total', 1)}] "
            f"{payload.get('spec_id', '')} | {payload.get('title', '')} "
            f"| steps={payload.get('total_steps', 0)}"
        )

    def _on_spec_end(self, payload: dict[str, Any]) -> None:
        error = _error_suffix(payload.get("error"))
        status = payload.get("status", "")
        self._print(
            f"{_status_prefix(status)} CASE {payload.get('spec_id', '')} {status} "
            f"duration={_fmt_duration(payload.get('duration_seconds', 0))}{error}"
        )

    def _on_step_start(self, payload: dict[str, Any]) -> None:
        self._print(
            f"  → STEP [{payload.get('step_index', 1)}/{payload.get('total_steps', 1)}] "
            f"{payload.get('order', '')} | {payload.get('description', '')}"
        )

    def _on_step_end(self, payload: dict[str, Any]) -> None:
        error = _error_suffix(payload.get("error"))
        self._print(
            f"  ← STEP [{payload.get('step_index', 1)}/{payload.get('total_steps', 1)}] "
            f"{payload.get('status', '')} duration={_fmt_ms(payload.get('duration_ms', 0))}{error}"
        )

    def _on_action_start(self, payload: dict[str, Any]) -> None:
        if not self.verbose:
            return
        self._print(
            f"    ACTION {payload.get('action_type', '')} start "
            f"locator={_format_locator(payload.get('locator'))}"
        )

    def _on_action_end(self, payload: dict[str, Any]) -> None:
        if not self.verbose:
            return
        status = "OK" if payload.get("success") else "FAIL"
        error = _error_suffix(payload.get("error"))
        self._print(
            f"    ACTION {payload.get('action_type', '')} {status} "
            f"duration={_fmt_ms(payload.get('duration_ms', 0))} "
            f"locator={_format_locator(payload.get('locator'), include_match=True)}{error}"
        )

    def _on_assertion_start(self, payload: dict[str, Any]) -> None:
        if not self.verbose:
            return
        self._print(
            f"    ASSERT {payload.get('assertion_type', '')} start "
            f"locator={_format_locator(payload.get('locator'))} "
            f"expected={_short(payload.get('expected'))}"
        )

    def _on_assertion_end(self, payload: dict[str, Any]) -> None:
        if not self.verbose:
            return
        status = "PASS" if payload.get("success") else "FAIL"
        error = _error_suffix(payload.get("error"))
        self._print(
            f"    ASSERT {payload.get('assertion_type', '')} {status} "
            f"duration={_fmt_ms(payload.get('duration_ms', 0))} "
            f"locator={_format_locator(payload.get('locator'), include_match=True)} "
            f"expected={_short(payload.get('expected'))} "
            f"actual={_short(payload.get('actual'))} "
            f"retry_count={payload.get('retry_count', 0)}{error}"
        )

    def _on_screenshot_saved(self, payload: dict[str, Any]) -> None:
        if self.verbose:
            self._print(f"    SCREENSHOT step={payload.get('step_order', '')} path={payload.get('path', '')}")

    def _print(self, line: str) -> None:
        self._console.print(line, markup=False)


def _run_scope_label(scope: Any, start: bool) -> str:
    if scope == "cases":
        return "RUN-CASES" if start else "END-CASES"
    return "RUN-SUITE" if start else "END-SUITE"


def _suite_title(payload: dict[str, Any]) -> str:
    suite_id = str(payload.get("suite_id") or "").strip()
    title = str(payload.get("title") or "").strip()
    return f"{suite_id} {title}".strip()


def _status_prefix(status: Any) -> str:
    return "✓" if status == "passed" else "✗"


def _format_locator(locator: dict[str, Any] | None, include_match: bool = False) -> str:
    if not locator:
        return "-"
    text = f"{locator.get('strategy', '')}:{locator.get('value', '')}"
    stability = locator.get("stability")
    if stability:
        text += f" stability={stability}"
    if include_match and locator.get("match_count") is not None:
        text += f" matches={locator.get('match_count')}"
    return text


def _error_suffix(error: Any) -> str:
    if not error:
        return ""
    return f" error={_short(error)}"


def _short(value: Any, limit: int = 120) -> str:
    if value is None:
        return "-"
    text = str(value).replace("\n", " ").strip()
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def _status_style(status: RunStatus) -> str:
    return {
        RunStatus.PASSED: "bold green",
        RunStatus.FAILED_PRODUCT: "bold red",
        RunStatus.FAILED_SCRIPT: "bold red",
        RunStatus.BLOCKED_ENV: "bold yellow",
        RunStatus.CANCELLED: "bold magenta",
    }.get(status, "white")


def _fmt_duration(seconds: float) -> str:
    try:
        value = float(seconds or 0)
    except (TypeError, ValueError):
        value = 0.0
    if value < 1:
        return f"{value:.2f}s"
    if value < 60:
        return f"{value:.1f}s"
    minutes, sec = divmod(int(value), 60)
    return f"{minutes}m{sec}s"


def _fmt_ms(ms: Any) -> str:
    try:
        value = int(ms or 0)
    except (TypeError, ValueError):
        value = 0
    if value < 1000:
        return f"{value}ms"
    return f"{value / 1000:.1f}s"
