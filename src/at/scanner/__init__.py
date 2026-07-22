# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only

# Modules that do NOT require pyatspi — always importable (headless-safe)
from src.at.scanner.clang_scanner import ScanResult, scan_source_dir
from src.at.scanner.merger import (
    append_scan_entry,
    dedup_runtime_tree,
    extract_transient,
    filter_noise,
    generate_name_gaps_report,
    layered_merge,
    load_record_session,
    load_state_snapshots,
    merge_persistent,
    merge_state_snapshots,
    merge_trees,
    write_at_tree_yaml,
    write_runtime_dump,
    write_static_dump,
)

# Modules that require pyatspi — optional, headless environments skip these
try:
    from src.at.scanner.atspi_dumper import dump_at_spi_tree
    from src.at.scanner.event_listener import (
        DegradedListener,
        InputEvent,
        InputEventListener,
        X11RecordListener,
        WaylandEvdevListener,
        create_input_listener,
        is_modifier,
        is_printable_char,
        keysym_to_name,
    )
    from src.at.scanner.hit_test import ExtentsCache, hit_test
    from src.at.scanner.recorder import RecordSession, Segment
except ImportError:
    dump_at_spi_tree = None  # type: ignore[assignment,misc]
    ExtentsCache = None  # type: ignore[assignment,misc]
    hit_test = None  # type: ignore[assignment,misc]
    RecordSession = None  # type: ignore[assignment,misc]
    Segment = None  # type: ignore[assignment,misc]
    InputEvent = None  # type: ignore[assignment,misc]
    InputEventListener = None  # type: ignore[assignment,misc]
    X11RecordListener = None  # type: ignore[assignment,misc]
    WaylandEvdevListener = None  # type: ignore[assignment,misc]
    DegradedListener = None  # type: ignore[assignment,misc]
    create_input_listener = None  # type: ignore[assignment,misc]
    keysym_to_name = None  # type: ignore[assignment,misc]
    is_modifier = None  # type: ignore[assignment,misc]
    is_printable_char = None  # type: ignore[assignment,misc]

__all__ = [
    "append_scan_entry",
    "dedup_runtime_tree",
    "dump_at_spi_tree",
    "scan_source_dir",
    "ScanResult",
    "merge_trees",
    "merge_state_snapshots",
    "load_state_snapshots",
    "write_at_tree_yaml",
    "filter_noise",
    "write_runtime_dump",
    "write_static_dump",
    "generate_name_gaps_report",
    "hit_test",
    "ExtentsCache",
    "InputEvent",
    "InputEventListener",
    "X11RecordListener",
    "WaylandEvdevListener",
    "DegradedListener",
    "create_input_listener",
    "keysym_to_name",
    "is_modifier",
    "is_printable_char",
    "RecordSession",
    "Segment",
    "layered_merge",
    "load_record_session",
    "merge_persistent",
    "extract_transient",
]
