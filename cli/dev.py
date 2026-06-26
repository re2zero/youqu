from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from src.yaml_test.suite import SuiteExecutor, SuiteResult, parse_suite
from src.yaml_test.suite.models import SuiteSpec


def _find_dev_yaml_dir() -> Path | None:
    candidates = [
        Path.cwd() / "dev-yaml",
        Path.cwd() / "autotest" / "dev-yaml",
    ]
    env_dir = Path(__file__).resolve().parent.parent / "dev-yaml"
    for path in candidates + [env_dir]:
        if path.is_dir():
            return path
    return None


def _find_suite_path(name: str) -> Path | None:
    base = _find_dev_yaml_dir()
    if base is None:
        return None
    for p in sorted(base.glob("*.suite.yaml")):
        if p.stem == name:
            return p
    for p in sorted(base.glob("*.suite.yaml")):
        prefix = p.name[: -len(".suite.yaml")]
        if prefix == name or prefix.startswith(name + "-"):
            return p
    return None


def _list_suites(dev_dir: Path) -> list[tuple[str, Path]]:
    suites = []
    for p in sorted(dev_dir.glob("*.suite.yaml")):
        suites.append((p.stem, p))
    return suites


def cmd_init(args: Any) -> None:
    """youqu dev init — create dev-yaml/ directory."""
    base = Path.cwd() / "dev-yaml"
    base.mkdir(parents=True, exist_ok=True)
    gitkeep = base / ".gitkeep"
    if not gitkeep.exists():
        gitkeep.touch()
    print(f"Created dev-yaml/ at {base}")


def cmd_make(args: Any) -> None:
    """youqu dev make <name> — create skeleton .suite.yaml."""
    dev_dir = _find_dev_yaml_dir()
    if dev_dir is None:
        dev_dir = Path.cwd() / "dev-yaml"
        dev_dir.mkdir(parents=True, exist_ok=True)

    name = args.name
    suite_path = dev_dir / f"{name}.suite.yaml"
    if suite_path.exists() and not args.force:
        print(f"Error: {suite_path} already exists (use --force to overwrite)")
        sys.exit(1)

    skeleton = f"""\
name: "{name}"
app: ""
module: ""
# env_check:
#   - type: process
#     name: ""
#     expect: "not_running"
# setup:
#   - action: session_start
#     command: ""
specs:
  - id: sample
    name: "示例操作"
    steps:
      - action: wait
        wait: 0.3
# teardown:
#   - action: session_stop
"""
    suite_path.write_text(skeleton, encoding="utf-8")
    print(f"Created {suite_path}")


def cmd_list(args: Any) -> None:
    """youqu dev list [name] — list suites or spec details."""
    dev_dir = _find_dev_yaml_dir()
    if dev_dir is None:
        print("No dev-yaml/ directory found. Run 'youqu dev init' first.")
        return

    suites = _list_suites(dev_dir)
    if not suites:
        print(f"No .suite.yaml files found in {dev_dir}")
        return

    if args.name:
        # Show spec details for a specific suite
        suite_path = _find_suite_path(args.name)
        if suite_path is None:
            _fuzzy_list(suites, args.name)
            return
        suite = parse_suite(suite_path)
        _print_suite_detail(suite, suite_path)
    else:
        # List all suites
        print(f"\nDev suites ({dev_dir}):\n")
        for stem, p in suites:
            try:
                suite = parse_suite(p)
                spec_count = len(suite.specs)
                tags = ",".join(suite.tags) if suite.tags else "-"
                print(f"  {stem}")
                print(f"    App: {suite.app or '-'}  |  Module: {suite.module or '-'}  |  Tags: {tags}")
                print(f"    Specs: {spec_count}")
                print()
            except Exception:
                print(f"  {stem}  [parse error]")


def _fuzzy_list(suites: list[tuple[str, Path]], partial: str) -> None:
    print(f"No exact match for '{partial}'. Available suites:")
    for stem, _ in suites:
        print(f"  {stem}")


def _print_suite_detail(suite: SuiteSpec, suite_path: Path) -> None:
    print(f"\nSuite: {suite.name}")
    print(f"File:  {suite_path}")
    print(f"App:   {suite.app or '-'}")
    print(f"Module: {suite.module or '-'}")
    if suite.tags:
        print(f"Tags:  {', '.join(suite.tags)}")
    if suite.env_check:
        print(f"Env checks: {len(suite.env_check)}")
    print(f"\nSpecs ({len(suite.specs)}):\n")
    for spec in suite.specs:
        skip_tag = f"  [SKIP: {spec.skip}]" if spec.skip else ""
        tags = f"  tags: {','.join(spec.tags)}" if spec.tags else ""
        timeout = f"  timeout: {spec.timeout}s" if spec.timeout else ""
        print(f"  {spec.id}: {spec.name}{skip_tag}")
        print(f"    Steps: {len(spec.steps)}{tags}{timeout}")
        print()


def cmd_run(args: Any) -> None:
    """youqu dev run <name> — execute a suite."""
    suite_path = _find_suite_path(args.name)
    if suite_path is None:
        print(f"Error: no suite matching '{args.name}' found in dev-yaml/")
        sys.exit(1)

    suite = parse_suite(suite_path)
    spec_ids = args.spec or None
    tags = args.tag or None
    skip_env_check = args.skip_env_check
    fast = args.fast

    if fast:
        result = _run_in_process(suite, spec_ids, tags, skip_env_check)
    else:
        result = _run_subprocess(suite_path, spec_ids, tags, skip_env_check)

    _print_result(result)
    sys.exit(1 if result.failed > 0 else 0)


def _run_in_process(
    suite: SuiteSpec, spec_ids: str | None, tags: str | None, skip_env: bool,
) -> SuiteResult:
    executor = SuiteExecutor(suite)
    return executor.run(spec_ids=spec_ids, tags=tags, skip_env_check=skip_env)


def _run_subprocess(
    suite_path: Path, spec_ids: str | None, tags: str | None, skip_env: bool,
) -> SuiteResult:
    cmd = [
        sys.executable, "-m", "src.yaml_test.suite",
        str(suite_path),
    ]
    if spec_ids:
        cmd.extend(["--spec", spec_ids])
    if tags:
        cmd.extend(["--tag", tags])
    if skip_env:
        cmd.append("--skip-env-check")

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
    except OSError as exc:
        return SuiteResult(
            suite_name=suite_path.stem,
            error=f"subprocess launch failed: {exc}",
        )

    try:
        stdout, stderr = proc.communicate(timeout=300)
    except subprocess.TimeoutExpired:
        proc.kill()
        return SuiteResult(
            suite_name=suite_path.stem,
            error="subprocess timed out after 300s",
        )

    if stderr:
        return SuiteResult(
            suite_name=suite_path.stem,
            error=stderr.decode("utf-8", errors="replace"),
        )

    try:
        data = json.loads(stdout)
        if "error" in data:
            return SuiteResult(suite_name=suite_path.stem, error=data["error"])
        return SuiteResult.model_validate(data)
    except (json.JSONDecodeError, Exception) as exc:
        return SuiteResult(
            suite_name=suite_path.stem,
            error=f"result parse failed: {exc}",
        )


def _print_result(result: SuiteResult) -> None:
    total = result.total
    passed = result.passed
    failed = result.failed
    skipped = result.skipped
    timeout = result.timeout

    print(f"\n{'='*60}")
    print(f"  Suite: {result.suite_name}")
    print(f"  Duration: {result.duration:.2f}s")
    print(f"  Total: {total}  |  Passed: {passed}  |  Failed: {failed}  |  Skipped: {skipped}  |  Timeout: {timeout}")
    if result.error:
        print(f"  Error: {result.error}")
    print(f"{'='*60}\n")

    for spec in result.specs:
        status_icon = {
            "passed": "\u2713",
            "failed": "\u2717",
            "skipped": "-",
            "timeout": "\u23F0",
        }.get(spec.status, "?")
        print(f"  {status_icon} [{spec.status}] {spec.id} ({spec.duration:.2f}s)")
        if spec.error:
            print(f"           {spec.error}")
