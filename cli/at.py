# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only


def _not_implemented(cmd: str):
    print(f"youqu at {cmd}: not implemented yet")


def cmd_dump(args):
    try:
        from youqu.src.at.scanner.atspi_dumper import dump_at_spi_tree
        from youqu.src.at.scanner.clang_scanner import scan_source_dir
        from youqu.src.at.scanner.merger import merge_trees, write_at_tree_yaml

        print(f"Dumping AT-SPI tree for app: {args.app}")
        runtime_tree = dump_at_spi_tree(args.app)

        print(f"Scanning source directory: {args.src}")
        static_classes = scan_source_dir(args.src)

        print("Merging static skeleton with runtime dump...")
        merged = merge_trees(runtime_tree, static_classes)

        output_path = f"{args.output}/at-tree.yaml"
        write_at_tree_yaml(merged, output_path, app_name=args.app)
        print(f"Wrote {output_path}")
    except ImportError as e:
        _not_implemented(f"dump ({e})")
    except Exception as e:
        print(f"Error: {e}")


def cmd_parse(args):
    try:
        from youqu.src.at.generator.case_parser import parse_to_cases
        parse_to_cases(input_path=args.input, output_path=args.output)
    except ImportError:
        _not_implemented("parse")


def cmd_map(args):
    try:
        from youqu.src.at.generator.mapper import map_elements
        map_elements(at_tree_path=args.at_tree, cases_path=args.cases, output_path=args.output)
    except ImportError:
        _not_implemented("map")


def cmd_generate(args):
    try:
        from youqu.src.at.generator.yaml_generator import generate_yaml
        generate_yaml(cases_path=args.cases, mappings_path=args.mappings, output_dir=args.output)
    except ImportError:
        _not_implemented("generate")


def cmd_run(args):
    try:
        from youqu.src.at.executor.runner import run_tests
        run_tests(test_dir=args.testdir, suite=args.suite, keyword=args.k)
    except ImportError:
        _not_implemented("run")
