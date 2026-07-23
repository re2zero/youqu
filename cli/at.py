# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only


def _not_implemented(cmd: str):
    print(f"youqu at {cmd}: not implemented yet")


def cmd_scan(args):
    try:
        import multiprocessing
        import os
        import sys
        import threading
        from pathlib import Path

        from src.at.scanner.clang_scanner import (
            _get_cxx_stdlib_flags,
            _get_qt_dtk_include_flags,
            _worker_init,
            scan_source_dir,
        )
        from src.at.scanner.merger import (
            append_scan_entry,
            generate_name_gaps_report,
        )

        output = Path(args.output)
        output.mkdir(parents=True, exist_ok=True)

        ok_path = output / "scanned_ok.yaml"
        gaps_path = output / "scanned_gaps.yaml"

        if ok_path.exists():
            ok_path.unlink()
        if gaps_path.exists():
            gaps_path.unlink()

        _last_pct = [-1]

        def _progress_cb(i: int, total: int, fp: str):
            pct = (i * 100 // total) if total else 0
            if pct != _last_pct[0] or i == total:
                _last_pct[0] = pct
                bar_w = 20
                filled = bar_w * i // total if total else 0
                bar = "█" * filled + "░" * (bar_w - filled)
                print(
                    f"\r\033[K  scanning: {bar} {i}/{total} ({pct}%)",
                    file=sys.stderr,
                    end="",
                    flush=True,
                )


        def _file_done_cb(rel_path: str, classes: list, error):
            for cls in classes:
                has_names = cls.get("object_names") or cls.get("accessible_names") or cls.get("action_texts")
                target = ok_path if has_names else gaps_path
                append_scan_entry(str(target), cls)

        scan_holder = [None, None]

        def _run_scan_thread():
            try:
                scan_holder[0] = scan_source_dir(
                    args.src,
                    progress_cb=_progress_cb,
                    file_done_cb=_file_done_cb,
                    include_dirs=getattr(args, "include_dirs", None),
                    target_lang=getattr(args, "target_lang", "zh_CN"),
                    compile_commands=getattr(args, "compile_commands", None),
                )
            except Exception as e:
                scan_holder[1] = e

        scan_thread = threading.Thread(target=_run_scan_thread, daemon=True)
        scan_thread.start()
        print(f"  Scanning source: {args.src} ...", file=sys.stderr, end="", flush=True)

        scan_thread.join()
        print(file=sys.stderr, flush=True)

        scan_result = scan_holder[0]
        scan_error = scan_holder[1]

        if scan_error:
            print(f"  Scan error: {scan_error}", file=sys.stderr, flush=True)
            return

        if scan_result:
            stats = scan_result.stats
            n_ok = sum(
                1 for c in scan_result.classes if c.get("object_names") or c.get("accessible_names")
            )
            n_gaps = len(scan_result.classes) - n_ok
            msg = f"  Scan done: {len(scan_result.classes)} UI classes in {stats['total_files']} files"
            if stats["failed_files"]:
                msg += f" ({stats['failed_files']} failed)"
            print(msg, file=sys.stderr, flush=True)
            print(f"  -> {ok_path} ({n_ok} with names)")
            if n_gaps > 0:
                print(f"  -> {gaps_path} ({n_gaps} missing names)")

            gaps_report_path = output / "element_gaps.yaml"
            generate_name_gaps_report(scan_result.classes, str(gaps_report_path), app_name=args.app)
            print(f"  -> {gaps_report_path}")
        else:
            print("  Scan failed — no results")

    except ImportError as e:
        _not_implemented(f"scan ({e})")
    except Exception as e:
        print(f"Error: {e}")


def cmd_split(args):
    from src.at.generator.splitter import split_cases

    split_cases(
        cases_path=args.cases,
        at_tree_path=args.at_tree,
        output_dir=args.output,
        app_name=getattr(args, "app", ""),
    )


def cmd_docs(args):
    from src.at.generator.manual_loader import cmd_docs as _cmd_docs

    _cmd_docs(args)


def cmd_precandidate(args):
    from src.at.generator.precandidate import (
        precandidate_from_cases,
        precandidate_from_module,
    )

    if getattr(args, "module_dir", None):
        precandidate_from_module(args.module_dir)
    else:
        precandidate_from_cases(
            cases_path=args.cases,
            at_tree_path=args.at_tree,
            output_path=args.output,
        )


def cmd_smoke(args):
    from src.at.executor.runner import smoke_test_all_modules, smoke_test_module

    if args.module_dir:
        result = smoke_test_module(args.module_dir, skip_env_check=args.skip_env_check)
        print(f"  {result['module']}: {result['status']}")
    else:
        smoke_test_all_modules(args.modules_dir, skip_env_check=args.skip_env_check)


def cmd_verify(args):
    from src.at.executor.runner import verify_single_case

    result = verify_single_case(
        suite_yaml=args.suite,
        spec_id=args.spec_id,
        skip_env_check=args.skip_env_check,
    )
    status_icon = "✓" if result["status"] == "pass" else "✗"
    print(f"  {status_icon} {result.get('suite', '')} [{result['status']}]")
    for spec in result.get("specs", []):
        icon = "✓" if spec["status"] == "passed" else "✗"
        print(f"    {icon} {spec['id']}: {spec['name']}")
        if spec.get("error"):
            print(f"       error: {spec['error']}")


def cmd_record(args):
    """Event-driven AT-SPI recording engine.

    Captures AT-SPI focus/window/children-changed events and input events
    (mouse/keyboard), organizes into segments, and outputs
    record_session.yaml + states/*.yaml.
    """
    try:
        import sys

        from src.at.scanner.recorder import RecordSession, qt_available

        gui_mode = getattr(args, "gui", False)
        if gui_mode and not qt_available():
            print("PyQt6 not installed — falling back to CLI mode")
            gui_mode = False

        module_slug = getattr(args, "module", "") or ""

        if module_slug:
            plan_path = getattr(args, "plan", "") or "tests/at/plan.yaml"
            try:
                from src.at.generator.plan_generator import get_module_guide

                guide = get_module_guide(plan_path, module_slug)
                if guide:
                    print(f"\n[RECORD] Module: {module_slug}", file=sys.stderr)
                    print(f"[RECORD] Recording guide:\n{guide}", file=sys.stderr)
                    print(file=sys.stderr)
                else:
                    print(
                        f"\n[RECORD] Module '{module_slug}' not found in {plan_path}",
                        file=sys.stderr,
                    )
            except FileNotFoundError:
                print(f"\n[RECORD] Plan file not found: {plan_path}", file=sys.stderr)
            except Exception as e:
                print(f"[RECORD] Could not load plan: {e}", file=sys.stderr)

        session = RecordSession(
            app_name=args.app,
            output_dir=args.output,
            gui_mode=gui_mode,
            launch_cmd=getattr(args, "launch", None),
        )
        session.start()
    except ImportError as e:
        print(f"Error: {e}")
        print("Install dependencies: pip install pyatspi2 python-xlib")
    except Exception as e:
        print(f"Error: {e}")


def cmd_plan(args):
    """Generate module-by-module recording plan from cases_raw + docs."""
    try:
        from src.at.generator.plan_generator import generate_plan

        generate_plan(
            cases_path=args.cases,
            docs_dir=getattr(args, "docs", ""),
            output_dir=args.output,
            app_name=getattr(args, "app", ""),
        )
    except ImportError as e:
        print(f"Error: {e}")
    except Exception as e:
        print(f"Error: {e}")


def cmd_merge(args):
    """Layered merge: scan output + record session → at-tree.yaml.

    Merges persistent-layer snapshots (launch + window:activate) with
    last-wins states, extracts transient contexts (menu/dialog/child_window),
    and injects static scan info.  Outputs at-tree.yaml (v2.0).
    """
    try:
        import sys
        from pathlib import Path
        from src.at.scanner.merger import (
            layered_merge,
            load_record_session,
            merge_trees,
            write_at_tree_yaml,
            write_element_gaps,
        )
        from src.at.scanner.clang_scanner import scan_source_dir

        output = Path(args.output)
        output.mkdir(parents=True, exist_ok=True)

        scan_dir = Path(args.scan) if args.scan else None
        record_dir = Path(args.record) if args.record else None

        scan_classes: list = []

        if scan_dir and scan_dir.is_dir():
            scanned_ok = scan_dir / "scanned_ok.yaml"
            if scanned_ok.is_file():
                import yaml

                with open(scanned_ok, encoding="utf-8") as f:
                    for doc in yaml.safe_load_all(f):
                        if doc:
                            scan_classes.append(doc)
                print(f"  Loaded {len(scan_classes)} static classes from {scanned_ok}")
            else:
                print(f"  Warning: scanned_ok.yaml not found in {scan_dir}")

        if not record_dir or not record_dir.is_dir():
            print("Error: --record directory is required and must exist")
            sys.exit(1)

        session = load_record_session(record_dir)
        if session:
            print(
                f"  Record session: {session.get('app', '?')}, "
                f"{len(session.get('segments', []))} segments"
            )
        else:
            print("  No record_session.yaml found — using old-style state snapshots")

        merged, transient = layered_merge(
            scan_classes, record_dir, clean=not getattr(args, "no_clean", False)
        )

        final_path = output / "at-tree.yaml"
        write_at_tree_yaml(
            merged,
            str(final_path),
            app_name=args.app,
            transient_contexts=transient,
        )
        print(f"  -> {final_path} ({len(merged)} root nodes, {len(transient)} transient contexts)")

        gaps_path = output / "element_gaps.yaml"
        write_element_gaps(merged, str(gaps_path), app_name=args.app)
        print(f"  -> {gaps_path}")

    except ImportError as e:
        print(f"Error: {e}")
    except Exception as e:
        print(f"Error: {e}")


def cmd_dump(args):
    try:
        import multiprocessing
        import os
        import subprocess
        import sys
        import threading
        import time
        from pathlib import Path
        from src.at.scanner.atspi_dumper import dump_at_spi_tree
        from src.at.scanner.clang_scanner import _worker_init, scan_source_dir
        from src.at.scanner.merger import (
            append_scan_entry,
            load_state_snapshots,
            merge_state_snapshots,
            merge_trees,
            write_at_tree_yaml,
            write_element_gaps,
            write_runtime_dump,
        )

        output = Path(args.output)
        dump_dir = output / "dump"
        dump_dir.mkdir(parents=True, exist_ok=True)

        launched_process = None

        if getattr(args, "launch", None):
            print(f"[1/3] Launching app: {args.launch}")
            env = os.environ.copy()
            env["QT_LINUX_ACCESSIBILITY_ALWAYS_ON"] = "1"
            launched_process = subprocess.Popen(
                args.launch.split(),
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            for sec in range(5, 0, -1):
                dots = "." * (5 - sec)
                print(f"\r  waiting{dots} {sec}s", end="", flush=True)
                time.sleep(1)
            print("\r  waiting.... done")
        else:
            print(f"[1/3] Dumping AT-SPI tree (app should be running)...")

        runtime_tree = dump_at_spi_tree(args.app)
        if not runtime_tree:
            print(f"  ERROR: Application '{args.app}' not found in AT-SPI tree")
            if launched_process:
                launched_process.terminate()
            return
        runtime_path = dump_dir / "runtime.yaml"
        write_runtime_dump(runtime_tree, str(runtime_path), app_name=args.app)
        print(f"  -> {runtime_path}")

        scan_result = None
        scan_pool = None
        scan_thread = None
        do_record = not getattr(args, "no_record", False)

        if args.src:
            ok_path = dump_dir / "scanned_ok.yaml"
            gaps_path = dump_dir / "scanned_gaps.yaml"

            _last_pct = -1

            def _progress_cb(i: int, total: int, fp: str):
                nonlocal _last_pct
                pct = (i * 100 // total) if total else 0
                if pct != _last_pct or i == total:
                    _last_pct = pct
                    bar_w = 20
                    filled = bar_w * i // total if total else 0
                    bar = "█" * filled + "░" * (bar_w - filled)
                    print(
                        f"\r\033[K  scanning: {bar} {i}/{total} ({pct}%)",
                        file=sys.stderr,
                        end="",
                        flush=True,
                    )

            def _file_done_cb(rel_path: str, classes: list, error):
                for cls in classes:
                    has_names = cls.get("object_names") or cls.get("accessible_names")
                    target = ok_path if has_names else gaps_path
                    append_scan_entry(str(target), cls)

            from src.at.scanner.clang_scanner import (
                _get_qt_dtk_include_flags,
                _get_cxx_stdlib_flags,
            )

            extra_args = ["-x", "c++", "-std=c++17", "-fPIC"]
            extra_args.extend(_get_cxx_stdlib_flags())
            extra_args.extend(_get_qt_dtk_include_flags())
            n_workers = min(os.cpu_count() or 4, 8)

            scan_pool = multiprocessing.Pool(
                processes=n_workers, initializer=_worker_init, initargs=(extra_args,)
            )

            scan_holder = [None, None]  # [ScanResult, Exception]

            def _run_scan_thread():
                try:
                    scan_holder[0] = scan_source_dir(
                        args.src,
                        progress_cb=_progress_cb,
                        file_done_cb=_file_done_cb,
                        include_dirs=args.include_dirs,
                        pool=scan_pool,
                    )
                except Exception as e:
                    scan_holder[1] = e

            scan_thread = threading.Thread(target=_run_scan_thread, daemon=True)
            scan_thread.start()
            print(f"  Scanning source: {args.src} ...", file=sys.stderr, end="", flush=True)

        if do_record:
            try:
                from src.at.scanner.recorder import ATRecorderManager, qt_available

                if not qt_available():
                    print("  PyQt6 not installed, falling back to CLI recording")
                    states_dir = dump_dir / "states"
                    states_dir.mkdir(parents=True, exist_ok=True)
                    state_index = 0
                    print(f"\n[2/3] Recording states - operate the app, then capture:")
                    while True:
                        try:
                            cmd = input("  [Enter=capture, done=finish] ").strip().lower()
                        except (EOFError, KeyboardInterrupt):
                            print()
                            break
                        if cmd in ("done", "q", "quit", "exit"):
                            break
                        print("  Capturing AT-SPI tree...", end="", flush=True)
                        state_tree = dump_at_spi_tree(args.app)
                        print(" done")
                        try:
                            label = input("  State name: ").strip()
                        except (EOFError, KeyboardInterrupt):
                            print()
                            break
                        if not label:
                            label = f"unnamed_{state_index}"
                        safe_label = "".join(c if c.isalnum() or c in "_-" else "_" for c in label)
                        state_path = states_dir / f"{state_index:02d}_{safe_label}.yaml"
                        write_runtime_dump(
                            state_tree,
                            str(state_path),
                            app_name=args.app,
                            state_label=label,
                        )
                        print(f"  -> {state_path}")
                        state_index += 1
                else:
                    states_dir = dump_dir / "states"
                    states_dir.mkdir(parents=True, exist_ok=True)
                    recorder = ATRecorderManager(
                        app_name=args.app,
                        states_dir=states_dir,
                        on_capture=lambda _label, _idx, _path: None,
                    )
                    print(f"\n[2/3] Recording states via GUI widget...")
                    recorder.start()
            except Exception as e:
                print(f"  Recording error: {e}")
                do_record = False
        else:
            print("\n[2/3] Recording skipped (--no-record)")

        if scan_thread is not None:
            scan_thread.join()
            scan_pool.close()
            scan_pool.join()
            print(file=sys.stderr, flush=True)
            scan_result = scan_holder[0]
            scan_error = scan_holder[1]
            if scan_error:
                print(f"  Scan error: {scan_error}", file=sys.stderr, flush=True)

        if args.src and scan_result:
            stats = scan_result.stats
            n_ok = sum(
                1 for c in scan_result.classes if c.get("object_names") or c.get("accessible_names")
            )
            n_gaps = len(scan_result.classes) - n_ok
            msg = f"  Scan done: {len(scan_result.classes)} UI classes in {stats['total_files']} files"
            if stats["failed_files"]:
                msg += f" ({stats['failed_files']} failed)"
            print(msg, file=sys.stderr, flush=True)
            print(f"  -> {ok_path} ({n_ok} with names)")
            if n_gaps > 0:
                print(f"  -> {gaps_path} ({n_gaps} missing names)")
        elif args.src and not scan_result:
            print("  Scan failed — no static data merged")
        elif not args.src:
            print("\n  No --src provided, skipping source scan")

        print(f"\n[3/3] Merging and filtering...")
        static_classes = scan_result.classes if scan_result else []

        from src.at.scanner.merger import dedup_runtime_tree

        runtime_tree = dedup_runtime_tree(runtime_tree)

        states_dir = dump_dir / "states"
        state_snapshots = load_state_snapshots(str(states_dir))
        if state_snapshots:
            print(f"  Merging {len(state_snapshots)} state snapshots...")
            runtime_tree = merge_state_snapshots(runtime_tree, state_snapshots)

        merged = merge_trees(runtime_tree, static_classes)
        final_path = output / "at-tree.yaml"
        write_at_tree_yaml(merged, str(final_path), app_name=args.app)
        print(f"  -> {final_path}")

        gaps_path = output / "element_gaps.yaml"
        write_element_gaps(merged, str(gaps_path), app_name=args.app)
        print(f"  -> {gaps_path}")

    except ImportError as e:
        _not_implemented(f"dump ({e})")
    except Exception as e:
        print(f"Error: {e}")


def cmd_parse(args):
    try:
        from youqu.src.at.generator.case_parser import parse_to_cases

        parse_to_cases(
            input_path=args.input,
            output_path=args.output,
            at_tree_path=getattr(args, "at_tree", ""),
        )
    except ImportError:
        _not_implemented("parse")


def cmd_tree_info(args):
    try:
        from youqu.src.at.generator.case_parser import compact_at_tree_to_file

        fmt = getattr(args, "format", "yaml")
        compact_at_tree_to_file(
            at_tree_path=args.at_tree,
            output_path=args.output,
            fmt=fmt,
        )
    except ImportError:
        _not_implemented("tree-info")


def cmd_map(args):
    try:
        from youqu.src.at.generator.mapper import map_elements

        map_elements(at_tree_path=args.at_tree, cases_path=args.cases, output_path=args.output)
    except ImportError:
        _not_implemented("map")


def cmd_generate(args):
    try:
        from youqu.src.at.generator.yaml_generator import generate_yaml

        generate_yaml(
            cases_path=args.cases,
            mappings_path=getattr(args, "mappings", ""),
            output_dir=args.output,
            app_name=getattr(args, "app", ""),
            at_tree_path=getattr(args, "at_tree", ""),
            assert_gate=getattr(args, "assert_gate", True),
        )
    except ImportError:
        _not_implemented("generate")


def cmd_run(args):
    try:
        from youqu.src.at.executor.runner import run_tests

        run_tests(
            test_dir=args.testdir,
            suite=args.suite,
            keyword=args.k,
            spec_ids=args.spec_ids,
            tags=args.tags,
            skip_env_check=args.skip_env_check,
        )
    except ImportError:
        _not_implemented("run")


def cmd_validate(args):
    try:
        from youqu.src.at.validator.gates import (
            run_all_gates,
            validate_gate1,
            validate_gate2,
            validate_gate3,
            validate_gate4,
            validate_gate5,
        )

        gate = getattr(args, "gate", "all")
        results: list[dict] = []

        if gate == "all":
            results = run_all_gates(
                at_tree_annotated_path=getattr(args, "at_tree_annotated", ""),
                suite_cases_path=getattr(args, "suite_cases", ""),
                cases_mapped_path=getattr(args, "cases_mapped", ""),
                generate_output_dir=getattr(args, "generate_output", ""),
                element_gaps_path=getattr(args, "element_gaps", ""),
            )
        else:
            gate_num = int(gate)
            at_tree = getattr(args, "at_tree_annotated", "")
            if gate_num == 1:
                results.append(validate_gate1(at_tree, getattr(args, "element_gaps", "")))
            elif gate_num == 2:
                results.append(validate_gate2(getattr(args, "suite_cases", ""), at_tree))
            elif gate_num == 3:
                results.append(validate_gate3(getattr(args, "cases_mapped", ""), at_tree))
            elif gate_num == 4:
                results.append(validate_gate4(getattr(args, "generate_output", ""), at_tree))
            elif gate_num == 5:
                results.append(validate_gate5(getattr(args, "cases_mapped", ""), at_tree))

        all_passed = True
        for r in results:
            status = "PASS" if r["passed"] else "FAIL"
            print(f"Gate {r['gate']}: {r['name']} — {status}")
            for err in r.get("errors", []):
                print(f"  ERROR: {err}")
                all_passed = False
            for warn in r.get("warnings", []):
                print(f"  WARN:  {warn}")

        if all_passed:
            print("\nAll gates passed.")
        else:
            print("\nSome gates failed. See errors above.")
            import sys

            sys.exit(1)

    except ImportError:
        _not_implemented("validate")
