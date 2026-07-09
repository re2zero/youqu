# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only

from src.at.scanner.atspi_dumper import dump_at_spi_tree
from src.at.scanner.clang_scanner import ScanResult, scan_source_dir
from src.at.scanner.merger import (
    append_scan_entry,
    dedup_runtime_tree,
    filter_noise,
    generate_name_gaps_report,
    load_state_snapshots,
    merge_state_snapshots,
    merge_trees,
    write_at_tree_yaml,
    write_runtime_dump,
    write_static_dump,
)

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
]
