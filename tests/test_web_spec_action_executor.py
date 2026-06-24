# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only
"""Unit tests for src.web_spec.action_executor."""

from web_spec.action_executor import execute
from web_spec.models import ActionSpec


class FakeKeyboard:
    def __init__(self):
        self.typed = ""
        self.pressed = ""

    def type(self, value):
        self.typed = value

    def press(self, value):
        self.pressed = value


class FakeLocator:
    def __init__(self, count=1):
        self._count = count
        self.first = self
        self.click_kwargs = None
        self.dblclick_kwargs = None
        self.drag_target = None
        self.drag_kwargs = None
        self.uploaded_files = None
        self.wait_calls = []

    def count(self):
        return self._count

    def wait_for(self, **kwargs):
        self.wait_calls.append(kwargs)

    def click(self, **kwargs):
        self.click_kwargs = kwargs

    def dblclick(self, **kwargs):
        self.dblclick_kwargs = kwargs

    def drag_to(self, target, **kwargs):
        self.drag_target = target
        self.drag_kwargs = kwargs

    def set_input_files(self, value):
        self.uploaded_files = value


class FakePage:
    def __init__(self, locators=None):
        self.keyboard = FakeKeyboard()
        self.locators = locators or {}

    def locator(self, value):
        return self.locators.setdefault(value, FakeLocator())

    def get_by_test_id(self, value):
        return self.locator(value)

    def get_by_text(self, value, exact=False):
        return self.locator(value)

    def get_by_role(self, value, **options):
        return self.locator(options.get("name") or value)


def test_keyboard_type_action():
    page = FakePage()
    spec = ActionSpec.model_validate({"type": "keyboard_type", "value": "hello"})

    result = execute(page, spec)

    assert result.success is True
    assert page.keyboard.typed == "hello"


def test_press_key_requires_key():
    result = execute(FakePage(), ActionSpec.model_validate({"type": "press_key"}))

    assert result.success is False
    assert "key" in result.error


def test_right_click_action():
    locator = FakeLocator()
    page = FakePage({".menu-target": locator})
    spec = ActionSpec.model_validate({
        "type": "right_click",
        "locator": {"strategy": "css", "value": ".menu-target"},
        "timeout_ms": 1234,
    })

    result = execute(page, spec)

    assert result.success is True
    assert locator.click_kwargs == {"button": "right", "timeout": 1234}


def test_dblclick_action():
    locator = FakeLocator()
    page = FakePage({".open-target": locator})
    spec = ActionSpec.model_validate({
        "type": "dblclick",
        "locator": {"strategy": "css", "value": ".open-target"},
        "timeout_ms": 2345,
    })

    result = execute(page, spec)

    assert result.success is True
    assert locator.dblclick_kwargs == {"timeout": 2345}


def test_drag_to_action_resolves_target():
    source = FakeLocator()
    target = FakeLocator()
    page = FakePage({".source": source, ".target": target})
    spec = ActionSpec.model_validate({
        "type": "drag_to",
        "locator": {"strategy": "css", "value": ".source"},
        "target": {"strategy": "css", "value": ".target"},
        "timeout_ms": 3456,
    })

    result = execute(page, spec)

    assert result.success is True
    assert source.drag_target is target
    assert source.drag_kwargs == {"timeout": 3456}


def test_drag_to_action_passes_positions_and_steps():
    source = FakeLocator()
    target = FakeLocator()
    page = FakePage({".source": source, ".target": target})
    spec = ActionSpec.model_validate({
        "type": "drag_to",
        "locator": {"strategy": "css", "value": ".source"},
        "source_position": {"x": 10, "y": 12},
        "target": {"strategy": "css", "value": ".target"},
        "target_position": {"x": 40, "y": 30},
        "steps": 5,
        "timeout_ms": 3456,
    })

    result = execute(page, spec)

    assert result.success is True
    assert source.drag_target is target
    assert source.drag_kwargs == {
        "timeout": 3456,
        "source_position": {"x": 10.0, "y": 12.0},
        "target_position": {"x": 40.0, "y": 30.0},
        "steps": 5,
    }


def test_drag_to_requires_target():
    spec = ActionSpec.model_validate({
        "type": "drag_to",
        "locator": {"strategy": "css", "value": ".source"},
    })

    result = execute(FakePage(), spec)

    assert result.success is False
    assert "target" in result.error


def test_upload_file_action():
    locator = FakeLocator()
    page = FakePage({"input[type=file]": locator})
    spec = ActionSpec.model_validate({
        "type": "upload_file",
        "locator": {"strategy": "css", "value": "input[type=file]"},
        "value": "/tmp/demo.png",
    })

    result = execute(page, spec)

    assert result.success is True
    assert locator.uploaded_files == "/tmp/demo.png"


def test_upload_file_requires_value():
    spec = ActionSpec.model_validate({
        "type": "upload_file",
        "locator": {"strategy": "css", "value": "input[type=file]"},
    })

    result = execute(FakePage(), spec)

    assert result.success is False
    assert "value" in result.error
