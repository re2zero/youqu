# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only
"""Unit tests for src.web_spec.models."""

import pytest
from pydantic import ValidationError

from web_spec.models import ActionType, AssertionType, LocatorStrategy, TestSpec


def test_parse_minimal_web_spec():
    spec = TestSpec.model_validate({
        "id": "login_smoke",
        "title": "登录冒烟测试",
        "steps": [{
            "order": 1,
            "description": "点击登录按钮",
            "actions": [{
                "type": "click",
                "locator": {"strategy": "role", "value": "button", "name": "登录"},
            }],
            "assertions": [{
                "type": "visible",
                "locator": {"strategy": "text", "value": "欢迎"},
            }],
        }],
    })

    assert spec.id == "login_smoke"
    assert spec.steps[0].actions[0].locator.strategy == LocatorStrategy.ROLE
    assert spec.steps[0].assertions[0].type == AssertionType.VISIBLE


def test_order_assertion_is_not_exposed():
    with pytest.raises(ValidationError):
        TestSpec.model_validate({
            "id": "order_case",
            "title": "顺序断言",
            "steps": [{
                "description": "检查顺序",
                "assertions": [{"type": "order", "expected": ["A", "B"]}],
            }],
        })


def test_locator_first_flag_is_supported():
    spec = TestSpec.model_validate({
        "id": "first_case",
        "title": "取第一个匹配元素",
        "steps": [{
            "description": "点击第一个",
            "actions": [{
                "type": "click",
                "locator": {"strategy": "css", "value": ".item", "first": True},
            }],
        }],
    })

    assert spec.steps[0].actions[0].locator.first is True


def test_drag_to_action_target_is_supported():
    spec = TestSpec.model_validate({
        "id": "drag_case",
        "title": "拖拽元素",
        "steps": [{
            "description": "拖拽到目标",
            "actions": [{
                "type": "drag_to",
                "locator": {"strategy": "css", "value": ".source"},
                "source_position": {"x": 10, "y": 12},
                "target": {"strategy": "css", "value": ".target"},
                "target_position": {"x": 40, "y": 30},
                "steps": 5,
            }],
        }],
    })

    action = spec.steps[0].actions[0]
    assert action.type == ActionType.DRAG_TO
    assert action.target.value == ".target"
    assert action.source_position.x == 10
    assert action.source_position.y == 12
    assert action.target_position.x == 40
    assert action.target_position.y == 30
    assert action.steps == 5


def test_numeric_priority_is_normalized_to_string():
    spec = TestSpec.model_validate({
        "id": "priority_case",
        "title": "数字优先级",
        "priority": 1,
        "steps": [{
            "description": "检查",
            "assertions": [{"type": "visible", "locator": {"strategy": "text", "value": "ok"}}],
        }],
    })

    assert spec.priority == "1"


def test_new_assertion_fields_are_supported():
    spec = TestSpec.model_validate({
        "id": "assertion_case",
        "title": "新增断言字段",
        "steps": [{
            "description": "检查属性和顺序",
            "assertions": [
                {
                    "type": "attribute_contains",
                    "locator": {"strategy": "css", "value": "button"},
                    "attribute": "aria-label",
                    "expected": "提交",
                },
                {
                    "type": "text_sequence",
                    "locator": {"strategy": "css", "value": ".item"},
                    "expected": ["A", "B"],
                    "mode": "contains_order",
                },
            ],
        }],
    })

    first, second = spec.steps[0].assertions
    assert first.attribute == "aria-label"
    assert second.mode == "contains_order"


def test_locator_scope_is_supported():
    spec = TestSpec.model_validate({
        "id": "scope_case",
        "title": "Scope 测试",
        "steps": [{
            "description": "在容器内点击",
            "actions": [{
                "type": "click",
                "locator": {
                    "strategy": "test_id",
                    "value": "submit",
                    "scope": {"strategy": "test_id", "value": "card-2"},
                },
            }],
        }],
    })

    locator = spec.steps[0].actions[0].locator
    assert locator.scope is not None
    assert locator.scope.value == "card-2"
    assert locator.scope.strategy == LocatorStrategy.TEST_ID


def test_nested_scope_is_supported():
    spec = TestSpec.model_validate({
        "id": "nested_scope_case",
        "title": "嵌套 Scope 测试",
        "steps": [{
            "description": "多层限定",
            "actions": [{
                "type": "click",
                "locator": {
                    "strategy": "test_id",
                    "value": "button",
                    "scope": {
                        "strategy": "test_id",
                        "value": "form",
                        "scope": {"strategy": "test_id", "value": "modal"},
                    },
                },
            }],
        }],
    })

    locator = spec.steps[0].actions[0].locator
    assert locator.scope.value == "form"
    assert locator.scope.scope.value == "modal"
    assert locator.scope.scope.scope is None
