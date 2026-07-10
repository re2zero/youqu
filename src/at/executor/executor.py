from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path
from typing import Any

from src.at.executor.crash_monitor import CrashMonitor
from src.at.executor.handlers import HANDLERS
from src.at.executor.models import AtSpecResult, AtSpecResult as SpecResult, AtSuiteResult, SpecStatus
from src.at.parser.models import EnvCheckItem, SuiteActionStep, SuiteCase, SuiteConfig

_log = logging.getLogger(__name__)


def check_env_process(item: EnvCheckItem) -> bool:
    result = subprocess.run(
        ["pgrep", "-x", item.name],
        capture_output=True, timeout=5,
    )
    if item.expect == "not_running":
        return result.returncode != 0
    if item.expect == "running":
        return result.returncode == 0
    return True


def check_env_file_exists(item: EnvCheckItem) -> bool:
    exists = Path(item.name).expanduser().exists()
    if item.expect in ("exists", "true"):
        return exists
    if item.expect in ("not_exists", "false"):
        return not exists
    return True


_ENV_CHECKERS = {
    "process": check_env_process,
    "file_exists": check_env_file_exists,
}


def check_env(item: EnvCheckItem) -> bool:
    checker = _ENV_CHECKERS.get(item.type)
    if checker is None:
        return True
    try:
        return checker(item)
    except (subprocess.TimeoutExpired, OSError):
        return False


def execute_steps(
    steps: list[SuiteActionStep],
    context: dict[str, Any],
) -> str | None:
    for step in steps:
        handler = HANDLERS.get(step.action)
        if handler is None:
            return f"unknown action '{step.action}'"
        try:
            handler(step, context)
        except Exception as exc:
            return f"action '{step.action}' failed: {exc}"
        if step.wait:
            time.sleep(step.wait)
    return None


def steps_from_dicts(step_dicts: list[dict[str, Any]]) -> list[SuiteActionStep]:
    return [SuiteActionStep.model_validate(d) for d in step_dicts]


class AtSuiteExecutor:
    def __init__(self, suite: SuiteConfig, context: dict[str, Any] | None = None):
        self.suite = suite
        self.context: dict[str, Any] = {
            "app": suite.app,
            **(context or {}),
        }

    def run(
        self,
        spec_ids: str | None = None,
        tags: str | None = None,
        skip_env_check: bool = False,
    ) -> AtSuiteResult:
        start = time.monotonic()
        specs = self._filter_specs(spec_ids, tags)
        result = AtSuiteResult(suite_name=self.suite.name, total=len(specs))

        env_skip_ids: set[str] = set()
        if not skip_env_check and self.suite.env_check:
            for item in self.suite.env_check:
                ok = check_env(item)
                if not ok:
                    if item.spec_ids:
                        env_skip_ids.update(item.spec_ids)
                    else:
                        for s in specs:
                            env_skip_ids.add(s.id)

        if self.suite.setup:
            err = execute_steps(self.suite.setup, self.context)
            if err:
                result.error = f"suite setup failed: {err}"
                for s in specs:
                    result.specs.append(SpecResult(
                        id=s.id, name=s.name,
                        status=SpecStatus.SKIPPED, error=result.error,
                    ))
                    result.skipped += 1
                result.duration = time.monotonic() - start
                return result

        crash_mon = CrashMonitor()
        app_proc = self.context.get("app_process")
        if app_proc and app_proc.poll() is None:
            crash_mon.start(self.suite.app or "", app_proc.pid)

        for spec in specs:
            spec_result = self._run_one_spec(spec, env_skip_ids, crash_mon)
            result.specs.append(spec_result)
            if spec_result.status == SpecStatus.PASSED:
                result.passed += 1
            elif spec_result.status == SpecStatus.FAILED:
                result.failed += 1
                if self.suite.fast_fail:
                    remaining = [s for s in specs if s.id != spec.id]
                    for s in remaining:
                        result.specs.append(SpecResult(
                            id=s.id, name=s.name,
                            status=SpecStatus.SKIPPED,
                            error="cancelled by fast_fail",
                        ))
                        result.skipped += 1
                    break
            elif spec_result.status == SpecStatus.SKIPPED:
                result.skipped += 1
            elif spec_result.status == SpecStatus.TIMEOUT:
                result.timeout += 1

        crash_mon.stop()

        if self.suite.teardown:
            try:
                execute_steps(self.suite.teardown, self.context)
            except Exception as exc:
                _log.warning("teardown failed: %s", exc)

        result.duration = time.monotonic() - start
        return result

    def _filter_specs(
        self, spec_ids: str | None, tags: str | None,
    ) -> list[SuiteCase]:
        candidates = list(self.suite.specs)
        if spec_ids:
            ids = {s.strip() for s in spec_ids.split(",") if s.strip()}
            candidates = [s for s in candidates if s.id in ids]
        if tags:
            tag_list = [t.strip() for t in tags.split(",") if t.strip()]
            candidates = [
                s for s in candidates
                if any(t in s.tags for t in tag_list)
            ]
        return candidates

    def _run_one_spec(
        self,
        spec: SuiteCase,
        env_skip_ids: set[str],
        crash_mon: CrashMonitor,
    ) -> AtSpecResult:
        spec_start = time.monotonic()
        spec_result = AtSpecResult(id=spec.id, name=spec.name)

        if spec.id in env_skip_ids:
            spec_result.status = SpecStatus.SKIPPED
            spec_result.error = "env_check failed"
            spec_result.duration = time.monotonic() - spec_start
            return spec_result
        if spec.skip:
            spec_result.status = SpecStatus.SKIPPED
            spec_result.skip_reason = spec.skip
            spec_result.duration = time.monotonic() - spec_start
            return spec_result

        if not crash_mon.check():
            spec_result.status = SpecStatus.FAILED
            spec_result.error = crash_mon.crash_reason
            spec_result.duration = time.monotonic() - spec_start
            return spec_result

        err = execute_steps(spec.steps, self.context)
        if err:
            spec_result.status = SpecStatus.FAILED
            spec_result.error = err
        elif not crash_mon.check():
            spec_result.status = SpecStatus.FAILED
            spec_result.error = crash_mon.crash_reason
        else:
            if spec.assert_steps:
                err = execute_steps(spec.assert_steps, self.context)
                if err:
                    spec_result.status = SpecStatus.FAILED
                    spec_result.error = err
                else:
                    spec_result.status = SpecStatus.PASSED
            else:
                spec_result.status = SpecStatus.PASSED

        spec_result.duration = time.monotonic() - spec_start
        return spec_result
