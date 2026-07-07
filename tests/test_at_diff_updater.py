# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only

import sys
import types

import pytest
from unittest.mock import MagicMock

_src_mock = sys.modules.get("src")
if not _src_mock or not getattr(_src_mock, "__spec__", None):
    sys.modules["src"] = types.ModuleType("src")
    sys.modules["src"].__path__ = ["/home/zero/work/research/youqu/src"]
    sys.modules["src"].__package__ = "src"
    sys.modules["src"].__file__ = "/home/zero/work/research/youqu/src/__init__.py"
if not isinstance(sys.modules.get("pyatspi"), types.ModuleType):
    sys.modules["pyatspi"] = MagicMock()

OLD_TREE = {
    "nodes": [
        {"id": "n1", "name": "Play", "role": "push button"},
        {"id": "n2", "name": "Stop", "role": "push button"},
        {"id": "n3", "name": "Menu", "role": "menu"},
    ]
}

NEW_TREE_DELETED = {
    "nodes": [
        {"id": "n1", "name": "Play", "role": "push button"},
    ]
}

NEW_TREE_CHANGED = {
    "nodes": [
        {"id": "n1", "name": "Play", "role": "push button"},
        {"id": "n2", "name": "Stop2", "role": "toggle button"},
        {"id": "n3", "name": "Menu", "role": "menu"},
    ]
}

NEW_TREE_ADDED = {
    "nodes": [
        {"id": "n1", "name": "Play", "role": "push button"},
        {"id": "n2", "name": "Stop", "role": "push button"},
        {"id": "n3", "name": "Menu", "role": "menu"},
        {"id": "n4", "name": "NewBtn", "role": "push button"},
    ]
}

EXISTING_MAPPINGS = {
    "metadata": {"generated_at": "2026-01-01", "at_tree_source": "old"},
    "mappings": [
        {
            "case_id": "s1",
            "step_index": 0,
            "description": "click play",
            "step_type": "action",
            "element_ref": "n1",
            "selector": {"name": "Play", "role": "push button"},
            "status": "mapped",
        },
        {
            "case_id": "s1",
            "step_index": 1,
            "description": "click stop",
            "step_type": "action",
            "element_ref": "n2",
            "selector": {"name": "Stop", "role": "push button"},
            "status": "mapped",
        },
    ],
}


def _write_temp(data: dict, path: str):
    import yaml

    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True)


def test_diff_update_marks_deleted():
    from src.at.generator.diff_updater import diff_update

    _write_temp(OLD_TREE, "/tmp/test_at_diff_old_tree.yaml")
    _write_temp(NEW_TREE_DELETED, "/tmp/test_at_diff_new_tree.yaml")
    _write_temp(EXISTING_MAPPINGS, "/tmp/test_at_diff_old_mappings.yaml")

    diff_update(
        "/tmp/test_at_diff_old_tree.yaml",
        "/tmp/test_at_diff_new_tree.yaml",
        "/tmp/test_at_diff_old_mappings.yaml",
        "/tmp/test_at_diff_out.yaml",
    )

    from src.at.parser.models import ElementMappingsDoc
    import yaml

    doc = ElementMappingsDoc.model_validate(yaml.safe_load(open("/tmp/test_at_diff_out.yaml", encoding="utf-8")))
    statuses = {m.element_ref: m.status for m in doc.mappings}
    assert statuses["n1"] == "mapped"
    assert statuses["n2"] == "deprecated"


def test_diff_update_migrates_changed():
    from src.at.generator.diff_updater import diff_update

    _write_temp(OLD_TREE, "/tmp/test_at_diff2_old_tree.yaml")
    _write_temp(NEW_TREE_CHANGED, "/tmp/test_at_diff2_new_tree.yaml")
    _write_temp(EXISTING_MAPPINGS, "/tmp/test_at_diff2_old_mappings.yaml")

    diff_update(
        "/tmp/test_at_diff2_old_tree.yaml",
        "/tmp/test_at_diff2_new_tree.yaml",
        "/tmp/test_at_diff2_old_mappings.yaml",
        "/tmp/test_at_diff2_out.yaml",
    )

    from src.at.parser.models import ElementMappingsDoc
    import yaml

    doc = ElementMappingsDoc.model_validate(yaml.safe_load(open("/tmp/test_at_diff2_out.yaml", encoding="utf-8")))
    n2 = next(m for m in doc.mappings if m.element_ref == "n2")
    assert n2.selector.name == "Stop2"
    assert n2.selector.role == "toggle button"


def test_diff_update_marks_new_unmapped():
    from src.at.generator.diff_updater import diff_update

    new_mappings = {
        "metadata": {"generated_at": "2026-01-01", "at_tree_source": "old"},
        "mappings": [
            {
                "case_id": "s1",
                "step_index": 0,
                "description": "click play",
                "step_type": "action",
                "element_ref": "n4",
                "selector": {"name": "NewBtn", "role": "push button"},
                "status": "mapped",
            },
        ],
    }
    _write_temp(NEW_TREE_DELETED, "/tmp/test_at_diff3_old_tree.yaml")
    _write_temp(NEW_TREE_ADDED, "/tmp/test_at_diff3_new_tree.yaml")
    _write_temp(new_mappings, "/tmp/test_at_diff3_old_mappings.yaml")

    diff_update(
        "/tmp/test_at_diff3_old_tree.yaml",
        "/tmp/test_at_diff3_new_tree.yaml",
        "/tmp/test_at_diff3_old_mappings.yaml",
        "/tmp/test_at_diff3_out.yaml",
    )

    from src.at.parser.models import ElementMappingsDoc
    import yaml

    doc = ElementMappingsDoc.model_validate(yaml.safe_load(open("/tmp/test_at_diff3_out.yaml", encoding="utf-8")))
    unmapped = [m for m in doc.mappings if m.status == "unmapped"]
    assert len(unmapped) == 1
    assert "n4" in unmapped[0].element_ref


def test_diff_update_unchanged_preserved():
    from src.at.generator.diff_updater import diff_update

    _write_temp(OLD_TREE, "/tmp/test_at_diff4_old_tree.yaml")
    _write_temp(OLD_TREE, "/tmp/test_at_diff4_new_tree.yaml")
    _write_temp(EXISTING_MAPPINGS, "/tmp/test_at_diff4_old_mappings.yaml")

    diff_update(
        "/tmp/test_at_diff4_old_tree.yaml",
        "/tmp/test_at_diff4_new_tree.yaml",
        "/tmp/test_at_diff4_old_mappings.yaml",
        "/tmp/test_at_diff4_out.yaml",
    )

    from src.at.parser.models import ElementMappingsDoc
    import yaml

    doc = ElementMappingsDoc.model_validate(yaml.safe_load(open("/tmp/test_at_diff4_out.yaml", encoding="utf-8")))
    assert all(m.status == "mapped" for m in doc.mappings)
    assert len(doc.mappings) == 2
