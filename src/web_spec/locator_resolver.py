# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only
"""Resolve Web spec locators to Playwright locators."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from web_spec.models import Locator as LocatorSpec
from web_spec.models import LocatorStrategy


class LocatorError(Exception):
    """Raised when a locator cannot be resolved safely."""


@dataclass
class ResolvedLocator:
    """Playwright locator plus metadata."""

    locator: Any
    strategy: str
    value: str
    match_count: int
    stability: str


def resolve_lazy(page: Any, spec: LocatorSpec) -> ResolvedLocator:
    """Resolve a locator without counting matches, for wait-like actions."""
    locator = _build_locator(page, spec)
    return ResolvedLocator(
        locator=locator.first,
        strategy=spec.strategy.value,
        value=spec.value,
        match_count=-1,
        stability=_stability(spec),
    )


def resolve(page: Any, spec: LocatorSpec, require_unique: bool = False) -> ResolvedLocator:
    """Resolve a locator and validate that at least one element matches."""
    locator = _build_locator(page, spec)
    count = locator.count()
    if count == 0:
        raise LocatorError(f"{spec.strategy.value}='{spec.value}' 匹配 0 个元素")
    if require_unique and count > 1 and not spec.first:
        raise LocatorError(
            f"{spec.strategy.value}='{spec.value}' 匹配 {count} 个元素；"
            "交互动作默认要求唯一匹配，如需取第一个请设置 locator.first: true"
        )
    return ResolvedLocator(
        locator=locator.first,
        strategy=spec.strategy.value,
        value=spec.value,
        match_count=count,
        stability=_stability(spec),
    )


def resolve_all(page: Any, spec: LocatorSpec) -> ResolvedLocator:
    """Resolve a locator as a collection for multi-element assertions."""
    locator = _build_locator(page, spec)
    count = locator.count()
    if count == 0:
        raise LocatorError(f"{spec.strategy.value}='{spec.value}' 匹配 0 个元素")
    return ResolvedLocator(
        locator=locator,
        strategy=spec.strategy.value,
        value=spec.value,
        match_count=count,
        stability=_stability(spec),
    )


def _build_locator(page: Any, spec: LocatorSpec):
    """Build a Playwright locator, optionally scoped to a parent locator."""
    if spec.scope:
        parent = _build_locator(page, spec.scope)
        return _build_locator_on_parent(parent, spec)
    return _build_locator_on_parent(page, spec)


def _build_locator_on_parent(parent: Any, spec: LocatorSpec):
    """Build locator on a parent (page or another locator)."""
    if spec.strategy == LocatorStrategy.ROLE:
        options = {"name": spec.name} if spec.name else {}
        return parent.get_by_role(spec.value, **options)
    if spec.strategy == LocatorStrategy.TEXT:
        return parent.get_by_text(spec.value, exact=spec.exact)
    if spec.strategy == LocatorStrategy.TEST_ID:
        return parent.get_by_test_id(spec.value)
    if spec.strategy in (LocatorStrategy.BEM_CSS, LocatorStrategy.CSS):
        return parent.locator(spec.value)
    raise LocatorError(f"未知的 locator strategy: {spec.strategy}")


def _stability(spec: LocatorSpec) -> str:
    if spec.strategy in (LocatorStrategy.ROLE, LocatorStrategy.TEXT, LocatorStrategy.TEST_ID):
        return "semantic"
    return spec.stability
