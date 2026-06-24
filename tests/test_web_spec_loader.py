# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only
"""Unit tests for src.web_spec.loader."""

import pytest

from web_spec.loader import SpecValidationError, load_spec, load_spec_dir, load_specs


def _write_spec(path, title="登录测试"):
    path.write_text(f"""
id: {path.stem}
title: {title}
module: 认证
feature: 登录
tags: [smoke]
steps:
  - description: 点击登录
    actions:
      - type: click
        locator: {{strategy: role, value: button, name: 登录}}
    assertions:
      - type: visible
        locator: {{strategy: text, value: 欢迎}}
""", encoding="utf-8")
    return path


def test_load_spec_parses_yaml(tmp_path):
    spec_path = _write_spec(tmp_path / "login.yaml")
    spec = load_spec(spec_path)

    assert spec.id == "login"
    assert spec.title == "登录测试"
    assert spec.module == "认证"
    assert spec.source == str(spec_path)
    assert spec.steps[0].order == 1


def test_load_spec_uses_name_as_title(tmp_path):
    spec_path = tmp_path / "named.yaml"
    spec_path.write_text("""
name: 命名用例
steps:
  - description: 等待文本
    assertions:
      - type: visible
        locator: {strategy: text, value: 完成}
""", encoding="utf-8")

    spec = load_spec(spec_path)
    assert spec.id == "named"
    assert spec.title == "命名用例"


def test_load_spec_rejects_empty_file(tmp_path):
    spec_path = tmp_path / "empty.yaml"
    spec_path.write_text("", encoding="utf-8")

    with pytest.raises(SpecValidationError):
        load_spec(spec_path)


def test_load_spec_wraps_yaml_parse_error(tmp_path):
    spec_path = tmp_path / "bad.yaml"
    spec_path.write_text("title: [未闭合\n", encoding="utf-8")

    with pytest.raises(SpecValidationError):
        load_spec(spec_path)


def test_load_spec_rejects_steps_without_work(tmp_path):
    spec_path = tmp_path / "bad.yaml"
    spec_path.write_text("""
title: 无动作
steps:
  - description: 空步骤
""", encoding="utf-8")

    with pytest.raises(SpecValidationError):
        load_spec(spec_path)


def test_load_spec_parses_new_actions(tmp_path):
    spec_path = tmp_path / "actions.yaml"
    spec_path.write_text("""
title: 常用动作
steps:
  - description: 右键和拖拽
    actions:
      - type: right_click
        locator: {strategy: css, value: .menu-target}
      - type: dblclick
        locator: {strategy: css, value: .open-target}
      - type: drag_to
        locator: {strategy: css, value: .source}
        source_position: {x: 10, y: 12}
        target: {strategy: css, value: .target}
        target_position: {x: 40, y: 30}
        steps: 5
      - type: upload_file
        locator: {strategy: css, value: "input[type=file]"}
        value: /tmp/demo.png
""", encoding="utf-8")

    spec = load_spec(spec_path)

    action_types = [action.type.value for action in spec.steps[0].actions]
    assert action_types == ["right_click", "dblclick", "drag_to", "upload_file"]
    drag_action = spec.steps[0].actions[2]
    assert drag_action.target.value == ".target"
    assert drag_action.source_position.x == 10
    assert drag_action.target_position.y == 30
    assert drag_action.steps == 5


def test_load_spec_parses_new_assertions(tmp_path):
    spec_path = tmp_path / "assertions.yaml"
    spec_path.write_text("""
title: 常用断言
steps:
  - description: 属性和顺序
    assertions:
      - type: input_value_contains
        locator: {strategy: css, value: input}
        expected: YouQu
      - type: attribute_equals
        locator: {strategy: css, value: button}
        attribute: aria-label
        expected: 提交
      - type: class_contains
        locator: {strategy: css, value: button}
        expected: primary
      - type: url_contains
        expected: /chat
      - type: text_sequence
        locator: {strategy: css, value: .item}
        expected: [A, B]
        mode: contains_order
""", encoding="utf-8")

    spec = load_spec(spec_path)

    assertion_types = [assertion.type.value for assertion in spec.steps[0].assertions]
    assert assertion_types == [
        "input_value_contains",
        "attribute_equals",
        "class_contains",
        "url_contains",
        "text_sequence",
    ]
    assert spec.steps[0].assertions[1].attribute == "aria-label"
    assert spec.steps[0].assertions[4].mode == "contains_order"


def test_load_spec_dir_loads_recursively_and_skips_index(tmp_path):
    spec_dir = tmp_path / "specs"
    spec_dir.mkdir()
    _write_spec(spec_dir / "b.yaml", title="B")
    sub = spec_dir / "sub"
    sub.mkdir()
    _write_spec(sub / "a.yml", title="A")
    (spec_dir / "index.yaml").write_text("specs: []\n", encoding="utf-8")

    specs = load_spec_dir(spec_dir)
    assert [spec.id for spec in specs] == ["b", "a"]


def test_load_spec_dir_skips_web_spec_config_file(tmp_path):
    _write_spec(tmp_path / "login.yaml")
    (tmp_path / "web_spec.yaml").write_text("""
base_url: http://localhost:5173
entry_route: /
""", encoding="utf-8")

    specs = load_spec_dir(tmp_path)

    assert [spec.id for spec in specs] == ["login"]


def test_load_specs_accepts_file_or_directory(tmp_path):
    spec_dir = tmp_path / "specs"
    spec_dir.mkdir()
    spec_path = _write_spec(spec_dir / "one.yaml")

    assert len(load_specs(spec_path)) == 1
    assert len(load_specs(spec_dir)) == 1
