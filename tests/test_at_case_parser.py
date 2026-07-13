# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

_src_root = Path(__file__).resolve().parent.parent / "src"
if str(_src_root) not in sys.path:
    sys.path.insert(0, str(_src_root))

stub = sys.modules.get("src")
if stub is not None and getattr(stub, "__spec__", None) is None:
    sys.modules["src"] = types.ModuleType("src")
    sys.modules["src"].__path__ = [str(_src_root)]
    sys.modules["src"].__package__ = "src"
    sys.modules["src"].__file__ = str(_src_root / "__init__.py")

if "pyatspi" not in sys.modules:
    sys.modules["pyatspi"] = MagicMock()

import pytest


def test_find_column_exact_match():
    from src.at.generator.case_parser import find_column, COLUMN_ALIASES

    record = {"用例标题": "播放音乐", "所属模块": "播放"}
    assert find_column(record, COLUMN_ALIASES["title"]) == "播放音乐"
    assert find_column(record, COLUMN_ALIASES["module"]) == "播放"


def test_find_column_alias_match():
    from src.at.generator.case_parser import find_column, COLUMN_ALIASES

    record = {"标题": "暂停播放", "模块": "控制"}
    assert find_column(record, COLUMN_ALIASES["title"]) == "暂停播放"


def test_find_column_fuzzy_match():
    from src.at.generator.case_parser import find_column, COLUMN_ALIASES

    record = {"测试步骤": "1.点击播放"}
    assert find_column(record, COLUMN_ALIASES["steps"]) == "1.点击播放"


def test_find_column_empty():
    from src.at.generator.case_parser import find_column, COLUMN_ALIASES

    record = {"无关列": "xxx"}
    assert find_column(record, COLUMN_ALIASES["title"]) == ""


def test_read_xlsx():
    from src.at.generator.case_parser import read_xlsx

    mock_wb = MagicMock()
    mock_ws = MagicMock()
    mock_ws.iter_rows.return_value = [
        ("用例标题", "所属模块", "步骤"),
        ("播放音乐", "播放", "1.点击播放按钮"),
        ("暂停播放", "播放", "1.点击暂停"),
    ]
    mock_wb.active = mock_ws

    with patch("openpyxl.load_workbook", return_value=mock_wb):
        result = read_xlsx("dummy.xlsx")

    assert len(result) == 2
    assert result[0]["用例标题"] == "播放音乐"
    assert result[1]["步骤"] == "1.点击暂停"


def test_read_xlsx_empty():
    from src.at.generator.case_parser import read_xlsx

    mock_wb = MagicMock()
    mock_ws = MagicMock()
    mock_ws.iter_rows.return_value = []
    mock_wb.active = mock_ws

    with patch("openpyxl.load_workbook", return_value=mock_wb):
        assert read_xlsx("empty.xlsx") == []


def test_read_csv_file(tmp_path):
    from src.at.generator.case_parser import read_csv_file

    csv_file = tmp_path / "test.csv"
    csv_file.write_text(
        "用例标题,所属模块,步骤\n播放音乐,播放,1.点击播放\n",
        encoding="utf-8-sig",
    )
    result = read_csv_file(str(csv_file))
    assert len(result) == 1
    assert result[0]["用例标题"] == "播放音乐"


def test_normalize_cases():
    from src.at.generator.case_parser import normalize_cases

    raw = [
        {"用例标题": "播放音乐", "所属模块": "播放", "操作步骤": "1.点击播放", "source_row": 2},
        {"标题": "暂停", "步骤": "1.暂停", "source_row": 3},
    ]
    cases = normalize_cases(raw)
    assert len(cases) == 2
    assert cases[0]["title"] == "播放音乐"
    assert cases[0]["steps"] == "1.点击播放"
    assert cases[1]["title"] == "暂停"
    assert cases[1]["steps"] == "1.暂停"
    assert cases[1]["id"] == "001"


def test_normalize_cases_fallback_id():
    from src.at.generator.case_parser import normalize_cases

    raw = [{"用例标题": "测试", "所属模块": "模块A"}]
    cases = normalize_cases(raw)
    assert cases[0]["id"] == "000"


def test_compact_at_tree_returns_nodes():
    from src.at.generator.case_parser import _compact_at_tree

    tree_yaml = "tree:\n  - id: n1\n    role: push button\n    name: OK\n    children:\n      - id: n2\n        role: label\n        name: label1\n"
    result = _compact_at_tree(tree_yaml)
    assert "n1" in result
    assert "push button" in result
    assert "OK" in result
    assert "n2" in result
    assert "parent: n1" in result


def test_compact_at_tree_empty():
    from src.at.generator.case_parser import _compact_at_tree

    assert _compact_at_tree("") == ""
    assert _compact_at_tree("not yaml: [") == "not yaml: ["


def test_compact_at_tree_to_file(tmp_path):
    from src.at.generator.case_parser import compact_at_tree_to_file

    tree_file = tmp_path / "at-tree.yaml"
    tree_file.write_text("tree:\n  - id: n1\n    role: push button\n    name: OK\n", encoding="utf-8")
    out_file = tmp_path / "tree-info.txt"
    compact_at_tree_to_file(str(tree_file), str(out_file))
    content = out_file.read_text(encoding="utf-8")
    assert "n1" in content
    assert "OK" in content


def test_parse_to_cases_format_only(tmp_path):
    from src.at.generator.case_parser import parse_to_cases

    csv_file = tmp_path / "input.csv"
    csv_file.write_text(
        "用例标题,所属模块,操作步骤,预期结果\n"
        "播放音乐,播放,1.点击播放按钮,音乐开始播放\n",
        encoding="utf-8-sig",
    )

    output_file = tmp_path / "cases.yaml"
    parse_to_cases(
        input_path=str(csv_file),
        output_path=str(output_file),
    )

    assert output_file.exists()
    content = output_file.read_text(encoding="utf-8")
    assert "播放音乐" in content
    assert "点击播放按钮" in content


def test_parse_to_cases_at_tree_deprecated_warning(tmp_path, capsys):
    from src.at.generator.case_parser import parse_to_cases

    csv_file = tmp_path / "input.csv"
    csv_file.write_text(
        "用例标题,所属模块,操作步骤\n测试,模块,1.步骤\n",
        encoding="utf-8-sig",
    )
    output_file = tmp_path / "cases.yaml"
    parse_to_cases(
        input_path=str(csv_file),
        output_path=str(output_file),
        at_tree_path="fake-tree.yaml",
    )
    captured = capsys.readouterr()
    assert "deprecated" in captured.out.lower()


def test_guess_step_type_action_no_keywords():
    from src.at.generator.case_parser import _guess_step_type
    from src.at.parser.models import StepType

    assert _guess_step_type("点击播放按钮") == StepType.action
    assert _guess_step_type("1.输入文字hello") == StepType.action
    assert _guess_step_type("") == StepType.action


def test_guess_step_type_assert_with_keywords():
    from src.at.generator.case_parser import _guess_step_type
    from src.at.parser.models import StepType

    assert _guess_step_type("检查搜索结果") == StepType.assert_
    assert _guess_step_type("确认窗口已打开") == StepType.assert_
    assert _guess_step_type("验证文件存在") == StepType.assert_
    assert _guess_step_type("查看列表是否显示") == StepType.assert_
    assert _guess_step_type("是否出现对话框") == StepType.assert_
    assert _guess_step_type("应该显示正确状态") == StepType.assert_


def test_parse_to_cases_expected_column_becomes_assert(tmp_path):
    from src.at.generator.case_parser import parse_to_cases

    csv_file = tmp_path / "input.csv"
    csv_file.write_text(
        "用例标题,所属模块,操作步骤,预期结果\n"
        "播放音乐,播放,1.点击播放按钮,音乐开始播放\n",
        encoding="utf-8-sig",
    )
    output_file = tmp_path / "cases.yaml"
    parse_to_cases(input_path=str(csv_file), output_path=str(output_file))

    import yaml

    data = yaml.safe_load(output_file.read_text(encoding="utf-8"))
    suite = data["suites"][0]
    steps = suite["steps"]
    assert steps[0]["step_type"] == "action"
    assert "点击播放按钮" in steps[0]["description"]
    assert steps[-1]["step_type"] == "assert"
    assert "音乐开始播放" in steps[-1]["description"]


def test_parse_to_cases_keyword_classification_in_steps(tmp_path):
    from src.at.generator.case_parser import parse_to_cases

    csv_file = tmp_path / "input.csv"
    csv_file.write_text(
        "用例标题,所属模块,操作步骤\n"
        "检查状态,测试,1.检查按钮是否可见\n",
        encoding="utf-8-sig",
    )
    output_file = tmp_path / "cases.yaml"
    parse_to_cases(input_path=str(csv_file), output_path=str(output_file))

    import yaml

    data = yaml.safe_load(output_file.read_text(encoding="utf-8"))
    steps = data["suites"][0]["steps"]
    assert steps[0]["step_type"] == "assert"


def test_parse_to_cases_no_expected_column(tmp_path):
    from src.at.generator.case_parser import parse_to_cases

    csv_file = tmp_path / "input.csv"
    csv_file.write_text(
        "用例标题,所属模块,操作步骤\n"
        "测试无预期,测试,1.点击按钮\n",
        encoding="utf-8-sig",
    )
    output_file = tmp_path / "cases.yaml"
    parse_to_cases(input_path=str(csv_file), output_path=str(output_file))

    import yaml

    data = yaml.safe_load(output_file.read_text(encoding="utf-8"))
    steps = data["suites"][0]["steps"]
    assert len(steps) == 1
    assert steps[0]["step_type"] == "action"
