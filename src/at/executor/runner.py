from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Optional

import yaml

from src.at.executor.executor import AtSuiteExecutor
from src.at.executor.models import SpecStatus
from src.at.parser.models import SuiteConfig
from src.at.parser.variables import substitute_dict

_log = logging.getLogger("youqu.at.executor")


def _find_suite_files(test_dir: str, suite_name: Optional[str] = None) -> list[Path]:
    if suite_name and (suite_name.startswith("/") or suite_name.endswith(".suite.yaml")):
        p = Path(suite_name)
        if p.is_file():
            return [p]
        if p.is_dir():
            return sorted(p.rglob("*.suite.yaml"))
        return []
    base = Path(test_dir)
    if not base.is_dir():
        _log.error("test directory not found: %s", test_dir)
        return []
    if suite_name:
        return sorted(base.rglob(f"*{suite_name}*.suite.yaml"))
    return sorted(base.rglob("*.suite.yaml"))


def _load_elements(suite_dir: Path) -> dict:
    """Load elements.yaml from the suite directory or its parent directories.

    The generator writes a single elements.yaml at the output root.
    Suite files live in subdirectories, so we search upward.
    """
    elements_path = suite_dir / "elements.yaml"
    if elements_path.is_file():
        try:
            with open(elements_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if isinstance(data, dict):
                return data.get("elements", data)
        except Exception:
            pass
    for parent in suite_dir.parents:
        candidate = parent / "elements.yaml"
        if candidate.is_file():
            try:
                with open(candidate, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                if isinstance(data, dict):
                    return data.get("elements", data)
            except Exception:
                pass
    return {}


def _load_and_run_suite(
    suite_path: Path,
    spec_ids: Optional[str] = None,
    tags: Optional[str] = None,
    skip_env_check: bool = False,
) -> dict:
    data = _parse_yaml(suite_path)
    if data is None:
        return {"suite": str(suite_path), "status": "error", "error": "invalid YAML"}

    # Variable substitution for suite YAML
    variables = data.get("vars", {}) or {}
    if isinstance(variables, dict):
        variables.setdefault("YAML_DIR", str(suite_path.parent))
        project_root = Path(os.getcwd())
        variables.setdefault("PROJECT_ROOT", str(project_root))
        
        _default_test_files = str(project_root / "tests" / "files")
        variables.setdefault(
            "TEST_FILES_DIR",
            os.environ.get("YOUQU_TEST_FILES_DIR", _default_test_files),
        )
        
        _raw_app = data.get("app", "")
        if _raw_app:
            variables.setdefault(
                "APP_PATH",
                os.path.basename(_raw_app) if "/" in str(_raw_app) else str(_raw_app),
            )

        for _ in range(5):
            prev = dict(variables)
            variables = {k: substitute_dict({k: v}, variables)[k] for k, v in variables.items()}
            if variables == prev:
                break

        data = substitute_dict(data, variables)

    try:
        config = SuiteConfig.model_validate(data)
    except Exception as exc:
        return {"suite": str(suite_path), "status": "error", "error": str(exc)}

    elements = _load_elements(suite_path.parent)
    context = {"elements": elements}
    executor = AtSuiteExecutor(config, context)
    result = executor.run(spec_ids=spec_ids, tags=tags, skip_env_check=skip_env_check)
    return {
        "suite": str(suite_path),
        "status": "ok",
        "passed": result.passed,
        "failed": result.failed,
        "skipped": result.skipped,
        "timeout": result.timeout,
        "duration": round(result.duration, 2),
        "specs": [
            {
                "id": s.id,
                "name": s.name,
                "status": s.status.value if isinstance(s.status, SpecStatus) else s.status,
                "error": s.error,
                "duration": round(s.duration, 2),
            }
            for s in result.specs
        ],
    }


def _parse_yaml(path: Path) -> Optional[dict]:
    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception as exc:
        _log.error("failed to parse %s: %s", path, exc)
        return None


def run_tests(
    test_dir: str = "tests/at/yaml",
    suite: Optional[str] = None,
    keyword: Optional[str] = None,
    spec_ids: Optional[str] = None,
    tags: Optional[str] = None,
    skip_env_check: bool = False,
) -> int:
    suite_files = _find_suite_files(test_dir, suite)
    if not suite_files:
        _log.warning("no suite files found in %s", test_dir)
        return 0

    total_passed = 0
    total_failed = 0
    total_skipped = 0
    results: list[dict] = []

    for suite_path in suite_files:
        suite_name = suite_path.stem
        print(f"  [{suite_name}] running ...", flush=True)
        r = _load_and_run_suite(
            suite_path,
            spec_ids=spec_ids,
            tags=tags,
            skip_env_check=skip_env_check,
        )
        if r["status"] == "ok":
            for spec in r.get("specs", []):
                icon = "✓" if spec["status"] == "passed" else ("✗" if spec["status"] == "failed" else "○")
                detail = f" — {spec['error']}" if spec.get("error") else ""
                print(f"    {icon} {spec['id']}: {spec['name']}{detail}", flush=True)
            total_passed += r["passed"]
            total_failed += r["failed"]
            total_skipped += r["skipped"]
        else:
            print(f"    ✗ ERROR: {r.get('error', 'unknown')}", flush=True)
            total_failed += 1
        results.append(r)

    _print_summary(results)
    return 1 if total_failed > 0 else 0


def _print_summary(results: list[dict]) -> None:
    total_suites = len(results)
    passed_suites = sum(1 for r in results if r["status"] == "ok" and r.get("failed", 0) == 0)
    failed_suites = sum(1 for r in results if r["status"] == "ok" and r.get("failed", 0) > 0)
    error_suites = sum(1 for r in results if r["status"] == "error")

    total_specs_passed = sum(r.get("passed", 0) for r in results)
    total_specs_failed = sum(r.get("failed", 0) for r in results)
    total_specs_skipped = sum(r.get("skipped", 0) for r in results)

    print(f"\n{'=' * 60}")
    print(
        f"Suites: {passed_suites} passed, {failed_suites} failed, {error_suites} error ({total_suites} total)"
    )
    print(
        f"Specs:  {total_specs_passed} passed, {total_specs_failed} failed, {total_specs_skipped} skipped"
    )
    print(f"{'=' * 60}")


# ---- L2: Module smoke test ----


def _select_representative_case(cases: list[dict]) -> dict | None:
    """Select the representative case for L2 smoke test.

    Criteria: fewest steps + highest selector coverage.
    """
    if not cases:
        return None
    scored = []
    for case in cases:
        steps = case.get("steps", [])
        action_steps = [s for s in steps if s.get("step_type") == "action"]
        has_selector = sum(
            1 for s in action_steps if s.get("selector") or s.get("selected")
        )
        coverage = (has_selector / len(action_steps)) if action_steps else 0.0
        scored.append((len(steps), -coverage, case))
    scored.sort(key=lambda x: (x[0], x[1]))
    return scored[0][2] if scored else None


def smoke_test_module(
    module_dir: str,
    suite_yaml: str = "",
    skip_env_check: bool = False,
) -> dict[str, Any]:
    """L2: Run a representative case from a module directory.

    Executes session_start → first 3 action steps → 1 assert step → session_stop.
    Verifies that the module's AT-SPI elements are runtime-addressable.

    Returns {"module": str, "status": "pass"|"fail", "details": [...]}.
    """
    module_path = Path(module_dir)
    module_name = module_path.name

    if suite_yaml:
        suite_path = Path(suite_yaml)
    else:
        suite_files = sorted(module_path.rglob("*.suite.yaml"))
        if not suite_files:
            return {
                "module": module_name,
                "status": "skip",
                "reason": "no .suite.yaml found",
            }
        suite_path = suite_files[0]

    r = _load_and_run_suite(suite_path, skip_env_check=skip_env_check)
    if r["status"] == "error":
        return {
            "module": module_name,
            "status": "fail",
            "reason": r.get("error", "unknown"),
            "suite": str(suite_path),
        }

    passed = r.get("passed", 0)
    failed = r.get("failed", 0)
    return {
        "module": module_name,
        "status": "pass" if failed == 0 and passed > 0 else "fail",
        "passed": passed,
        "failed": failed,
        "suite": str(suite_path),
        "specs": r.get("specs", []),
    }


def smoke_test_all_modules(
    modules_dir: str,
    skip_env_check: bool = False,
) -> list[dict[str, Any]]:
    """L2: Run smoke test for every module in modules_dir."""
    base = Path(modules_dir)
    if not base.is_dir():
        _log.error("modules directory not found: %s", modules_dir)
        return []

    results = []
    for module_dir in sorted(base.iterdir()):
        if not module_dir.is_dir():
            continue
        _log.info("L2 smoke test: %s", module_dir.name)
        result = smoke_test_module(str(module_dir), skip_env_check=skip_env_check)
        results.append(result)
        status_icon = "✓" if result["status"] == "pass" else "✗"
        print(f"  {status_icon} {module_dir.name}: {result['status']}")

    passed = sum(1 for r in results if r["status"] == "pass")
    failed = sum(1 for r in results if r["status"] == "fail")
    skipped = sum(1 for r in results if r["status"] == "skip")
    print(f"\nL2 Smoke: {passed} passed, {failed} failed, {skipped} skipped")
    return results


# ---- L3: Single case runtime verification ----


def verify_single_case(
    suite_yaml: str,
    spec_id: str = "",
    skip_env_check: bool = True,
) -> dict[str, Any]:
    """L3: Run a single case with detailed logging for diagnosis.

    Triggered when: precandidate top-1 score < 2.0, high priority,
    L1 warns, or L2 failure diagnosis.
    """
    suite_path = Path(suite_yaml)
    if not suite_path.exists():
        return {"suite": suite_yaml, "status": "error", "reason": "file not found"}

    _log.info("L3 verify: %s (spec_id=%s)", suite_path, spec_id)

    r = _load_and_run_suite(
        suite_path,
        spec_ids=spec_id,
        skip_env_check=skip_env_check,
    )

    if r["status"] == "error":
        return {"suite": str(suite_path), "status": "error", "reason": r.get("error")}

    return {
        "suite": str(suite_path),
        "spec_id": spec_id,
        "status": "pass" if r.get("failed", 1) == 0 else "fail",
        "passed": r.get("passed", 0),
        "failed": r.get("failed", 0),
        "duration": r.get("duration", 0),
        "specs": r.get("specs", []),
    }
