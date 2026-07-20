# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only


def _not_implemented(cmd: str):
    print(f"youqu at {cmd}: not implemented yet")


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
