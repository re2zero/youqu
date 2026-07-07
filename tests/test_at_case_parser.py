# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

import json
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


def test_build_parse_prompt():
    from src.at.generator.case_parser import build_parse_prompt

    cases = [{"title": "播放音乐", "module": "播放", "steps": "1.点击播放"}]
    prompt = build_parse_prompt(cases, "at-tree context")
    assert "播放音乐" in prompt
    assert "at-tree context" in prompt
    assert "action" in prompt
    assert "element_hint" in prompt


def test_build_parse_prompt_no_context():
    from src.at.generator.case_parser import build_parse_prompt

    cases = [{"title": "测试"}]
    prompt = build_parse_prompt(cases, "")
    assert "（无UI上下文）" in prompt


def test_call_llm_success():
    from src.at.generator.case_parser import call_llm

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": '{"suites": []}'}}]
    }
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.post.return_value = mock_response
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    with patch("httpx.Client", return_value=mock_client):
        result = call_llm("test prompt", {"base_url": "http://localhost:8000/v1", "model": "test", "api_key": "k", "timeout": 10, "max_retries": 1, "retry_delay": 0})
    assert result == '{"suites": []}'


def test_call_llm_empty_response():
    from src.at.generator.case_parser import call_llm

    mock_response = MagicMock()
    mock_response.json.return_value = {"choices": []}
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.post.return_value = mock_response
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    with patch("httpx.Client", return_value=mock_client):
        result = call_llm("prompt", {"base_url": "http://x/v1", "model": "test", "api_key": "k", "timeout": 5, "max_retries": 1, "retry_delay": 0})
    assert result == ""


def test_call_llm_retry_exhausted():
    from src.at.generator.case_parser import call_llm

    mock_client = MagicMock()
    mock_client.post.side_effect = Exception("connection refused")
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    with patch("httpx.Client", return_value=mock_client):
        result = call_llm("prompt", {"base_url": "http://x/v1", "model": "test", "api_key": "k", "timeout": 5, "max_retries": 2, "retry_delay": 0})
    assert result == ""
    assert mock_client.post.call_count == 2


def test_extract_json_plain():
    from src.at.generator.case_parser import _extract_json

    assert _extract_json('{"suites": []}') == {"suites": []}


def test_extract_json_markdown_block():
    from src.at.generator.case_parser import _extract_json

    text = '```json\n{"suites": [{"id": "s1"}]}\n```'
    assert _extract_json(text) == {"suites": [{"id": "s1"}]}


def test_extract_json_invalid():
    from src.at.generator.case_parser import _extract_json

    assert _extract_json("not json") is None
    assert _extract_json("") is None


def test_extract_json_list_wrapped():
    from src.at.generator.case_parser import _extract_json

    assert _extract_json("[1, 2, 3]") == [1, 2, 3]


def test_get_llm_config_env_override():
    from src.at.generator.case_parser import _get_llm_config

    with patch.dict("os.environ", {"YOUQU_AT_MODEL": "gpt-4"}):
        config = _get_llm_config()
    assert config["model"] == "gpt-4"


def test_get_llm_config_fallback():
    from src.at.generator.case_parser import _get_llm_config

    with patch("setting.globalconfig.GetCfg", side_effect=Exception("no config")):
        config = _get_llm_config()
    assert config["base_url"] == "http://localhost:8000/v1"
    assert config["timeout"] == 30


def test_parse_to_cases_end_to_end(tmp_path):
    from src.at.generator.case_parser import parse_to_cases

    csv_file = tmp_path / "input.csv"
    csv_file.write_text(
        "用例标题,所属模块,操作步骤,预期结果\n"
        "播放音乐,播放,1.点击播放按钮,音乐开始播放\n",
        encoding="utf-8-sig",
    )

    at_tree_file = tmp_path / "at-tree.yaml"
    at_tree_file.write_text("metadata:\n  app: test\n", encoding="utf-8")

    llm_response = json.dumps({
        "metadata": {"generated_at": "2026-07-07", "source": "input.csv"},
        "suites": [{
            "id": "playback",
            "name": "播放控制",
            "module": "播放",
            "status": "active",
            "steps": [
                {
                    "step_type": "action",
                    "description": "点击播放按钮",
                    "element_hint": None,
                    "menu_path": None,
                },
                {
                    "step_type": "assert",
                    "description": "验证音乐播放中",
                    "element_hint": None,
                    "menu_path": None,
                },
            ],
        }],
    })

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": llm_response}}],
    }
    mock_resp.raise_for_status = MagicMock()
    mock_client.post.return_value = mock_resp
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    output_file = tmp_path / "cases.yaml"
    with patch("httpx.Client", return_value=mock_client):
        parse_to_cases(
            input_path=str(csv_file),
            output_path=str(output_file),
            at_tree_path=str(at_tree_file),
        )

    assert output_file.exists()
    content = output_file.read_text(encoding="utf-8")
    assert "playback" in content
    assert "播放控制" in content


def test_parse_to_cases_skipped_suite(tmp_path):
    from src.at.generator.case_parser import parse_to_cases

    csv_file = tmp_path / "input.csv"
    csv_file.write_text(
        "用例标题,所属模块,操作步骤,预期结果\n"
        "音质主观评价,播放,1.听音乐音质,音质优美\n",
        encoding="utf-8-sig",
    )

    llm_response = json.dumps({
        "metadata": {"generated_at": "2026-07-07", "source": "input.csv"},
        "suites": [{
            "id": "audio_quality",
            "name": "音质评价",
            "module": "播放",
            "status": "skipped",
            "reason": "需要人工主观判断",
            "steps": [],
        }],
    })

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": llm_response}}],
    }
    mock_resp.raise_for_status = MagicMock()
    mock_client.post.return_value = mock_resp
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    output_file = tmp_path / "cases.yaml"
    with patch("httpx.Client", return_value=mock_client):
        parse_to_cases(
            input_path=str(csv_file),
            output_path=str(output_file),
        )

    content = output_file.read_text(encoding="utf-8")
    assert "skipped" in content
    assert "人工主观判断" in content


def test_parse_to_cases_invalid_llm_output(tmp_path, capsys):
    from src.at.generator.case_parser import parse_to_cases

    csv_file = tmp_path / "input.csv"
    csv_file.write_text(
        "用例标题,所属模块,操作步骤,预期结果\n"
        "播放音乐,播放,1.点击播放,音乐播放\n",
        encoding="utf-8-sig",
    )

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "not valid json at all"}}],
    }
    mock_resp.raise_for_status = MagicMock()
    mock_client.post.return_value = mock_resp
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    output_file = tmp_path / "cases.yaml"
    with patch("httpx.Client", return_value=mock_client):
        with pytest.raises(SystemExit):
            parse_to_cases(
                input_path=str(csv_file),
                output_path=str(output_file),
            )

    assert "failed to parse" in capsys.readouterr().out
