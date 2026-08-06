# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only

"""YouQu CLI entry point.

Registered as console_scripts: youqu = "youqu.cli.main:main"
"""

import argparse
import sys
from pathlib import Path

_YOUQU_PKG = Path(__file__).resolve().parent.parent

_INJECT_PATHS = (
    _YOUQU_PKG,
    _YOUQU_PKG / "src",
    _YOUQU_PKG / "setting",
    _YOUQU_PKG / "src" / "depends",
)


def _inject_paths():
    for p in _INJECT_PATHS:
        p_str = str(p)
        if p_str not in sys.path:
            sys.path.insert(0, p_str)


def main():
    _inject_paths()
    try:
        from importlib.metadata import version as _get_version

        _youqu_version = _get_version("youqu-ai")
    except Exception:
        _youqu_version = "unknown"

    parser = argparse.ArgumentParser(
        prog="youqu",
        description="YouQu test framework CLI",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {_youqu_version}")
    sub = parser.add_subparsers(dest="command")

    # youqu mcp
    p_mcp = sub.add_parser("mcp", help="Start MCP server")
    p_mcp.add_argument(
        "--transport",
        default="stdio",
        choices=["stdio", "sse", "http"],
        help="Transport protocol (default: stdio)",
    )
    p_mcp.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    p_mcp.add_argument("--port", type=int, default=8000, help="HTTP port (default: 8000)")

    # youqu doctor
    sub.add_parser("doctor", help="Check and fix environment issues")

    # youqu web-spec
    p_web_spec = sub.add_parser("web-spec", help="Run and manage Web specs")
    web_spec_sub = p_web_spec.add_subparsers(dest="web_spec_command")

    p_web_run = web_spec_sub.add_parser("run", help="Run Web spec file or directory")
    p_web_run.add_argument("spec_path", help="Web spec file or directory")
    p_web_run.add_argument("--config", default=None, help="Web spec config path")
    p_web_run.add_argument("--headed", action="store_true", help="Run browser in headed mode")
    p_web_run.add_argument("--report-dir", default=None, help="Report output directory")
    p_web_run.add_argument("--dry-run", action="store_true", help="Load and validate specs only")
    p_web_run.add_argument("--no-screenshot", action="store_true", help="Disable step screenshots")
    p_web_run.add_argument(
        "--verbose", action="store_true", help="Show action and assertion details"
    )

    p_web_list = web_spec_sub.add_parser("list", help="List Web specs")
    p_web_list.add_argument("spec_dir", help="Web spec directory")
    p_web_list.add_argument("--module", default="", help="Filter by module")
    p_web_list.add_argument("--feature", default="", help="Filter by feature")
    p_web_list.add_argument("--tag", default="", help="Filter by tag (comma-separated)")

    p_web_index = web_spec_sub.add_parser("index", help="Rebuild Web spec index")
    p_web_index.add_argument("spec_dir", help="Web spec directory")

    p_web_check = web_spec_sub.add_parser("check", help="Statically check Web specs")
    p_web_check.add_argument("spec_path", help="Web spec file or directory")

    p_web_init = web_spec_sub.add_parser("init", help="Initialize Web spec config file")
    p_web_init.add_argument(
        "config_path", nargs="?", default="web_spec.yaml", help="Config file path"
    )
    p_web_init.add_argument("--force", action="store_true", help="Overwrite existing config file")

    p_web_suite = web_spec_sub.add_parser("suite", help="Run Web spec suite file")
    p_web_suite.add_argument("suite_path", help="Web spec suite.yaml path")
    p_web_suite.add_argument("--config", default=None, help="Web spec config path")
    p_web_suite.add_argument("--headed", action="store_true", help="Run browser in headed mode")
    p_web_suite.add_argument("--report-dir", default=None, help="Report output directory")
    p_web_suite.add_argument("--dry-run", action="store_true", help="Load and validate suite only")
    p_web_suite.add_argument(
        "--no-screenshot", action="store_true", help="Disable step screenshots"
    )
    p_web_suite.add_argument(
        "--verbose", action="store_true", help="Show action and assertion details"
    )

    # youqu startproject <name>
    p_sp = sub.add_parser("startproject", help="Create project from template")
    p_sp.add_argument("name", nargs="?", help="Project name (default: youqu)")

    # youqu at <subcommand>
    p_at = sub.add_parser("at", help="AT-SPI YAML test pipeline")
    at_sub = p_at.add_subparsers(dest="at_command")

    p_at_scan = at_sub.add_parser("scan", help="Scan source code for DTK/Qt widget classes")
    p_at_scan.add_argument("--src", required=True, help="App source directory")
    p_at_scan.add_argument("--app", required=True, help="App ID (e.g. dde-file-manager)")
    p_at_scan.add_argument("--output", default="tests/at", help="Output directory")
    p_at_scan.add_argument(
        "--include-dirs",
        nargs="*",
        default=None,
        help="Only scan source files under these subdirectories (e.g. src widgets)",
    )
    p_at_scan.add_argument(
        "--target-lang",
        default="zh_CN",
        help="Target language for translation lookup (default: zh_CN)",
    )
    p_at_scan.add_argument(
        "--compile-commands",
        default=None,
        help="Path to compile_commands.json (auto-detected if not specified)",
    )

    p_at_dump = at_sub.add_parser("dump", help="Dump AT-SPI tree")
    p_at_dump.add_argument("type", choices=["dtk"], help="App framework type")
    p_at_dump.add_argument("--app", required=True, help="App ID (e.g. dde-file-manager)")
    p_at_dump.add_argument("--src", default="", help="App source directory")
    p_at_dump.add_argument(
        "--launch", default="", help="Launch command (e.g. /usr/bin/dde-file-manager)"
    )
    p_at_dump.add_argument("--output", default="tests/at", help="Output directory")
    p_at_dump.add_argument(
        "--no-record",
        action="store_true",
        help="Skip interactive state recording (default: record)",
    )
    p_at_dump.add_argument(
        "--include-dirs",
        nargs="*",
        default=None,
        help="Only scan source files under these subdirectories (e.g. src widgets)",
    )

    p_at_record = at_sub.add_parser("record", help="Event-driven AT-SPI recording")
    p_at_record.add_argument("--app", required=True, help="App ID (e.g. dde-file-manager)")
    p_at_record.add_argument(
        "--launch",
        default="",
        help="Launch command (e.g. /usr/bin/dde-file-manager)",
    )
    p_at_record.add_argument("--output", default="tests/at", help="Output directory")
    p_at_record.add_argument(
        "--gui",
        action="store_true",
        help="GUI mode: PyQt6 floating widget with event log",
    )
    p_at_record.add_argument(
        "--module",
        default="",
        help="Module slug from plan.yaml — prints recording guide before recording",
    )
    p_at_record.add_argument(
        "--plan",
        default="tests/at/plan.yaml",
        help="Path to plan.yaml (used with --module)",
    )

    p_at_merge = at_sub.add_parser("merge", help="Layered merge: scan + record → at-tree.yaml")
    p_at_merge.add_argument("--app", default="", help="Application name")
    p_at_merge.add_argument("--scan", default="", help="Scan output directory (scanned_ok.yaml)")
    p_at_merge.add_argument("--record", required=True, help="Record output directory")
    p_at_merge.add_argument("--output", default="tests/at", help="Output directory")
    p_at_merge.add_argument(
        "--no-clean",
        action="store_true",
        help="Skip record session cleaning (keep invalid events)",
    )

    p_at_plan = at_sub.add_parser("plan", help="Generate module recording plan from cases_raw + docs")
    p_at_plan.add_argument("--cases", required=True, help="Path to cases_raw.yaml")
    p_at_plan.add_argument("--docs", default="", help="Docs directory (from youqu at docs)")
    p_at_plan.add_argument("--app", default="", help="Application name")
    p_at_plan.add_argument("--output", default="tests/at", help="Output directory")

    p_at_parse = at_sub.add_parser(
        "parse", help="Parse xlsx into cases.yaml (format conversion only)"
    )
    p_at_parse.add_argument("--input", required=True, help="Input xlsx or text directory")
    p_at_parse.add_argument("--at-tree", default="", help="(deprecated) Path to at-tree.yaml")
    p_at_parse.add_argument("--output", required=True, help="Output cases.yaml path")

    p_at_tree_info = at_sub.add_parser(
        "tree-info", help="Export compact at-tree listing for AI context"
    )
    p_at_tree_info.add_argument("--at-tree", required=True, help="Path to at-tree.yaml")
    p_at_tree_info.add_argument(
        "--output", required=True, help="Output compact tree-info file path"
    )
    p_at_tree_info.add_argument(
        "--format",
        choices=["yaml", "text"],
        default="yaml",
        help="Output format: yaml (structured, default) or text (legacy flat)",
    )

    p_at_map = at_sub.add_parser("map", help="(deprecated) Map operations to AT-SPI elements")
    p_at_map.add_argument("--at-tree", required=True, help="Path to at-tree.yaml")
    p_at_map.add_argument("--cases", required=True, help="Path to cases.yaml")
    p_at_map.add_argument("--output", required=True, help="Output element-mappings.yaml path")

    p_at_generate = at_sub.add_parser("generate", help="Generate executable YAML")
    p_at_generate.add_argument("--cases", required=True, help="Path to cases.yaml")
    p_at_generate.add_argument(
        "--mappings", default="", help="(deprecated) Path to element-mappings.yaml"
    )
    p_at_generate.add_argument("--output", required=True, help="Output directory")
    p_at_generate.add_argument("--app", default="", help="Application name (e.g. deepin-terminal)")
    p_at_generate.add_argument(
        "--at-tree", dest="at_tree", default="", help="Path to at-tree.yaml (for app name fallback)"
    )
    p_at_generate.add_argument(
        "--no-assert-gate",
        dest="assert_gate",
        action="store_false",
        help="Disable assertion gate (allow cases without assertions)",
    )

    p_at_run = at_sub.add_parser("run", help="Run AT-SPI YAML tests")
    p_at_run.add_argument("--testdir", default="tests/at/yaml", help="Test directory")
    p_at_run.add_argument("--suite", help="Run specific suite")
    p_at_run.add_argument("-k", help="Keyword filter")
    p_at_run.add_argument("--spec-ids", help="Filter by spec IDs (comma-separated)")
    p_at_run.add_argument("--tags", help="Filter by tags (comma-separated)")
    p_at_run.add_argument("--skip-env-check", action="store_true", help="Skip environment checks")
    # Multica integration (Fix #2)
    p_at_run.add_argument("--multica-report", action="store_true", default=False,
                          help="Enable multica batch progress reporting")
    p_at_run.add_argument("--issue-id", type=str, default="",
                          help="Multica issue ID (required with --multica-report)")
    p_at_run.add_argument("--app", type=str, default="",
                          help="Application name (for version detection)")
    p_at_run.add_argument("--report-interval", type=int, default=300,
                          help="Heartbeat interval in seconds (default: 300, i.e. 5 min)")

    p_at_validate = at_sub.add_parser(
        "validate", help="Run verification gates on AT pipeline artifacts"
    )
    p_at_validate.add_argument(
        "--gate",
        default="all",
        choices=["all", "1", "2", "3", "4", "5"],
        help="Which gate to run (default: all)",
    )
    p_at_validate.add_argument(
        "--at-tree-annotated", default="", help="Path to at-tree-annotated.yaml (Gate 1-4)"
    )
    p_at_validate.add_argument(
        "--suite-cases", default="", help="Path to suite-cases.yaml (Gate 2)"
    )
    p_at_validate.add_argument(
        "--cases-mapped", default="", help="Path to cases_mapped.yaml (Gate 3)"
    )
    p_at_validate.add_argument(
        "--generate-output", default="", help="Path to generate output dir (Gate 4)"
    )
    p_at_validate.add_argument(
        "--element-gaps", default="", help="Path to element_gaps.yaml (Gate 1)"
    )

    p_at_split = at_sub.add_parser("split", help="Split cases_raw.yaml into per-module directories")
    p_at_split.add_argument("--cases", required=True, help="Path to cases_raw.yaml")
    p_at_split.add_argument("--at-tree", required=True, help="Path to at-tree-annotated.yaml")
    p_at_split.add_argument("--output", required=True, help="Output directory")
    p_at_split.add_argument(
        "--app", default="", help="Application name (default: from cases source)"
    )

    p_at_docs = at_sub.add_parser("docs", help="Import deepin-manual for an app")
    p_at_docs.add_argument("app", help="App ID (e.g. deepin-terminal)")
    p_at_docs.add_argument("--output", default="docs", help="Output directory")

    p_at_precandidate = at_sub.add_parser(
        "precandidate", help="Pre-filter candidates for each step"
    )
    p_at_precandidate.add_argument("--cases", default="", help="Path to cases_raw.yaml")
    p_at_precandidate.add_argument("--at-tree", default="", help="Path to at-tree-annotated.yaml")
    p_at_precandidate.add_argument("--output", default="", help="Output suite-cases.yaml path")
    p_at_precandidate.add_argument(
        "--module-dir", default="", help="Module directory (alternative to --cases)"
    )

    p_at_smoke = at_sub.add_parser("smoke", help="L2: module smoke test (runtime addressability)")
    p_at_smoke.add_argument("--modules-dir", default="", help="Directory containing all modules")
    p_at_smoke.add_argument("--module-dir", default="", help="Single module directory")
    p_at_smoke.add_argument("--skip-env-check", action="store_true", help="Skip environment checks")

    p_at_verify = at_sub.add_parser("verify", help="L3: single case runtime verification")
    p_at_verify.add_argument("--suite", required=True, help="Path to .suite.yaml")
    p_at_verify.add_argument("--spec-id", default="", help="Specific spec ID to verify")
    p_at_verify.add_argument(
        "--skip-env-check", action="store_true", help="Skip environment checks"
    )

    args = parser.parse_args()

    if args.command == "mcp":
        from youqu.src.mcp.server import start as mcp_start

        mcp_start(transport=args.transport, port=args.port, host=args.host)
    elif args.command == "doctor":
        from youqu.cli.doctor import run as doctor_run

        doctor_run()
    elif args.command == "web-spec":
        from youqu.cli.web_spec import run as web_spec_run

        web_spec_run(args)
    elif args.command == "startproject":
        from youqu.src.startproject import cli

        cli()
    elif args.command == "at":
        from youqu.cli.at import (
            cmd_docs,
            cmd_dump,
            cmd_generate,
            cmd_map,
            cmd_merge,
            cmd_parse,
            cmd_plan,
            cmd_precandidate,
            cmd_record,
            cmd_run,
            cmd_scan,
            cmd_smoke,
            cmd_split,
            cmd_tree_info,
            cmd_validate,
            cmd_verify,
        )

        dispatch = {
            "scan": cmd_scan,
            "dump": cmd_dump,
            "record": cmd_record,
            "merge": cmd_merge,
            "plan": cmd_plan,
            "parse": cmd_parse,
            "tree-info": cmd_tree_info,
            "map": cmd_map,
            "generate": cmd_generate,
            "run": cmd_run,
            "validate": cmd_validate,
            "split": cmd_split,
            "docs": cmd_docs,
            "precandidate": cmd_precandidate,
            "smoke": cmd_smoke,
            "verify": cmd_verify,
        }
        handler = dispatch.get(args.at_command)
        if handler:
            handler(args)
        else:
            print(
                "Usage: youqu at {scan|dump|record|merge|plan|parse|tree-info|map|generate|run|validate|split|docs|precandidate|smoke|verify}"
            )
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
