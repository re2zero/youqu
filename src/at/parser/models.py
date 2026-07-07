# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class SourceType(str, Enum):
    static = "static"
    runtime = "runtime"


class StepType(str, Enum):
    action = "action"
    assert_ = "assert"
    navigate = "navigate"


class ElementHint(str, Enum):
    main_menu_comb = "main_menu_comb"
    context_menu_comb = "context_menu_comb"
    titlebar = "titlebar"
    toolbar = "toolbar"
    sidebar = "sidebar"
    tab_bar = "tab_bar"
    dialog = "dialog"
    tooltip = "tooltip"
    dock = "dock"


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
    menu_path: Optional[list[str]] = None


class CaseSuite(BaseModel):
    id: str
    name: str
    module: str
    description: str = ""
    steps: list[CaseStep] = Field(default_factory=list)


class CasesMetadata(BaseModel):
    generated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    source: str = ""


class CasesDoc(BaseModel):
    metadata: CasesMetadata = Field(default_factory=CasesMetadata)
    suites: list[CaseSuite] = Field(default_factory=list)


# ---- Phase 3: Element Mappings ----

class MappingSelector(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    name_pattern: Optional[str] = None


class MappingEntry(BaseModel):
    case_id: str
    step_index: int
    description: str
    step_type: StepType
    element_hint: Optional[ElementHint] = None
    menu_path: Optional[list[str]] = None
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


# ---- Phase 4/5: Executable Suite YAML ----

class SuiteActionStep(BaseModel):
    action: str
    ref: Optional[str] = None
    selector: Optional[dict[str, Any]] = None
    command: Optional[str] = None
    wait: Optional[int] = None
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


class SuiteCase(BaseModel):
    id: str
    steps: list[SuiteActionStep] = Field(default_factory=list)
    assert_steps: list[SuiteActionStep] = Field(default_factory=list)


class SuiteConfig(BaseModel):
    name: str
    app: str = ""
    description: str = ""
    module: str = ""
    setup: list[SuiteActionStep] = Field(default_factory=list)
    suites: list[SuiteCase] = Field(default_factory=list)
    teardown: list[SuiteActionStep] = Field(default_factory=list)
