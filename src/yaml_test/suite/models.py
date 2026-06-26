# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only
"""Pydantic models for dev-mode suite YAML format.

Schema:
    name: "键盘快捷键自测"           # Suite display name
    app: "deepin-reader"           # Target application
    module: "键盘"                  # Module classification
    env_check:                     # Optional env pre-checks
      - type: process
        name: "deepin-reader"
        expect: "not_running"
    setup:                         # Suite-level setup (once)
      - action: session_start
        command: "deepin-reader"
    specs:                         # Suite specs (serial execution)
      - id: shortcut_copy
        name: "Ctrl+C 复制"
        tags: ["shortcut"]
        steps:
          - action: keyboard_hot_key
            keys: "Ctrl+C"
    teardown:                      # Suite-level teardown (once)
      - action: session_stop
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class EnvCheckItem(BaseModel):
    """A single environment pre-check entry.

    ``type`` determines the check method:
    - ``process``    — pgrep by process name
    - ``file_exists`` — file path existence
    - ``dbus_property`` — (future) D-Bus property check
    - ``dconfig`` — (future) OS config key check
    """

    model_config = ConfigDict(extra="allow")

    type: str
    name: str
    expect: str = "not_running"
    spec_ids: list[str] | None = None


class SuiteSpecItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    name: str = ""
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    skip: str | None = None
    steps: list[dict[str, Any]] = Field(default_factory=list)
    timeout: int | None = None


class SuiteSpec(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    app: str = ""
    module: str = ""
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    skip: str | None = None
    fast_fail: bool = False
    env_check: list[EnvCheckItem] = Field(default_factory=list)
    setup: list[dict[str, Any]] = Field(default_factory=list)
    specs: list[SuiteSpecItem] = Field(default_factory=list)
    teardown: list[dict[str, Any]] = Field(default_factory=list)


class SpecResult(BaseModel):
    id: str
    name: str = ""
    status: str = ""
    error: str = ""
    duration: float = 0.0


class SuiteResult(BaseModel):
    suite_name: str = ""
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    timeout: int = 0
    total: int = 0
    specs: list[SpecResult] = Field(default_factory=list)
    duration: float = 0.0
    error: str = ""
