# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class SourceType(str, Enum):
    static = "static"
    runtime = "runtime"


class StepType(str, Enum):
    action = "action"
    assert_ = "assert"
    navigate = "navigate"


class ElementHint(str, Enum):
    dtk_main_menu = "dtk_main_menu"
    dtk_context_menu = "dtk_context_menu"
    titlebar = "titlebar"
    toolbar = "toolbar"
    sidebar = "sidebar"
    tab_bar = "tab_bar"
    dialog = "dialog"
    tooltip = "tooltip"
    dock = "dock"
    click = "click"
    hover = "hover"
    keyboard_shortcut = "keyboard_shortcut"
    scroll = "scroll"
    input_text = "input_text"
    drag_drop = "drag_drop"
    dbus_call = "dbus_call"
    screenshot = "screenshot"
    vlm_assert = "vlm_assert"
    assert_window = "assert_window"
    assert_element = "assert_element"
    assert_window_count = "assert_window_count"
    assert_not_exists = "assert_not_exists"
    visual_check = "visual_check"
    physical_device = "physical_device"
    cross_device = "cross_device"


class MappingStatus(str, Enum):
    mapped = "mapped"
    unmapped = "unmapped"
    deprecated = "deprecated"


# ---- Phase 1: AT-SPI Tree ----


class AtTreeNode(BaseModel):
    id: str
    role: str = ""
    name: str = ""
    object_name: str = ""
    accessible_id: str = ""
    source: SourceType = SourceType.runtime
    note: str = ""
    comment: str = ""
    annotation_status: str = "draft"
    classification: str = ""
    children: list[AtTreeNode] = Field(default_factory=list)


class AtTreeMetadata(BaseModel):
    app: str
    source_commit: str = ""
    generated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    scan_mode: str = "hybrid"


class AtTree(BaseModel):
    metadata: AtTreeMetadata
    structure: dict[str, list[AtTreeNode]] = Field(default_factory=lambda: {"windows": []})


# ---- Phase 2: Cases ----


class CaseStep(BaseModel):
    step_type: StepType
    description: str
    element_hint: Optional[ElementHint] = None
    items: Optional[list[str]] = None

    action: Optional[str] = None
    key: Optional[str] = None
    text: Optional[str] = None
    command: Optional[str] = None
    element_ref: Optional[str] = None
    selector: Optional[dict[str, Any]] = None
    assertion: Optional[str] = None
    needs_accessible_name: bool = False
    accessible_name_suggestion: Optional[str] = None
    value: Optional[Any] = None


class CaseSuite(BaseModel):
    id: str
    name: str
    module: str
    description: str = ""
    status: str = "active"
    reason: str = ""
    steps: list[CaseStep] = Field(default_factory=list)


class CasesMetadata(BaseModel):
    generated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    source: str = ""


class CasesDoc(BaseModel):
    metadata: CasesMetadata = Field(default_factory=CasesMetadata)
    cases: list[CaseSuite] = Field(default_factory=list)


# ---- Phase 3: Element Mappings ----


class MappingSelector(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    name_pattern: Optional[str] = None
    # Qt6 bridge 把 objectName 编码进 get_accessible_id() 的点分路径；
    # 生成链通过该字段透传，否则映射产物会静默丢弃。
    accessible_id: Optional[str] = None
    object_name: Optional[str] = None


class MappingEntry(BaseModel):
    case_id: str
    step_index: int
    description: str
    step_type: StepType
    element_hint: Optional[ElementHint] = None
    items: Optional[list[str]] = None
    element_ref: Optional[str] = None
    selector: Optional[MappingSelector] = None
    status: MappingStatus = MappingStatus.mapped
    reason: str = ""
    fix_suggestion: str = ""
    note: str = ""
    context: str = ""


class MappingsMetadata(BaseModel):
    generated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    at_tree_source: str = ""


class ElementMappingsDoc(BaseModel):
    metadata: MappingsMetadata = Field(default_factory=MappingsMetadata)
    mappings: list[MappingEntry] = Field(default_factory=list)


# ---- Phase 4/5: Executable Suite YAML (shared data contract) ----


class EnvCheckItem(BaseModel):
    """Environment pre-check entry.

    type:
      - process      — pgrep by process name
      - file_exists  — file path existence
    """

    type: str
    name: str
    expect: str = "not_running"
    spec_ids: Optional[list[str]] = None


class WaitCondition(BaseModel):
    selector: dict[str, Any]
    timeout: int = 3000
    interval: int = 200


class SuiteActionStep(BaseModel):
    action: str
    ref: Optional[str] = None
    selector: Optional[dict[str, Any]] = None
    command: Optional[str] = None
    wait: Optional[float] = None
    wait_for: Optional[WaitCondition] = None
    wait_after: Optional[int] = None
    do: Optional[str] = None
    x: Optional[int] = None
    y: Optional[int] = None
    items: Optional[list[str]] = None
    path: Optional[str] = None
    prompt: Optional[str] = None
    evidence: Optional[str] = None
    app: Optional[str] = None
    expected: Optional[int] = None
    name_pattern: Optional[str] = None
    key: Optional[str] = None
    text: Optional[str] = None
    value: Optional[Any] = None
    note: Optional[str] = None


class SuiteCase(BaseModel):
    id: str
    name: str = ""
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    skip: Optional[str] = None
    steps: list[SuiteActionStep] = Field(default_factory=list)
    assert_steps: list[SuiteActionStep] = Field(default_factory=list)
    timeout: Optional[int] = None


class SuiteConfig(BaseModel):
    name: str
    app: str = ""
    description: str = ""
    module: str = ""
    tags: list[str] = Field(default_factory=list)
    skip: Optional[str] = None
    fast_fail: bool = False
    env_check: list[EnvCheckItem] = Field(default_factory=list)
    setup: list[SuiteActionStep] = Field(default_factory=list)
    suites: list[SuiteCase] = Field(default_factory=list)
    teardown: list[SuiteActionStep] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True)
