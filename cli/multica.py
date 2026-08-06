# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only
"""Multica integration: progress reporting, heartbeat, and app version detection.

Restored and adapted from the old cli/multica_report.py which was cleaned up
in commit c73b5c6 but the underlying need (prevent multica 30-min timeout)
remains.  New features:
  - Time-based heartbeat (every N seconds) in addition to batch-based reports
  - App version detection via dpkg + apt policy (avoids hanging on --version)
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from typing import Any, Callable

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# App version detection (Fix #3)
# ---------------------------------------------------------------------------


def _find_package_for_binary(binary: str) -> str | None:
    """Find the Debian package name that owns *binary*.

    If *binary* is a bare name (e.g. ``deepin-reader``) it is looked up as
    ``/usr/bin/<binary>``; absolute paths are used as-is.
    """
    if "/" in binary:
        path = binary
    else:
        path = f"/usr/bin/{binary}"
    try:
        result = subprocess.run(
            ["dpkg", "-S", path],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            # Format: "package-name: /path/to/binary"
            return result.stdout.strip().split(":")[0]
    except (subprocess.TimeoutExpired, OSError):
        pass
    return None


def _query_apt_policy(package: str) -> str | None:
    """Query the installed version of *package* via ``apt policy``."""
    try:
        result = subprocess.run(
            ["apt", "policy", package],
            capture_output=True,
            text=True,
            timeout=5,
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            # locale-aware: "已安装：1.2.3-1" / "Installed: 1.2.3-1"
            if ":" in line and any(
                key in line.lower()
                for key in ("已安装", "installed")
            ):
                version = line.split(":", 1)[-1].strip()
                if version and version not in ("", "(none)"):
                    return version
    except (subprocess.TimeoutExpired, OSError):
        pass
    return None


def get_app_version(app_command: str) -> str:
    """Return the installed version of the application.

    Uses ``dpkg -S`` to find the owning package, then ``apt policy`` to
    read the installed version.  This avoids calling ``<app> --version``
    which may block or hang when the app does not support the flag.

    Returns the version string, or ``"unknown"`` on failure.
    """
    if not app_command:
        return "unknown"
    binary = app_command.split()[0]
    # If the binary path is absolute, take its basename for package lookup
    bin_name = os.path.basename(binary) if "/" in binary else binary

    # Try dpkg -S to find the owning package
    pkg = _find_package_for_binary(binary)
    if pkg:
        ver = _query_apt_policy(pkg)
        if ver:
            return ver

    # Fallback: use binary name directly as package name
    ver = _query_apt_policy(bin_name)
    if ver:
        return ver

    return "unknown"


# ---------------------------------------------------------------------------
# Multica CLI helpers
# ---------------------------------------------------------------------------


def check_multica_cli() -> bool:
    """Return True if ``multica`` CLI is installed and configured."""
    if not shutil.which("multica"):
        print(
            "  [multica] Warning: multica CLI not found. "
            "Progress comments disabled.",
            flush=True,
        )
        return False
    config = os.path.expanduser("~/.multica/config.json")
    if not os.path.exists(config):
        print(
            "  [multica] Warning: multica auth config not found. "
            "Progress comments disabled.",
            flush=True,
        )
        return False
    return True


def post_multica_comment(issue_id: str, content: str) -> None:
    """Post a comment to a multica issue.

    Failures are logged but do not raise.
    """
    try:
        subprocess.run(
            ["multica", "issue", "comment", "add", issue_id, "--content", content],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError) as exc:
        print(
            f"  [multica] Warning: failed to post comment: {exc}",
            file=sys.stderr,
            flush=True,
        )


# ---------------------------------------------------------------------------
# Comment formatting
# ---------------------------------------------------------------------------


def _format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)}s"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    minutes_str = f"{minutes}m" if minutes else ""
    secs_str = f" {secs}s" if secs else ""
    return f"{minutes_str}{secs_str}"


def _format_start_comment(
    app: str,
    app_version: str,
    total_suites: int,
) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "🚀 **YouQu AT Test Started**",
        f"- App: `{app}`",
        f"- App Version: `{app_version}`",
        f"- Total Suites: {total_suites}",
        f"- Started: {now}",
    ]
    return "\n".join(lines)


def _format_progress_comment(
    suites_done: int,
    total_suites: int,
    passed: int,
    failed: int,
    skipped: int,
    elapsed: float,
) -> str:
    total = passed + failed + skipped
    rate = f"{passed / total * 100:.1f}%" if total > 0 else "N/A"
    lines = [
        f"📊 **Progress: {suites_done}/{total_suites} suites**",
        f"- Specs: {total} | Passed: {passed} | Failed: {failed} | Skipped: {skipped}",
        f"- Pass Rate: {rate}",
        f"- Elapsed: {_format_duration(elapsed)}",
    ]
    return "\n".join(lines)


def _format_finish_comment(
    total_suites: int,
    passed: int,
    failed: int,
    skipped: int,
    duration: float,
    summary: str,
) -> str:
    effective = passed + failed + skipped
    rate = f"{passed / effective * 100:.1f}%" if effective > 0 else "N/A"
    partial = " (partial)" if failed > 0 else ""
    icon = "✅" if failed == 0 else "⚠️"
    lines = [
        f"{icon} **YouQu AT Test Complete{partial}**",
        f"- Suites: {total_suites}",
        f"- Specs: {effective} | Passed: {passed} | Failed: {failed} | Skipped: {skipped}",
        f"- Pass Rate: {rate}",
        f"- Duration: {_format_duration(duration)}",
        f"- Summary: {summary}",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Progress reporter class
# ---------------------------------------------------------------------------


class MulticaReporter:
    """Post progress comments to a multica issue during ``youqu at run``.

    Reports are sent:
    1. After each suite (batch) completes.
    2. When the heartbeat interval expires (default 5 min) — even if a
       single suite runs longer than that.

    This prevents the multica 30-minute job timeout from reporting failure
    for tests that legitimately take longer.
    """

    def __init__(
        self,
        issue_id: str,
        app_name: str = "",
        app_command: str = "",
        report_interval: int = 300,
    ):
        self.issue_id = issue_id
        self.app_name = app_name
        self.app_command = app_command
        self.report_interval = report_interval

        self.total_suites = 0
        self.suites_done = 0
        self.total_passed = 0
        self.total_failed = 0
        self.total_skipped = 0
        self._start_time: float = 0.0
        self._last_report: float = 0.0
        self._lock = threading.Lock()
        self._heartbeat_thread: threading.Thread | None = None
        self._stop_heartbeat = threading.Event()
        self._multica_available = check_multica_cli()
        self._app_version = "unknown"

    def start(self, total_suites: int) -> None:
        """Begin tracking and post the start comment."""
        self.total_suites = total_suites
        self._start_time = time.time()
        self._last_report = self._start_time

        app_cmd = self.app_command or self.app_name
        self._app_version = get_app_version(app_cmd)

        if self._multica_available:
            comment = _format_start_comment(
                app=self.app_name or app_cmd,
                app_version=self._app_version,
                total_suites=total_suites,
            )
            post_multica_comment(self.issue_id, comment)

        # Start heartbeat thread for time-based progress reports
        if self.report_interval > 0 and total_suites > 0:
            self._start_heartbeat()

    def _start_heartbeat(self) -> None:
        self._stop_heartbeat.clear()
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            daemon=True,
            name="multica-heartbeat",
        )
        self._heartbeat_thread.start()

    def _heartbeat_loop(self) -> None:
        while not self._stop_heartbeat.wait(self.report_interval):
            with self._lock:
                if self.suites_done >= self.total_suites:
                    return
                now = time.time()
                # Only post if meaningful time passed since last report
                if now - self._last_report >= self.report_interval * 0.8:
                    elapsed = now - self._start_time
                    comment = _format_progress_comment(
                        suites_done=self.suites_done,
                        total_suites=self.total_suites,
                        passed=self.total_passed,
                        failed=self.total_failed,
                        skipped=self.total_skipped,
                        elapsed=elapsed,
                    )
                    post_multica_comment(self.issue_id, comment)
                    self._last_report = now

    def on_suite_complete(self, suite_result: dict) -> None:
        """Call after each suite completes.

        *suite_result* must contain at least ``passed``, ``failed``,
        ``skipped`` keys and an optional ``suite`` key.
        """
        with self._lock:
            self.suites_done += 1
            self.total_passed += suite_result.get("passed", 0)
            self.total_failed += suite_result.get("failed", 0)
            self.total_skipped += suite_result.get("skipped", 0)

            if self.total_failed > 0:
                _log.warning(
                    "multica suite_done %d/%d: %s  (failed=%d)",
                    self.suites_done,
                    self.total_suites,
                    suite_result.get("suite", ""),
                    suite_result.get("failed", 0),
                )

        if not self._multica_available:
            return

        now = time.time()
        elapsed = now - self._start_time
        with self._lock:
            comment = _format_progress_comment(
                suites_done=self.suites_done,
                total_suites=self.total_suites,
                passed=self.total_passed,
                failed=self.total_failed,
                skipped=self.total_skipped,
                elapsed=elapsed,
            )
            post_multica_comment(self.issue_id, comment)
            self._last_report = now

    def finish(self, summary: str = "") -> None:
        """Stop heartbeat and post the final summary comment."""
        if self._heartbeat_thread is not None:
            self._stop_heartbeat.set()
            self._heartbeat_thread.join(timeout=3)

        if not self._multica_available:
            return

        duration = time.time() - self._start_time
        comment = _format_finish_comment(
            total_suites=self.total_suites,
            passed=self.total_passed,
            failed=self.total_failed,
            skipped=self.total_skipped,
            duration=duration,
            summary=summary,
        )
        post_multica_comment(self.issue_id, comment)