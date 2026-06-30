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
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {_youqu_version}"
    )
    sub = parser.add_subparsers(dest="command")

    # youqu make <name>
    p_make = sub.add_parser("make", help="Generate autotest/ skeleton")
    p_make.add_argument("name", help="App name (e.g. terminal)")
    p_make.add_argument("--dir", default=".", help="Output directory (default: CWD)")
    p_make.add_argument(
        "--format",
        default="yaml",
        choices=["yaml", "py", "all"],
        help="Skeleton format: yaml (default), py (Python only), all (both)",
    )

    # youqu run [pytest args...]
    p_run = sub.add_parser("run", help="Run tests from autotest/")
    p_run.add_argument("-a", "--app", default="", help="Override autotest path")
    p_run.add_argument(
        "--multica-report",
        action="store_true",
        default=False,
        help="Enable multica batch execution with progress reporting",
    )
    p_run.add_argument(
        "--issue-id",
        type=str,
        default="",
        help="Multica issue ID (required with --multica-report)",
    )
    p_run.add_argument(
        "--batch-size",
        type=int,
        default=20,
        help="Cases per batch (default: 20)",
    )
    p_run.add_argument(
        "--case-timeout",
        type=int,
        default=90,
        help="Per-case timeout in seconds (default: 90)",
    )
    p_run.add_argument(
        "--module",
        type=str,
        default="",
        help="Filter by module name",
    )
    p_run.add_argument(
        "--tag",
        type=str,
        default="",
        help="Filter by tags (comma-separated)",
    )

    # youqu report
    p_report = sub.add_parser("report", help="Generate Allure HTML report")
    p_report.add_argument("-a", "--app", default="", help="Override autotest path")
    p_report.add_argument(
        "--clean",
        action="store_true",
        help="Clean output directory before generating",
    )
    p_report.add_argument(
        "--serve",
        action="store_true",
        help="Serve report via HTTP after generation (dynamic port, 0.0.0.0)",
    )

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

    # youqu index
    p_index = sub.add_parser("index", help="Manage YAML test index")
    p_index.add_argument("--rebuild", action="store_true", help="Rebuild index from YAML files")
    p_index.add_argument("--list", action="store_true", help="List test cases")
    p_index.add_argument("--app", default="", help="Filter by app")
    p_index.add_argument("--module", default="", help="Filter by module")
    p_index.add_argument("--tag", default="", help="Filter by tag (comma-separated)")

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
    p_web_run.add_argument("--verbose", action="store_true", help="Show action and assertion details")

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
    p_web_init.add_argument("config_path", nargs="?", default="web_spec.yaml", help="Config file path")
    p_web_init.add_argument("--force", action="store_true", help="Overwrite existing config file")

    p_web_suite = web_spec_sub.add_parser("suite", help="Run Web spec suite file")
    p_web_suite.add_argument("suite_path", help="Web spec suite.yaml path")
    p_web_suite.add_argument("--config", default=None, help="Web spec config path")
    p_web_suite.add_argument("--headed", action="store_true", help="Run browser in headed mode")
    p_web_suite.add_argument("--report-dir", default=None, help="Report output directory")
    p_web_suite.add_argument("--dry-run", action="store_true", help="Load and validate suite only")
    p_web_suite.add_argument("--no-screenshot", action="store_true", help="Disable step screenshots")
    p_web_suite.add_argument("--verbose", action="store_true", help="Show action and assertion details")

    # youqu dev <subcommand>
    p_dev = sub.add_parser("dev", help="Dev-mode suite management")
    dev_sub = p_dev.add_subparsers(dest="dev_command")

    p_dev_init = dev_sub.add_parser("init", help="Create dev-yaml/ directory")

    p_dev_make = dev_sub.add_parser("make", help="Create skeleton .suite.yaml")
    p_dev_make.add_argument("name", help="Suite name (e.g. 键盘-快捷键)")
    p_dev_make.add_argument("--force", action="store_true", help="Overwrite existing file")

    p_dev_list = dev_sub.add_parser("list", help="List suites or spec details")
    p_dev_list.add_argument("name", nargs="?", default="", help="Suite name filter")

    p_dev_run = dev_sub.add_parser("run", help="Execute a suite")
    p_dev_run.add_argument("name", help="Suite name (e.g. 键盘-快捷键)")
    p_dev_run.add_argument("--spec", default="", help="Spec IDs (comma-separated)")
    p_dev_run.add_argument("--tag", default="", help="Filter by tags (comma-separated)")
    p_dev_run.add_argument("--skip-env-check", action="store_true", help="Skip environment checks")

    # youqu startproject <name>
    p_sp = sub.add_parser("startproject", help="Create project from template")
    p_sp.add_argument("name", nargs="?", help="Project name (default: youqu)")

    # youqu inspect <app_path> [app_args...]
    p_inspect = sub.add_parser("inspect", help="Inspect app accessibility events (NDJSON output)")
    p_inspect.add_argument("app_path", help="Application executable path")
    p_inspect.add_argument("app_args", nargs="*", help="Arguments passed to application")

    args, extra = parser.parse_known_args()

    if args.command == "make":
        from youqu.cli.make import generate
        generate(args.name, args.dir, fmt=args.format)
    elif args.command == "run":
        if args.multica_report and not args.issue_id:
            print("Error: --issue-id is required when --multica-report is set")
            sys.exit(1)
        from youqu.cli.run import run
        run(
            autotest_path=args.app or None,
            extra=extra,
            multica_report=args.multica_report,
            issue_id=args.issue_id,
            batch_size=args.batch_size,
            case_timeout=args.case_timeout,
            module=args.module,
            tag=args.tag,
        )
    elif args.command == "report":
        from youqu.cli.report import run as report_run
        report_run(autotest_path=args.app or None, clean=args.clean, serve=args.serve)
    elif args.command == "mcp":
        from youqu.src.mcp.server import start as mcp_start
        mcp_start(transport=args.transport, port=args.port, host=args.host)
    elif args.command == "doctor":
        from youqu.cli.doctor import run as doctor_run
        doctor_run()
    elif args.command == "index":
        from youqu.cli.index import run as index_run
        index_run(args)
    elif args.command == "dev":
        from youqu.cli.dev import cmd_init, cmd_list, cmd_make, cmd_run
        dispatch = {
            "init": cmd_init,
            "make": cmd_make,
            "list": cmd_list,
            "run": cmd_run,
        }
        handler = dispatch.get(args.dev_command)
        if handler:
            handler(args)
        else:
            print("Unknown dev command. Usage: youqu dev {init|make|list|run}")
            sys.exit(1)
    elif args.command == "web-spec":
        from youqu.cli.web_spec import run as web_spec_run
        web_spec_run(args)
    elif args.command == "startproject":
        from youqu.src.startproject import cli
        cli()
    elif args.command == "inspect":
        try:
            from youqu.src.atspi_inspector import AtspiInspector
            inspector = AtspiInspector()
            inspector.inspect(args.app_path, args.app_args)
        except ImportError as e:
            print(f"AT-SPI inspector requires: sudo apt install at-spi2-core python3-pyatspi\n{e}", file=sys.stderr)
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
