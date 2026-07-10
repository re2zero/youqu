from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

from src.yaml_test.parser import ActionStep
from src.yaml_test.suite.models import (
    EnvCheckItem,
    SpecResult,
    SuiteResult,
    SuiteSpec,
    SuiteSpecItem,
)


def _check_env_process(item: EnvCheckItem) -> bool:
    result = subprocess.run(
        ["pgrep", "-x", item.name],
        capture_output=True, timeout=5,
    )
    if item.expect == "not_running":
        return result.returncode != 0
    if item.expect == "running":
        return result.returncode == 0
    return True


def _check_env_file_exists(item: EnvCheckItem) -> bool:
    exists = Path(item.name).expanduser().exists()
    if item.expect in ("exists", "true"):
        return exists
    if item.expect in ("not_exists", "false"):
        return not exists
    return True


_ENV_CHECKERS = {
    "process": _check_env_process,
    "file_exists": _check_env_file_exists,
}


def _check_env(item: EnvCheckItem) -> bool:
    checker = _ENV_CHECKERS.get(item.type)
    if checker is None:
        return True
    try:
        return checker(item)
    except (subprocess.TimeoutExpired, OSError):
        return False


def _action_step_from_dict(d: dict[str, Any]) -> ActionStep:
    return ActionStep.model_validate(d)


def _import_action_handlers():
    from src.yaml_test.executor import ACTION_HANDLERS
    return ACTION_HANDLERS


def _import_step_executor():
    from src.yaml_test.executor import StepExecutor
    return StepExecutor


def _execute_lifecycle_steps(
    steps: list[dict[str, Any]],
    context: dict[str, Any],
    handlers: dict,
) -> str | None:
    for step_dict in steps:
        step = _action_step_from_dict(step_dict)
        handler = handlers.get(step.action)
        if handler is None:
            return f"unknown action '{step.action}'"
        try:
            handler(step, context)
        except BaseException as exc:
            return f"action '{step.action}' failed: {exc}"
        if step.wait:
            time.sleep(step.wait)
    return None


def _execute_spec_steps(
    spec: SuiteSpecItem,
    context: dict[str, Any],
    handlers: dict,
) -> str | None:
    for step_dict in spec.steps:
        step = _action_step_from_dict(step_dict)
        handler = handlers.get(step.action)
        if handler is None:
            return f"unknown action '{step.action}'"
        try:
            handler(step, context)
        except BaseException as exc:
            return f"action '{step.action}' failed: {exc}"
        if step.wait:
            time.sleep(step.wait)
        if step.wait_after:
            time.sleep(step.wait_after / 1000.0)
    return None


class SuiteExecutor:
    """Execute a SuiteSpec: env_check → setup → specs → teardown.

    Each spec runs in isolation — failure in one spec does not
    affect subsequent specs (unless fast_fail is enabled).
    """

    def __init__(self, suite: SuiteSpec, suite_path: str | None = None):
        self.suite = suite
        self.context: dict[str, Any] = {
            "app": suite.app,
        }
        if suite_path:
            from src.yaml_test.elements import load_elements
            try:
                self.context["elements"] = load_elements(Path(suite_path))
            except Exception:
                pass

    def run(
        self,
        spec_ids: str | None = None,
        tags: str | None = None,
        skip_env_check: bool = False,
    ) -> SuiteResult:
        start = time.monotonic()
        specs = self._filter_specs(spec_ids, tags)
        result = SuiteResult(
            suite_name=self.suite.name,
            total=len(specs),
        )

        # env_check
        env_skip_ids: set[str] = set()
        if not skip_env_check and self.suite.env_check:
            for item in self.suite.env_check:
                if isinstance(item, dict):
                    item = EnvCheckItem(**item)
                ok = _check_env(item)
                if not ok:
                    if item.spec_ids:
                        env_skip_ids.update(item.spec_ids)
                    else:
                        for s in specs:
                            env_skip_ids.add(s.id)

        # setup
        if self.suite.setup:
            handlers = _import_action_handlers()
            err = _execute_lifecycle_steps(
                self.suite.setup, self.context, handlers,
            )
            if err:
                result.error = f"suite setup failed: {err}"
                for s in specs:
                    result.specs.append(SpecResult(
                        id=s.id, name=s.name,
                        status="skipped", error=result.error,
                    ))
                    result.skipped += 1
                result.duration = time.monotonic() - start
                return result

        # specs
        handlers = _import_action_handlers()
        for spec in specs:
            spec_result = self._run_one_spec(spec, handlers, env_skip_ids)
            result.specs.append(spec_result)
            if spec_result.status == "passed":
                result.passed += 1
            elif spec_result.status == "failed":
                result.failed += 1
                if self.suite.fast_fail:
                    remaining = [s for s in specs if s.id != spec.id]
                    for s in remaining:
                        result.specs.append(SpecResult(
                            id=s.id, name=s.name,
                            status="skipped",
                            error="cancelled by fast_fail",
                        ))
                        result.skipped += 1
                    break
            elif spec_result.status == "skipped":
                result.skipped += 1
            elif spec_result.status == "timeout":
                result.timeout += 1

        # teardown (run regardless of failures)
        if self.suite.teardown:
            try:
                _execute_lifecycle_steps(
                    self.suite.teardown, self.context, handlers,
                )
            except Exception:
                pass

        result.duration = time.monotonic() - start
        return result

    def _filter_specs(
        self, spec_ids: str | None, tags: str | None,
    ) -> list[SuiteSpecItem]:
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
        spec: SuiteSpecItem,
        handlers: dict,
        env_skip_ids: set[str],
    ) -> SpecResult:
        spec_start = time.monotonic()
        spec_result = SpecResult(id=spec.id, name=spec.name)

        # skip checks
        if spec.id in env_skip_ids:
            spec_result.status = "skipped"
            spec_result.error = "env_check failed"
            spec_result.duration = time.monotonic() - spec_start
            return spec_result
        if spec.skip:
            spec_result.status = "skipped"
            spec_result.error = spec.skip
            spec_result.duration = time.monotonic() - spec_start
            return spec_result

        # execute steps
        err = _execute_spec_steps(spec, self.context, handlers)
        if err:
            spec_result.status = "failed"
            spec_result.error = err
        else:
            spec_result.status = "passed"
        spec_result.duration = time.monotonic() - spec_start
        return spec_result
