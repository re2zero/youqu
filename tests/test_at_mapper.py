# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only
"""Tests for the deprecated mapper module."""

import sys
import types
from unittest.mock import MagicMock

_src_mock = sys.modules.get("src")
if not _src_mock or not getattr(_src_mock, "__spec__", None):
    sys.modules["src"] = types.ModuleType("src")
    sys.modules["src"].__path__ = ["/home/zero/work/research/youqu/src"]
    sys.modules["src"].__package__ = "src"
    sys.modules["src"].__file__ = "/home/zero/work/research/youqu/src/__init__.py"
if not isinstance(sys.modules.get("pyatspi"), types.ModuleType):
    sys.modules["pyatspi"] = MagicMock()

import pytest


def test_map_elements_deprecated(tmp_path, capsys):
    """map_elements should emit deprecation warning and write empty output."""
    from src.at.generator.mapper import map_elements

    tree_file = tmp_path / "tree.yaml"
    tree_file.write_text("tree: []\n", encoding="utf-8")
    cases_file = tmp_path / "cases.yaml"
    cases_file.write_text("cases: []\n", encoding="utf-8")
    out_file = tmp_path / "mappings.yaml"

    map_elements(str(tree_file), str(cases_file), str(out_file))

    captured = capsys.readouterr()
    assert "deprecated" in captured.out.lower()
    assert out_file.exists()
