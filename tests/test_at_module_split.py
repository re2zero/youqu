# SPDX-FileCopyrightText: 2026 Uniontech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only

"""Tests for module-split pipeline: splitter, tree_subset, manifest."""

from __future__ import annotations

import sys
import types
from pathlib import Path

import yaml

_src_root = Path(__file__).resolve().parent.parent / "src"
if str(_src_root) not in sys.path:
    sys.path.insert(0, str(_src_root))
stub = sys.modules.get("src")
if stub is not None and getattr(stub, "__spec__", None) is None:
    sys.modules["src"] = types.ModuleType("src")
    sys.modules["src"].__path__ = [str(_src_root)]
    sys.modules["src"].__package__ = "src"
    sys.modules["src"].__file__ = str(_src_root / "__init__.py")

from src.at.generator.manifest import (
    build_manifest,
    load_manifest,
    make_module_entry,
    update_module_status,
    write_manifest,
)
from src.at.generator.splitter import (
    _extract_module_name,
    _slugify,
    split_cases,
)
from src.at.generator.tree_subset import extract_subtree


# ---- manifest tests ----


def test_make_module_entry_defaults():
    entry = make_module_entry("find", 7)
    assert entry["slug"] == "find"
    assert entry["status"] == "pending"
    assert entry["cases"] == 7
    assert entry["mapped"] == 0
    assert entry["selector_coverage"] == 0.0
    assert entry["has_manual"] is False


def test_build_manifest_stats():
    modules = [
        make_module_entry("find", 7),
        make_module_entry("settings", 5),
    ]
    manifest = build_manifest(app="deepin-terminal", source="test.xlsx", modules=modules)
    assert manifest["app"] == "deepin-terminal"
    assert manifest["stats"]["total_cases"] == 12
    assert manifest["stats"]["total_modules"] == 2
    assert manifest["stats"]["mapped_cases"] == 0


def test_write_and_load_manifest(tmp_path):
    manifest = build_manifest(
        app="test",
        source="t.xlsx",
        modules=[make_module_entry("a", 3)],
    )
    path = write_manifest(manifest, str(tmp_path))
    assert path.exists()
    loaded = load_manifest(str(path))
    assert loaded["app"] == "test"
    assert loaded["modules"][0]["slug"] == "a"


def test_update_module_status_recomputes_stats(tmp_path):
    manifest = build_manifest(
        app="t",
        source="s",
        modules=[make_module_entry("a", 5), make_module_entry("b", 3)],
    )
    update_module_status(manifest, "a", "mapped", mapped=5, selector_coverage=0.8)
    assert manifest["modules"][0]["status"] == "mapped"
    assert manifest["modules"][0]["mapped"] == 5
    assert manifest["stats"]["mapped_cases"] == 5
    assert manifest["stats"]["avg_coverage"] == 0.8


# ---- splitter helper tests ----


def test_slugify_chinese():
    assert _slugify("查找") == "查找"
    assert _slugify("设置界面高级设置(#116119)") == "设置界面高级设置116119"
    assert _slugify("") == "misc"


def test_extract_module_name_from_path():
    assert _extract_module_name("/V25/终端/104X/查找(#116101)") == "查找"
    assert _extract_module_name("") == "misc"
    assert _extract_module_name("/V25/终端/设置界面") == "设置界面"


# ---- tree_subset tests ----


def test_extract_subtree_filters_nodes(tmp_path):
    at_tree = {
        "version": "1.0",
        "tree": [
            {
                "id": "n0",
                "role": "frame",
                "name": "",
                "comment": "主窗口",
                "children": [
                    {
                        "id": "n1",
                        "role": "button",
                        "name": "SearchButton",
                        "comment": "查找按钮",
                    },
                    {
                        "id": "n2",
                        "role": "label",
                        "name": "status",
                        "comment": "状态栏",
                    },
                ],
            }
        ],
    }
    tree_path = tmp_path / "at-tree.yaml"
    tree_path.write_text(yaml.dump(at_tree, allow_unicode=True), encoding="utf-8")

    output_path = tmp_path / "subtree.yaml"
    stats = extract_subtree(
        str(tree_path),
        ["查找", "搜索"],
        str(output_path),
    )
    assert stats["total_nodes"] == 3
    assert stats["subtree_nodes"] >= 2  # n1 + parent n0
    assert stats["coverage"] > 0.0

    subtree = yaml.safe_load(output_path.read_text(encoding="utf-8"))
    ids = []

    def _collect(nodes):
        for n in nodes:
            ids.append(n.get("id"))
            _collect(n.get("children", []))

    _collect(subtree.get("tree", []))
    assert "n1" in ids  # matched
    assert "n0" in ids  # ancestor
    assert "n2" not in ids  # filtered out


# ---- split_cases integration ----


def _write_cases_raw(path, cases):
    data = {
        "metadata": {"source": "test.xlsx"},
        "cases": cases,
    }
    path.write_text(yaml.dump(data, allow_unicode=True), encoding="utf-8")


def _write_at_tree(path):
    tree = {
        "version": "1.0",
        "tree": [
            {
                "id": "n0",
                "role": "frame",
                "name": "",
                "comment": "主窗口",
                "children": [
                    {"id": "n1", "role": "button", "name": "SearchBtn", "comment": "查找"},
                    {"id": "n2", "role": "entry", "name": "Input", "comment": "输入框"},
                ],
            }
        ],
    }
    path.write_text(yaml.dump(tree, allow_unicode=True), encoding="utf-8")


def test_split_cases_creates_modules(tmp_path):
    cases_path = tmp_path / "cases_raw.yaml"
    at_tree_path = tmp_path / "at-tree.yaml"
    output_dir = tmp_path / "output"

    _write_cases_raw(cases_path, [
        {
            "id": "case_001",
            "name": "查找显示",
            "module": "/V25/终端/查找(#100)",
            "description": "查找显示",
            "status": "active",
            "steps": [
                {"step_type": "action", "description": "点击查找按钮"},
                {"step_type": "assert", "description": "查找框显示"},
            ],
        },
        {
            "id": "case_002",
            "name": "设置",
            "module": "/V25/终端/设置",
            "description": "设置",
            "status": "active",
            "steps": [
                {"step_type": "action", "description": "打开设置"},
            ],
        },
    ])
    _write_at_tree(at_tree_path)

    result = split_cases(
        cases_path=str(cases_path),
        at_tree_path=str(at_tree_path),
        output_dir=str(output_dir),
        app_name="test-app",
    )

    assert result["modules"] == 2
    assert result["total_cases"] == 2
    assert (output_dir / "manifest.yaml").exists()
    assert (output_dir / "modules" / "查找" / "cases.md").exists()
    assert (output_dir / "modules" / "查找" / "at-tree-subtree.yaml").exists()
    assert (output_dir / "modules" / "设置" / "cases.md").exists()

    manifest = yaml.safe_load((output_dir / "manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["app"] == "test-app"
    assert manifest["stats"]["total_cases"] == 2
    assert len(manifest["modules"]) == 2


def test_split_cases_misc_for_empty_module(tmp_path):
    cases_path = tmp_path / "cases_raw.yaml"
    at_tree_path = tmp_path / "at-tree.yaml"
    output_dir = tmp_path / "out"

    _write_cases_raw(cases_path, [
        {
            "id": "c1",
            "name": "test",
            "module": "",
            "description": "test",
            "status": "active",
            "steps": [{"step_type": "action", "description": "do something"}],
        },
    ])
    _write_at_tree(at_tree_path)

    result = split_cases(
        cases_path=str(cases_path),
        at_tree_path=str(at_tree_path),
        output_dir=str(output_dir),
    )
    assert result["modules"] == 1
    assert (output_dir / "modules" / "misc" / "cases.md").exists()
