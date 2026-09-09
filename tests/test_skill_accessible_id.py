# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only
"""Tests for at-spi-coverage skill scripts: accessible_id numerator/denominator.

Covers the objectName → accessible_id support (df20e47) that made
QAction/DAction-located controls count in coverage:
- coverage_atcase._iter_suite_refs collects selector.accessible_id
- coverage_atcase._load_scan_total reads at_locatable_by_aid_total
- coverage_atcase._collect_elements_yaml collects accessible_id entries
- cover.py (at-case-generator) _walk_refs collects accessible_id refs
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

_SKILLS = Path(__file__).resolve().parent.parent / "skills"


def _load_module(name: str, rel_path: str) -> types.ModuleType:
    path = _SKILLS / rel_path
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    # ensure parent package names resolve for relative imports in scan_gaps
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def cov_atcase():
    return _load_module("cov_atcase", "at-spi-coverage/scripts/coverage_atcase.py")


@pytest.fixture(scope="module")
def cover():
    return _load_module("acg_cover", "at-case-generator/scripts/cover.py")


@pytest.fixture(scope="module")
def element_manifest():
    return _load_module("acg_manifest", "at-case-generator/scripts/element_manifest.py")


# ---- coverage_atcase: selector collection (numerator) ----

def test_iter_suite_refs_collects_name_and_accessible_id(cov_atcase):
    suite = {
        "setup": [
            {"action": "element_action", "selector": {"accessible_id": "UnixAction"}, "do": "click"},
        ],
        "suites": [
            {
                "id": "c1",
                "steps": [
                    {"action": "assert_element", "selector": {"name": "TextEditor"}},
                    {"action": "dtk_main_menu", "items": ["GIF"]},
                ],
            }
        ],
    }
    selectors: set[str] = set()
    items: set[str] = set()
    cov_atcase._iter_suite_refs(suite, selectors, items)
    assert selectors == {"UnixAction", "TextEditor"}
    assert items == {"GIF"}
def test_iter_suite_refs_dtk_dropdown_menu_items_persistent(cov_atcase):
    """dtk_dropdown_menu 的 items 是 objectName 后缀 (持久) → 计入 selectors,
    不是瞬态 items (与 dtk_main_menu/dtk_context_menu 区分)。"""
    suite = {
        "suites": [
            {
                "id": "c1",
                "steps": [
                    {"action": "dtk_dropdown_menu", "selector": {"accessible_id": "PToolButton"}, "items": ["WindowsAction"]},
                    {"action": "dtk_context_menu", "selector": {"name": "tab_title"}, "items": ["关闭标签页"]},
                ],
            }
        ],
    }
    selectors: set[str] = set()
    items: set[str] = set()
    cov_atcase._iter_suite_refs(suite, selectors, items)
    assert selectors == {"PToolButton", "WindowsAction", "tab_title"}
    assert items == {"关闭标签页"}


def test_iter_refs_by_type_counts_dropdown_items_as_aid(cov_atcase):
    """dtk_dropdown_menu 的 items 归 aid_refs (objectName 后缀)。"""
    suite = {
        "steps": [
            {"action": "dtk_dropdown_menu", "items": ["WindowsAction"]},
            {"action": "element_action", "selector": {"name": "SaveButton"}},
        ]
    }
    name_refs: set[str] = set()
    aid_refs: set[str] = set()
    cov_atcase._iter_refs_by_type(suite, name_refs, aid_refs)
    assert name_refs == {"SaveButton"}
    assert aid_refs == {"WindowsAction"}

def test_collect_elements_yaml_collects_accessible_id(cov_atcase, tmp_path):
    el = tmp_path / "elements.yaml"
    el.write_text(
        "elements:\n"
        "  UnixAction: {accessible_id: UnixAction, role: push button}\n"
        "  SaveButton: {name: SaveButton, role: push button}\n",
        encoding="utf-8",
    )
    names = cov_atcase._collect_elements_yaml(el)
    assert names == {"UnixAction", "SaveButton"}


def test_load_scan_total_prefers_selected_key(cov_atcase, tmp_path):
    scan = tmp_path / "scan"
    scan.mkdir()
    (scan / "pre_report.json").write_text(
        json.dumps(
            {
                "summary": {
                    "total_widgets": 12,
                    "at_locatable_total": 10,
                    "at_locatable_by_aid_total": 7,
                }
            }
        ),
        encoding="utf-8",
    )
    total, src = cov_atcase._load_scan_total(scan, key="at_locatable_total")
    assert (total, src) == (10, "pre_report.json")
    total, _ = cov_atcase._load_scan_total(scan, key="at_locatable_by_aid_total")
    assert total == 7
    # fallback to total_widgets when key missing
    (scan / "pre_report.json").write_text(
        json.dumps({"summary": {"total_widgets": 5}}), encoding="utf-8"
    )
    total, _ = cov_atcase._load_scan_total(scan, key="at_locatable_by_aid_total")
    assert total == 5


# ---- cover.py gate: accessible_id refs satisfy 100% ----

def test_cover_walk_refs_collects_accessible_id(cover):
    refs: set[str] = set()
    suite = {"suites": [{"steps": [{"action": "element_action", "selector": {"accessible_id": "WindowsAction"}}]}]}
    cover._walk_refs(suite, refs)
    assert refs == {"WindowsAction"}
def test_cover_walk_refs_collects_dtk_dropdown_menu_items(cover):
    """dtk_dropdown_menu 的 items (objectName 后缀) 计入覆盖分子。"""
    refs: set[str] = set()
    suite = {
        "suites": [
            {
                "steps": [
                    {"action": "dtk_dropdown_menu", "selector": {"accessible_id": "PToolButton"}, "items": ["WindowsAction"]},
                ]
            }
        ]
    }
    cover._walk_refs(suite, refs)
    assert refs == {"PToolButton", "WindowsAction"}

def test_cover_gate_passes_with_accessible_id(cover, tmp_path):
    em = tmp_path / "element-map.yaml"
    em.write_text(
        "elements:\n"
        "  - ui_name: 保存按钮\n    id_name: SaveButton\n    role: push button\n"
        "  - ui_name: 行尾格式\n    object_name: WindowsAction\n    role: push button\n",
        encoding="utf-8",
    )
    testdir = tmp_path / "yaml"
    testdir.mkdir()
    (testdir / "m.suite.yaml").write_text(
        "suites:\n"
        "  - id: c1\n"
        "    steps:\n"
        "      - action: element_action\n"
        "        selector: {accessible_id: WindowsAction}\n"
        "        do: click\n"
        "      - action: assert_element\n"
        "        selector: {name: SaveButton}\n",
        encoding="utf-8",
    )

    # cover.main parses argv; call the internals instead
    elements, _ = cover._collect_element_map(em)
    refs = {r for r in cover._collect_suite_refs(testdir) if not cover._is_noise(r)}
    denominator = set(elements)
    covered = {n for n in denominator if n in refs}
    assert covered == {"SaveButton", "WindowsAction"}


def test_cover_keeps_menu_items_excludes_context_roles(cover, tmp_path):
    """menu item with objectName stays in denominator (intelligent routing);
    bare menu/popup roles (no objectName, right-click QMenu) are transient.
    No menu_type field needed — object_name presence decides."""
    em = tmp_path / "element-map.yaml"
    em.write_text(
        "elements:\n"
        "  - ui_name: 行尾格式\n    object_name: WindowsAction\n    role: menu item\n"
        "  - ui_name: 关闭标签\n    id_name: CloseTab\n    role: menu\n"
        "  - ui_name: 主菜单\n    id_name: Menu_2\n    role: menu\n",
        encoding="utf-8",
    )
    elements, transient = cover._collect_element_map(em)
    assert set(elements) == {"WindowsAction"}
    assert [t["name"] for t in transient] == ["CloseTab", "Menu_2"]


def test_element_manifest_marks_menu_item_locator(element_manifest, tmp_path):
    em = tmp_path / "element-map.yaml"
    em.write_text(
        "elements:\n"
        "  - ui_name: 行尾格式\n    object_name: WindowsAction\n    role: menu item\n"
        "  - ui_name: 保存按钮\n    id_name: SaveButton\n    role: push button\n",
        encoding="utf-8",
    )
    out = tmp_path / "manifest.yaml"
    import sys
    import yaml

    old_argv = sys.argv
    sys.argv = ["element_manifest.py", "--element-map", str(em), "--output", str(out)]
    try:
        rc = element_manifest.main()
    finally:
        sys.argv = old_argv
    assert rc == 0
    data = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert data["scan_total"] == 2
    # 有 object_name → accessible_id 定位
    assert data["elements"]["WindowsAction"]["locator"] == "accessible_id"
    # 仅 id_name → name 定位
    assert data["elements"]["SaveButton"]["locator"] == "name"


def test_element_manifest_menu_item_without_object_name_transient(element_manifest, tmp_path):
    """无 object_name 的 menu/menu item → transient（与 cover.py 判定一致）。"""
    em = tmp_path / "element-map.yaml"
    em.write_text(
        "elements:\n"
        "  - ui_name: 关闭标签\n    id_name: CloseTab\n    role: menu\n",
        encoding="utf-8",
    )
    out = tmp_path / "manifest.yaml"
    import sys
    import yaml

    old_argv = sys.argv
    sys.argv = ["element_manifest.py", "--element-map", str(em), "--output", str(out)]
    try:
        rc = element_manifest.main()
    finally:
        sys.argv = old_argv
    assert rc == 0
    data = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert data["elements"] == {}
    assert len(data["transient_items"]) == 1
    assert data["transient_items"][0]["name"] == "CloseTab"

def test_element_manifest_object_name_preferred_over_id_name(element_manifest, tmp_path):
    """两者都有时以 object_name 为键、locator=accessible_id（优先）。"""
    em = tmp_path / "element-map.yaml"
    em.write_text(
        "elements:\n"
        "  - ui_name: 格式按钮\n    id_name: FormatButton\n    object_name: FormatAct\n"
        "    role: push button\n",
        encoding="utf-8",
    )
    out = tmp_path / "manifest.yaml"
    import sys
    import yaml

    old_argv = sys.argv
    sys.argv = ["element_manifest.py", "--element-map", str(em), "--output", str(out)]
    try:
        rc = element_manifest.main()
    finally:
        sys.argv = old_argv
    assert rc == 0
    data = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert "FormatAct" in data["elements"]
    assert "FormatButton" not in data["elements"]
    assert data["elements"]["FormatAct"]["locator"] == "accessible_id"


def test_element_manifest_both_empty_goes_unresolved(element_manifest, tmp_path):
    """id_name 与 object_name 均空/TBD → unresolved，不进分母。"""
    em = tmp_path / "element-map.yaml"
    em.write_text(
        "elements:\n"
        "  - ui_name: 待补名按钮\n    id_name: TBD\n    object_name: ''\n"
        "    role: push button\n",
        encoding="utf-8",
    )
    out = tmp_path / "manifest.yaml"
    import sys
    import yaml

    old_argv = sys.argv
    sys.argv = ["element_manifest.py", "--element-map", str(em), "--output", str(out)]
    try:
        rc = element_manifest.main()
    finally:
        sys.argv = old_argv
    assert rc == 0
    data = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert data["elements"] == {}
    assert len(data["unresolved"]) == 1
