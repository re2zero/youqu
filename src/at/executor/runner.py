from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import yaml

from src.at.executor.executor import AtSuiteExecutor
from src.at.executor.models import SpecStatus
from src.at.parser.models import SuiteConfig

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
    elements_path = suite_dir / "elements.yaml"
    if elements_path.is_file():
        try:
            with open(elements_path, encoding="utf-8") as f:
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
        _log.info("running suite: %s", suite_path)
        r = _load_and_run_suite(
            suite_path,
            spec_ids=spec_ids,
            tags=tags,
            skip_env_check=skip_env_check,
        )
        results.append(r)
        if r["status"] == "ok":
            total_passed += r["passed"]
            total_failed += r["failed"]
            total_skipped += r["skipped"]
        else:
            _log.error("suite %s error: %s", suite_path, r.get("error"))
            total_failed += 1

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
    print(f"Suites: {passed_suites} passed, {failed_suites} failed, {error_suites} error ({total_suites} total)")
    print(f"Specs:  {total_specs_passed} passed, {total_specs_failed} failed, {total_specs_skipped} skipped")
    print(f"{'=' * 60}")

    for r in results:
        status_icon = "✓" if r["status"] == "ok" and r.get("failed", 0) == 0 else "✗"
        print(f"  {status_icon} {r['suite']}")
        for spec in r.get("specs", []):
            icon = "✓" if spec["status"] == "passed" else ("✗" if spec["status"] == "failed" else "○")
            detail = f" ({spec['error']})" if spec.get("error") else ""
            print(f"      {icon} {spec['id']}: {spec['name']}{detail}")
