# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only
"""Web spec data models for deterministic Playwright execution."""

from __future__ import annotations

from enum import Enum
from typing import Any, ClassVar, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LocatorStrategy(str, Enum):
    """Supported Web locator strategies."""

    ROLE = "role"
    TEXT = "text"
    BEM_CSS = "bem_css"
    TEST_ID = "test_id"
    CSS = "css"


class Locator(BaseModel):
    """Element locator in a Web spec."""

    model_config = ConfigDict(extra="allow")

    strategy: LocatorStrategy
    value: str
    name: Optional[str] = None
    exact: bool = False
    stability: str = "stable_bem"
    first: bool = False
    scope: Optional[Locator] = None


class ActionType(str, Enum):
    """Supported deterministic Web actions."""

    CLICK = "click"
    FILL = "fill"
    INPUT_TEXT = "input_text"
    KEYBOARD_TYPE = "keyboard_type"
    PRESS_KEY = "press_key"
    HOVER = "hover"
    SELECT_OPTION = "select_option"
    WAIT_FOR = "wait_for"
    SCROLL = "scroll"
    RIGHT_CLICK = "right_click"
    DBLCLICK = "dblclick"
    DRAG_TO = "drag_to"
    UPLOAD_FILE = "upload_file"


class SettleSpec(BaseModel):
    """Optional stabilization rule after an action."""

    model_config = ConfigDict(extra="allow")

    network_idle: bool = False
    settle_ms: int = 300
    wait_for: Optional[Locator] = None
    wait_for_text: Optional[str] = None


class PositionSpec(BaseModel):
    """Element-relative position in a Web spec action."""

    x: float
    y: float


class ActionSpec(BaseModel):
    """A single action in a Web spec step."""

    model_config = ConfigDict(extra="allow")

    type: ActionType
    locator: Optional[Locator] = None
    target: Optional[Locator] = None
    source_position: Optional[PositionSpec] = None
    target_position: Optional[PositionSpec] = None
    value: Optional[Any] = None
    key: Optional[str] = None
    direction: Optional[str] = None
    steps: Optional[int] = None
    timeout_ms: int = 5000
    settle_after: Optional[SettleSpec] = None


class AssertionType(str, Enum):
    """Supported deterministic Web assertions."""

    VISIBLE = "visible"
    NOT_VISIBLE = "not_visible"
    TEXT_CONTAINS = "text_contains"
    TEXT_EQUALS = "text_equals"
    HTML_CONTAINS = "html_contains"
    HTML_EQUALS = "html_equals"
    ENABLED = "enabled"
    DISABLED = "disabled"
    COUNT = "count"
    INPUT_VALUE_EQUALS = "input_value_equals"
    INPUT_VALUE_CONTAINS = "input_value_contains"
    ATTRIBUTE_EQUALS = "attribute_equals"
    ATTRIBUTE_CONTAINS = "attribute_contains"
    CLASS_CONTAINS = "class_contains"
    URL_EQUALS = "url_equals"
    URL_CONTAINS = "url_contains"
    TEXT_SEQUENCE = "text_sequence"


class AssertionSpec(BaseModel):
    """A single assertion in a Web spec step."""

    model_config = ConfigDict(extra="allow")

    type: AssertionType
    locator: Optional[Locator] = None
    expected: Optional[Any] = None
    attribute: Optional[str] = None
    mode: Optional[str] = None
    timeout_ms: Optional[int] = None
    retry: bool = True


class ExecutionSpec(BaseModel):
    """Per-spec execution overrides."""

    model_config = ConfigDict(extra="allow")

    auto_wait: str = "interactive"
    settle_after_action: SettleSpec = Field(default_factory=SettleSpec)
    assertion_timeout_ms: int = 30000
    assertion_retry: bool = True
    assertion_retry_interval_ms: int = 500


class TeardownSpec(BaseModel):
    """Teardown policy and optional teardown steps."""

    model_config = ConfigDict(extra="allow")

    reset_page_state: bool = True
    restore_entry_page: bool = False
    steps: list[ActionSpec] = Field(default_factory=list)


class StepSpec(BaseModel):
    """A single deterministic Web test step."""

    model_config = ConfigDict(extra="allow")

    order: int = 0
    description: str = ""
    expected: str = ""
    actions: list[ActionSpec] = Field(default_factory=list)
    assertions: list[AssertionSpec] = Field(default_factory=list)


class TestSpec(BaseModel):
    """Parsed Web test spec."""

    __test__: ClassVar[bool] = False
    model_config = ConfigDict(extra="allow")

    @field_validator("priority", mode="before")
    @classmethod
    def _normalize_priority(cls, value: Any) -> str:
        if value is None:
            return "1"
        return str(value)

    id: str
    title: str
    description: str = ""
    module: str = ""
    feature: str = ""
    tags: list[str] = Field(default_factory=list)
    priority: str = "1"
    given: str = ""
    entry_page: str = ""
    entry_url: str = ""
    setup: list[ActionSpec] = Field(default_factory=list)
    steps: list[StepSpec] = Field(default_factory=list)
    teardown: Optional[TeardownSpec] = None
    execution: Optional[ExecutionSpec] = None
    source: str = ""
    pms_id: Optional[str] = None
