# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only
"""Execute deterministic Web spec actions."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from web_spec.locator_resolver import LocatorError, ResolvedLocator, resolve, resolve_lazy
from web_spec.models import ActionSpec, ActionType, ExecutionSpec, SettleSpec


@dataclass
class ActionResult:
    """Single action execution result."""

    type: str
    success: bool
    error: str | None = None
    locator_strategy: str | None = None
    locator_value: str | None = None
    locator_match_count: int = 0
    locator_stability: str | None = None
    duration_ms: int = 0


def execute(page: Any, spec: ActionSpec, execution: ExecutionSpec | None = None) -> ActionResult:
    """Execute one action and return a structured result."""
    start = time.monotonic()
    resolved: ResolvedLocator | None = None
    try:
        if spec.type == ActionType.CLICK:
            resolved = _wait_and_resolve(page, spec, execution)
            resolved.locator.click()
        elif spec.type == ActionType.FILL:
            resolved = _resolve_required(page, spec, require_unique=True)
            resolved.locator.fill(str(spec.value or ""))
        elif spec.type == ActionType.INPUT_TEXT:
            resolved = _resolve_required(page, spec, require_unique=True)
            resolved.locator.click()
            page.keyboard.type(str(spec.value or ""))
        elif spec.type == ActionType.KEYBOARD_TYPE:
            page.keyboard.type(str(spec.value or ""))
        elif spec.type == ActionType.PRESS_KEY:
            if not spec.key:
                raise ValueError("press_key 需要 key 参数")
            page.keyboard.press(spec.key)
        elif spec.type == ActionType.HOVER:
            resolved = _wait_and_resolve(page, spec, execution)
            resolved.locator.hover()
        elif spec.type == ActionType.SELECT_OPTION:
            resolved = _resolve_required(page, spec, require_unique=True)
            resolved.locator.select_option(spec.value)
        elif spec.type == ActionType.WAIT_FOR:
            if spec.locator:
                resolved = resolve_lazy(page, spec.locator)
                resolved.locator.wait_for(state="visible", timeout=spec.timeout_ms)
            else:
                time.sleep(spec.timeout_ms / 1000)
        elif spec.type == ActionType.SCROLL:
            resolved = _do_scroll(page, spec)
        elif spec.type == ActionType.RIGHT_CLICK:
            resolved = _wait_and_resolve(page, spec, execution)
            resolved.locator.click(button="right", timeout=spec.timeout_ms)
        elif spec.type == ActionType.DBLCLICK:
            resolved = _wait_and_resolve(page, spec, execution)
            resolved.locator.dblclick(timeout=spec.timeout_ms)
        elif spec.type == ActionType.DRAG_TO:
            resolved = _resolve_required(page, spec, require_unique=True)
            target = _resolve_target(page, spec)
            drag_kwargs = _build_drag_kwargs(spec)
            resolved.locator.drag_to(target.locator, **drag_kwargs)
        elif spec.type == ActionType.UPLOAD_FILE:
            if spec.value is None:
                raise ValueError("upload_file 需要 value 参数")
            resolved = _resolve_required(page, spec, require_unique=True)
            resolved.locator.set_input_files(spec.value)
        else:
            raise ValueError(f"不支持的 action type: {spec.type}")

        settle = spec.settle_after or (execution.settle_after_action if execution else None)
        if settle:
            _settle(page, settle)
        return _make_result(spec, True, start, resolved=resolved)
    except Exception as exc:
        return _make_result(spec, False, start, error=str(exc), resolved=resolved)


def _resolve_required(page: Any, spec: ActionSpec, require_unique: bool) -> ResolvedLocator:
    if not spec.locator:
        raise ValueError(f"{spec.type.value} 需要 locator")
    return resolve(page, spec.locator, require_unique=require_unique)


def _resolve_target(page: Any, spec: ActionSpec) -> ResolvedLocator:
    if not spec.target:
        raise ValueError("drag_to 需要 target")
    return resolve(page, spec.target, require_unique=True)


def _build_drag_kwargs(spec: ActionSpec) -> dict[str, Any]:
    drag_kwargs: dict[str, Any] = {"timeout": spec.timeout_ms}
    if spec.source_position:
        drag_kwargs["source_position"] = spec.source_position.model_dump()
    if spec.target_position:
        drag_kwargs["target_position"] = spec.target_position.model_dump()
    if spec.steps is not None:
        drag_kwargs["steps"] = spec.steps
    return drag_kwargs


def _wait_and_resolve(page: Any, spec: ActionSpec, execution: ExecutionSpec | None) -> ResolvedLocator:
    resolved = _resolve_required(page, spec, require_unique=True)
    auto_wait = execution.auto_wait if execution else "interactive"
    if auto_wait in ("interactive", "visible"):
        resolved.locator.wait_for(state="visible", timeout=spec.timeout_ms)
    return resolved


def _do_scroll(page: Any, spec: ActionSpec) -> ResolvedLocator | None:
    if spec.locator:
        resolved = resolve(page, spec.locator, require_unique=False)
        resolved.locator.scroll_into_view_if_needed()
        return resolved
    delta = 300
    direction = spec.direction or "down"
    if direction == "down":
        page.mouse.wheel(0, delta)
    elif direction == "up":
        page.mouse.wheel(0, -delta)
    elif direction == "right":
        page.mouse.wheel(delta, 0)
    elif direction == "left":
        page.mouse.wheel(-delta, 0)
    else:
        raise ValueError(f"未知滚动方向: {direction}")
    return None


def _settle(page: Any, settle: SettleSpec) -> None:
    if settle.wait_for:
        resolved = resolve_lazy(page, settle.wait_for)
        resolved.locator.wait_for(state="visible", timeout=5000)
    if settle.wait_for_text:
        page.get_by_text(settle.wait_for_text).first.wait_for(state="visible", timeout=5000)
    if settle.network_idle:
        try:
            page.wait_for_load_state("networkidle", timeout=3000)
        except Exception:
            pass
    if settle.settle_ms and settle.settle_ms > 0:
        time.sleep(settle.settle_ms / 1000)


def _make_result(
    spec: ActionSpec,
    success: bool,
    start: float,
    error: str | None = None,
    resolved: ResolvedLocator | None = None,
) -> ActionResult:
    return ActionResult(
        type=spec.type.value,
        success=success,
        error=error,
        locator_strategy=resolved.strategy if resolved else (spec.locator.strategy.value if spec.locator else None),
        locator_value=resolved.value if resolved else (spec.locator.value if spec.locator else None),
        locator_match_count=resolved.match_count if resolved else 0,
        locator_stability=resolved.stability if resolved else (spec.locator.stability if spec.locator else None),
        duration_ms=int((time.monotonic() - start) * 1000),
    )
