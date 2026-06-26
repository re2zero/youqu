from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

from src.yaml_test.suite.executor import SuiteExecutor
from src.yaml_test.suite.parser import parse_suite


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: python -m src.yaml_test.suite <suite.yaml> [--spec IDs] [--tag TAGS] [--skip-env-check]"}))
        sys.exit(1)

    suite_path = Path(sys.argv[1])
    spec_ids = None
    tags = None
    skip_env_check = False
    i = 2
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == "--spec" and i + 1 < len(sys.argv):
            spec_ids = sys.argv[i + 1]
            i += 2
        elif arg == "--tag" and i + 1 < len(sys.argv):
            tags = sys.argv[i + 1]
            i += 2
        elif arg == "--skip-env-check":
            skip_env_check = True
            i += 1
        else:
            print(json.dumps({"error": f"unknown argument: {arg}"}))
            sys.exit(1)

    try:
        suite = parse_suite(suite_path)
    except Exception as exc:
        print(json.dumps({"error": f"parse failed: {exc}"}))
        sys.exit(1)

    try:
        executor = SuiteExecutor(suite)
        result = executor.run(
            spec_ids=spec_ids, tags=tags, skip_env_check=skip_env_check,
        )
        print(result.model_dump_json(indent=2))
        sys.exit(1 if result.failed > 0 else 0)
    except Exception as exc:
        print(json.dumps({"error": f"execution failed: {exc}", "traceback": traceback.format_exc()}))
        sys.exit(1)


if __name__ == "__main__":
    main()
