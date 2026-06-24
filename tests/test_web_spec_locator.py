# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only
"""Unit tests for src.web_spec.locator_resolver."""

import pytest

from web_spec.locator_resolver import LocatorError, resolve, resolve_all
from web_spec.models import Locator


class FakeLocator:
    def __init__(self, count):
        self.first = object()
        self._count = count

    def count(self):
        return self._count


class FakePage:
    def __init__(self, count):
        self.count = count

    def locator(self, value):
        return FakeLocator(self.count)


def test_interactive_locator_requires_unique_match_by_default():
    locator = Locator(strategy="css", value=".item")

    with pytest.raises(LocatorError):
        resolve(FakePage(2), locator, require_unique=True)


def test_locator_can_explicitly_take_first_match():
    locator = Locator(strategy="css", value=".item", first=True)

    resolved = resolve(FakePage(2), locator, require_unique=True)

    assert resolved.match_count == 2


def test_resolve_all_keeps_collection_locator():
    locator = Locator(strategy="css", value=".item")
    page = FakePage(3)

    resolved = resolve_all(page, locator)

    assert resolved.match_count == 3
    assert resolved.locator is not resolved.locator.first


class FakeScopedLocator:
    """模拟 Playwright locator 的链式调用能力"""

    def __init__(self, value: str):
        self._value = value
        self.first = self

    def count(self):
        return 1

    def get_by_test_id(self, value: str):
        return FakeScopedLocator(f"{self._value} > {value}")

    def get_by_role(self, value: str, **kwargs):
        return FakeScopedLocator(f"{self._value} > role:{value}")

    def get_by_text(self, value: str, exact: bool = False):
        return FakeScopedLocator(f"{self._value} > text:{value}")

    def locator(self, value: str):
        return FakeScopedLocator(f"{self._value} > {value}")


class FakeScopedPage:
    """模拟 page 的链式定位能力"""

    def get_by_test_id(self, value: str):
        return FakeScopedLocator(value)

    def get_by_role(self, value: str, **kwargs):
        return FakeScopedLocator(f"role:{value}")

    def get_by_text(self, value: str, exact: bool = False):
        return FakeScopedLocator(f"text:{value}")

    def locator(self, value: str):
        return FakeScopedLocator(value)


def test_scope_limits_search_to_parent_locator():
    """scope 应限定在父容器内搜索"""
    locator = Locator(
        strategy="test_id",
        value="submit",
        scope=Locator(strategy="test_id", value="card-2"),
    )
    page = FakeScopedPage()

    resolved = resolve(page, locator)

    # 验证链式调用：card-2 > submit
    assert resolved.value == "submit"
    assert resolved.strategy == "test_id"


def test_nested_scope_builds_chain_correctly():
    """多层 scope 应正确构建链式定位"""
    locator = Locator(
        strategy="test_id",
        value="button",
        scope=Locator(
            strategy="test_id",
            value="form",
            scope=Locator(strategy="test_id", value="modal"),
        ),
    )
    page = FakeScopedPage()

    resolved = resolve(page, locator)

    # 验证三层链式：modal > form > button
    assert resolved.value == "button"
    assert resolved.strategy == "test_id"
