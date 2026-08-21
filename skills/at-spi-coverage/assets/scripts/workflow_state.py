#!/usr/bin/env python3
"""workflow-state.json 读写脚本。

用法：
  python3 workflow_state.py init <project_path> <project_name>
  python3 workflow_state.py set <key> <value>
  python3 workflow_state.py get <key>
  python3 workflow_state.py status
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

STATE_FILE = Path("workflow-state.json")


def load() -> dict:
    if STATE_FILE.is_file():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}


def save(state: dict) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def main():
    if len(sys.argv) < 2:
        print("Usage: workflow_state.py <init|set|get|status> [...]")
        sys.exit(1)

    op = sys.argv[1]

    if op == "init":
        if len(sys.argv) < 4:
            print("Usage: workflow_state.py init <project_path> <project_name>")
            sys.exit(1)
        state = {
            "project_path": sys.argv[2],
            "project_name": sys.argv[3],
            "phase": "init",
            "pipeline_a_done": False,
            "pipeline_b_done": False,
            "report_done": False,
        }
        save(state)
        print(f"State initialized: {state['project_name']} @ {state['project_path']}")

    elif op == "set":
        if len(sys.argv) < 4:
            print("Usage: workflow_state.py set <key> <value>")
            sys.exit(1)
        state = load()
        key = sys.argv[2]
        val = sys.argv[3]
        # Try to parse as JSON
        try:
            val = json.loads(val)
        except (json.JSONDecodeError, ValueError):
            pass
        state[key] = val
        save(state)
        print(f"Set {key} = {val}")

    elif op == "get":
        if len(sys.argv) < 3:
            print("Usage: workflow_state.py get <key>")
            sys.exit(1)
        state = load()
        val = state.get(sys.argv[2], "<not set>")
        print(val)

    elif op == "status":
        state = load()
        if not state:
            print("No workflow state (workflow-state.json not found)")
            sys.exit(1)
        print(json.dumps(state, indent=2))

    else:
        print(f"Unknown operation: {op}")
        sys.exit(1)


if __name__ == "__main__":
    main()