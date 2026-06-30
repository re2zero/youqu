# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only
"""Step executor — dispatches YAML action steps to YouQu API calls.

Converts Selector models to YouQu AT-SPI expr strings, then calls
DogtailUtils, MouseKey, DbusUtils, or MenuNavigator as appropriate.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import re
import signal
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from src.yaml_test.elements import resolve_ref
from src.yaml_test.parser import ActionStep, AssertStep, TestCase


def selector_to_expr(selector: Any) -> str:
    """Convert a Selector dict or model to a YouQu AT-SPI expr string.

    YouQu expr format: $-prefixed, /-separated, trailing /.
    $//name/ recursively searches all descendants for elements matching name.

    >>> selector_to_expr({"name": "OK"})
    '$//OK/'
    >>> selector_to_expr({})
    '$/'
    """
    if selector is None:
        return "$/"

    if hasattr(selector, "model_dump"):
        sel = selector.model_dump(exclude_none=True)
    elif isinstance(selector, dict):
        sel = {k: v for k, v in selector.items() if v is not None}
    else:
        return "$/"

    name = sel.get("name", "")
    if name:
        return f"$//{name}/"
    return "$/"


def _find_element(dog, attrs, idx=0):
    name = attrs.get("name", "")
    role = attrs.get("role", "")
    if name:
        expr = f"$//{name}/"
        return dog.find_element_by_attr(expr, idx)
    if role:
        from src.depends.dogtail.tree import predicate

        results = dog.obj.findChildren(
            predicate.GenericPredicate(roleName=role), recursive=True
        )
        if not results:
            from src.custom_exception import ElementNotFound

            raise ElementNotFound(f"role={role}")
        return results[idx]
    from src.custom_exception import ElementNotFound

    raise ElementNotFound("no name or role in element definition")


def _resolve_step_attrs(step: ActionStep, elements: dict) -> dict:
    """Resolve step.ref to element attributes dict, then merge step-level fields.

    Resolution order (later values win):
    1. ``step.ref`` looked up in elements.yaml (provides base attrs)
    2. Step-level inline fields: ``x``, ``y``, ``items``, ``menu``,
       ``selector``, ``do``, ``text``, ``keys``, ``command``,
       ``amount``, ``value``

    Use ``step.ref`` for AT-SPI selectors + coordinates from the registry,
    and step-level ``items``/``menu`` for the keyboard navigation path.
    """
    if step.ref:
        attrs = dict(resolve_ref(step.ref, elements))
    else:
        attrs = {}

    click_target = attrs.pop("click_target", None)
    if click_target and isinstance(click_target, str):
        target_el = resolve_ref(click_target, elements)
        tx = target_el.get("x")
        ty = target_el.get("y")
        if tx is not None:
            attrs.setdefault("x", tx)
        if ty is not None:
            attrs.setdefault("y", ty)
        if not (tx is not None and ty is not None):
            attrs.setdefault("click_target", click_target)

    sel = step.selector
    if sel is not None and not step.ref:
        if hasattr(sel, "model_dump"):
            attrs.update({k: v for k, v in sel.model_dump(exclude_none=True).items() if v is not None})
        elif isinstance(sel, dict):
            attrs.update({k: v for k, v in sel.items() if v is not None})

    if step.x is not None:
        attrs.setdefault("x", step.x)
    if step.y is not None:
        attrs.setdefault("y", step.y)
    if step.items is not None:
        attrs["items"] = step.items

    extras = getattr(step, "model_extra", {}) or {}
    for key in ("duration", "key", "desc"):
        val = extras.get(key)
        if val is not None:
            attrs.setdefault(key, val)
    menu_val = extras.get("menu")
    if menu_val is not None:
        attrs["menu"] = menu_val

    click_target = extras.get("click_target")
    if click_target and isinstance(click_target, str):
        attrs.setdefault("click_target", click_target)

    attrs.setdefault("x", None)
    attrs.setdefault("y", None)
    return attrs


def _resolve_coordinates(attrs: dict, context: dict) -> tuple[int, int]:
    """Resolve (x, y): prefer AT-SPI dynamic center, fall back to hardcoded coords."""
    name = attrs.get("name")
    role = attrs.get("role")
    accessible_id = attrs.get("accessible_id")

    click_target = attrs.get("click_target")
    if click_target and isinstance(click_target, str):
        elements = context.get("elements", {})
        target_attrs = resolve_ref(click_target, elements)
        name = name or target_attrs.get("name")
        role = role or target_attrs.get("role")

    if name or role or accessible_id:
        try:
            dog = _get_dog(context, context.get("app") or "")
            _ensure_window_focus(context)
            if name:
                found = dog.find_elements_by_attr(f"$//{name}/")
            elif role:
                from src.depends.dogtail.tree import predicate
                found = dog.obj.findChildren(
                    predicate.GenericPredicate(roleName=role), recursive=True
                )
            else:
                found = []
            if found:
                for node in found:
                    try:
                        x, y, width, height = node.extents
                        center = (x + width / 2, y + height / 2)
                        if (
                            center
                            and center[0] >= 0
                            and center[1] >= 0
                            and width is not None
                            and height is not None
                            and width > 0
                            and height > 0
                        ):
                            return center
                    except BaseException:
                        pass
                try:
                    center = dog.element_center(found[0])
                    if center and center[0] >= 0 and center[1] >= 0:
                        return center
                except BaseException:
                    pass
        except BaseException:
            pass

    if attrs.get("x") is not None and attrs.get("y") is not None:
        return attrs.get("x"), attrs.get("y")

    try:
        dog = _get_dog(context, context.get("app") or "")
        node = dog.obj[0] if isinstance(dog.obj, list) else dog.obj
        x, y, width, height = node.extents
        center = (x + width / 2, y + height / 2)
        if center and center[0] >= 0 and center[1] >= 0:
            return center
    except BaseException:
        pass

    return attrs.get("x") or 0, attrs.get("y") or 0


def _ensure_window_focus(context: dict):
    app_name = context.get("app")
    if not app_name:
        return
    try:
        from src.button_center import ButtonCenter

        bc = ButtonCenter(app_name, None)
        bc.focus_windows(app_name)
    except Exception:
        pass


@dataclass
class ExecutorResult:
    """Result of executing a TestCase."""

    passed: bool = True
    message: str = ""
    step_index: int = -1
    errors: list[str] = field(default_factory=list)


def _get_mk(context: dict):
    if context.get("mk") is None:
        from src.mouse_key import MouseKey

        context["mk"] = MouseKey()
    return context["mk"]


def _get_dog(context: dict, app: str | None = None):
    if context.get("dog") is None:
        from src.dogtail_utils import DogtailUtils

        if app and "/" in app:
            atspi_name = os.path.basename(app)
        else:
            atspi_name = app
        context["dog"] = DogtailUtils(atspi_name) if atspi_name else DogtailUtils()
    return context["dog"]


def _handle_session_start(step: ActionStep, context: dict) -> None:
    cmd = step.command or context.get("app", "")
    if not cmd:
        raise ValueError("session_start requires 'command' or app name")
    context["app"] = cmd
    if not any(c in cmd for c in "|&;><$`"):
        parts = cmd.split()
        if len(parts) == 1:
            cmd = shlex.quote(cmd)
    proc = subprocess.Popen(
        cmd,
        shell=True,
        start_new_session=True,
    )
    context["app_process"] = proc


def _handle_session_stop(step: ActionStep, context: dict) -> None:
    proc = context.get("app_process")
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
    # Always pkill by app name to handle single-instance apps (e.g. DTK DBus
    # Use pgrep to find PIDs by cmdline, then kill them directly.
    # Filter out python3 (test script) and sh (shell wrapper) to avoid
    # killing ourselves. Exclude our own PID as well.
    app = context.get("app", "")
    if app:
        pkill_name = os.path.basename(app) if "/" in app else app
        pgrep = subprocess.run(
            ["pgrep", "-f", re.escape(pkill_name)],
            capture_output=True, text=True,
        )
        if pgrep.stdout.strip():
            own_pid = os.getpid()
            for pid in pgrep.stdout.strip().split():
                pid_int = int(pid)
                if pid_int == own_pid:
                    continue
                # Read comm to skip python3 (test script) and sh (shell wrapper)
                try:
                    comm = open(f"/proc/{pid_int}/comm").read().strip()
                except (FileNotFoundError, PermissionError):
                    continue
                if comm in ("python3", "python", "sh", "bash"):
                    continue
                try:
                    os.kill(pid_int, signal.SIGKILL)
                except ProcessLookupError:
                    pass


def _handle_keyboard_press(step: ActionStep, context: dict) -> None:
    mk = _get_mk(context)
    key = step.keys if isinstance(step.keys, str) else str(step.keys or "")
    mk.press_key(key)


def _handle_keyboard_hot_key(step: ActionStep, context: dict) -> None:
    mk = _get_mk(context)
    keys = step.keys
    if isinstance(keys, str):
        key_list = [k.strip() for k in keys.split(",") if k.strip()]
    elif isinstance(keys, list):
        key_list = [str(k) for k in keys]
    else:
        key_list = [str(keys)]
    mk.hot_key(*key_list)


def _handle_keyboard_type(step: ActionStep, context: dict) -> None:
    mk = _get_mk(context)
    mk.input_message(step.text or "")


def _handle_mouse_click(step: ActionStep, context: dict) -> None:
    mk = _get_mk(context)
    attrs = _resolve_step_attrs(step, context.get("elements", {}))
    x, y = _resolve_coordinates(attrs, context)
    mk.click(x, y)


def _handle_mouse_right_click(step: ActionStep, context: dict) -> None:
    mk = _get_mk(context)
    attrs = _resolve_step_attrs(step, context.get("elements", {}))
    x, y = _resolve_coordinates(attrs, context)
    mk.right_click(x, y)


def _handle_mouse_double_click(step: ActionStep, context: dict) -> None:
    mk = _get_mk(context)
    attrs = _resolve_step_attrs(step, context.get("elements", {}))
    x, y = _resolve_coordinates(attrs, context)
    mk.double_click(x, y)


def _handle_mouse_scroll(step: ActionStep, context: dict) -> None:
    mk = _get_mk(context)
    mk.mouse_scroll(step.amount or 0)


def _handle_mouse_drag(step: ActionStep, context: dict) -> None:
    mk = _get_mk(context)
    attrs = _resolve_step_attrs(step, context.get("elements", {}))
    x, y = _resolve_coordinates(attrs, context)
    mk.drag_to(x, y)


def _handle_element_action(step: ActionStep, context: dict) -> None:
    app_name = context.get("app") or ""
    dog = _get_dog(context, app_name)
    elements = context.get("elements") or {}

    attrs = _resolve_step_attrs(step, elements)
    idx = attrs.get("index", 0)
    element = _find_element(dog, attrs, idx)
    action = step.do or "click"
    if action == "click":
        element.click()
    elif action == "right_click":
        element.click(button=3)
    elif action == "middle_click":
        element.click(button=2)
    elif action == "double_click":
        element.doubleClick()
    elif action == "point":
        dog.element_point(element)
    elif action == "focus":
        element.grabFocus()
    else:
        method = getattr(element, action, None)
        if callable(method):
            method()
        else:
            raise ValueError(f"Unknown element action: {action}")


def _handle_element_set_value(step: ActionStep, context: dict) -> None:
    app_name = context.get("app") or ""
    dog = _get_dog(context, app_name)
    mk = _get_mk(context)
    elements = context.get("elements") or {}

    attrs = _resolve_step_attrs(step, elements)
    idx = attrs.get("index", 0)
    element = _find_element(dog, attrs, idx)
    element.click()
    mk.input_message(step.text or "")


def _handle_main_menu_comb(step: ActionStep, context: dict) -> None:
    try:
        from src.menu_nav import MenuNavigator
    except ImportError as e:
        raise ImportError(f"menu_nav module not available: {e}") from e

    elements = context.get("elements") or {}
    attrs = _resolve_step_attrs(step, elements)
    items = attrs.get("menu", []) or attrs.get("items", [])

    if not items:
        role = attrs.get("role", "")
        name = attrs.get("name", "")
        if name and "menu" in role.lower():
            items = [name]

    nav = MenuNavigator(context.get("app"))
    nav.open_main_menu()
    if items:
        nav.select(items)


def _handle_context_menu_comb(step: ActionStep, context: dict) -> None:
    try:
        from src.menu_nav import MenuNavigator
    except ImportError as e:
        raise ImportError(f"menu_nav module not available: {e}") from e

    elements = context.get("elements") or {}
    attrs = _resolve_step_attrs(step, elements)
    x, y = _resolve_coordinates(attrs, context)
    items = attrs.get("menu", []) or attrs.get("items", [])

    if not items:
        role = attrs.get("role", "")
        name = attrs.get("name", "")
        if name and "menu" in role.lower():
            items = [name]

    nav = MenuNavigator(context.get("app"))
    nav.open_context_menu(x, y)
    if items:
        nav.select(items)


def _handle_dbus_call(step: ActionStep, context: dict) -> None:
    from src.dbus_utils import DbusUtils

    v = step.value if isinstance(step.value, dict) else {}
    dog = DbusUtils(
        v.get("dbus_name", ""),
        v.get("object_path", ""),
        v.get("interface", ""),
    )
    bus_type = v.get("bus_type", "session")
    if bus_type == "system":
        methods = dog.system_object_methods()
    else:
        methods = dog.session_object_methods()
    method_name = v.get("method", "")
    args = v.get("args", [])
    method = getattr(methods, method_name, None)
    if callable(method):
        method(*args)
    else:
        raise ValueError(f"Unknown DBus method: {method_name}")


def _handle_dbus_get_property(step: ActionStep, context: dict) -> None:
    from src.dbus_utils import DbusUtils

    v = step.value if isinstance(step.value, dict) else {}
    dog = DbusUtils(
        v.get("dbus_name", ""),
        v.get("object_path", ""),
        v.get("interface", ""),
    )
    prop = v.get("property", "")
    bus_type = v.get("bus_type", "session")
    if bus_type == "system":
        dog.get_system_properties_value(prop)
    else:
        dog.get_session_properties_value(prop)


def _handle_wait(step: ActionStep, context: dict) -> None:
    pass


def _handle_screenshot(step: ActionStep, context: dict) -> None:
    from src.image_utils import ImageUtils

    try:
        mk = _get_mk(context)
        w, h = mk.screen_size()
    except Exception:
        w, h = 1920, 1080
    ImageUtils.save_temporary_picture(0, 0, w, h)


ACTION_HANDLERS: dict[str, Callable[[ActionStep, dict], None]] = {
    "session_start": _handle_session_start,
    "session_stop": _handle_session_stop,
    "keyboard_press": _handle_keyboard_press,
    "keyboard_hot_key": _handle_keyboard_hot_key,
    "keyboard_type": _handle_keyboard_type,
    "keyboard_type_text": _handle_keyboard_type,
    "mouse_click": _handle_mouse_click,
    "mouse_right_click": _handle_mouse_right_click,
    "mouse_double_click": _handle_mouse_double_click,
    "mouse_scroll": _handle_mouse_scroll,
    "mouse_drag": _handle_mouse_drag,
    "element_action": _handle_element_action,
    "element_set_value": _handle_element_set_value,
    "main_menu_comb": _handle_main_menu_comb,
    "context_menu_comb": _handle_context_menu_comb,
    "dbus_call": _handle_dbus_call,
    "dbus_get_property": _handle_dbus_get_property,
    "wait": _handle_wait,
    "screenshot": _handle_screenshot,
}

_LIFECYCLE_ACTIONS = frozenset({"session_start", "session_stop"})


def _extract_selector_from_step(
    step: ActionStep, elements: dict
) -> dict | None:
    if step.ref:
        attrs = resolve_ref(step.ref, elements)
        name = attrs.get("name")
        role = attrs.get("role")
        if name or role:
            return {"name": name, "role": role}
    if step.selector is not None:
        d = step.selector.model_dump(exclude_none=True)
        if d.get("name") or d.get("role"):
            return d
    return None


def _extract_selector_from_assert(
    assert_step: AssertStep, elements: dict
) -> dict | None:
    if assert_step.type not in (
        "element_visible",
        "element_not_visible",
        "element_numbers",
        "element_text",
    ):
        return None
    if assert_step.ref:
        attrs = resolve_ref(assert_step.ref, elements)
        name = attrs.get("name")
        role = attrs.get("role")
        if name or role:
            return {"name": name, "role": role}
    if assert_step.selector is not None:
        d = assert_step.selector.model_dump(exclude_none=True)
        if d.get("name") or d.get("role"):
            return d
    return None


def _peek_next_selector(
    step: ActionStep,
    idx: int,
    all_steps: list[tuple[str, ActionStep]],
    elements: dict,
) -> dict | None:
    for assert_step in step.assert_steps:
        sel = _extract_selector_from_assert(assert_step, elements)
        if sel:
            return sel

    if idx + 1 < len(all_steps):
        _, next_step = all_steps[idx + 1]
        if next_step.action in _LIFECYCLE_ACTIONS:
            return None
        if next_step.wait_for:
            return None
        sel = _extract_selector_from_step(next_step, elements)
        if sel:
            return sel

    return None


def _smart_wait(
    target: dict, timeout_s: float, context: dict
) -> bool:
    name = target.get("name")
    role = target.get("role")
    if not name and not role:
        time.sleep(timeout_s)
        return False

    expr = f"$//{name}/" if name else "$/"
    if expr == "$/":
        time.sleep(timeout_s)
        return False

    dog = _get_dog(context, context.get("app") or "")

    deadline = time.time() + timeout_s
    interval = 0.2
    while time.time() < deadline:
        try:
            found = dog.find_elements_by_attr(expr)
            if found:
                return True
        except Exception:
            pass
        time.sleep(interval)
    return False


class StepExecutor:
    """Executes a parsed TestCase through the YouQu API."""

    def __init__(self, testcase: TestCase):
        self.testcase = testcase
        self.context: dict[str, Any] = {
            "app": testcase.app,
            "mk": None,
            "dog": None,
            "app_process": None,
            "elements": testcase.elements,
        }

    def run(self) -> ExecutorResult:
        result = ExecutorResult()
        all_steps = [
            ("setup", s) for s in self.testcase.setup
        ] + [
            ("steps", s) for s in self.testcase.steps
        ]
        for idx, (phase, step) in enumerate(all_steps):
            step_result = self._execute_step(step, idx, all_steps)
            if not step_result.passed:
                result.passed = False
                result.message = step_result.message
                result.step_index = idx
                result.errors.extend(step_result.errors)
                break

        for tear in self.testcase.teardown:
            try:
                handler = ACTION_HANDLERS.get(tear.action)
                if handler:
                    handler(tear, self.context)
                if tear.wait:
                    time.sleep(tear.wait)
                if tear.wait_after:
                    time.sleep(tear.wait_after / 1000.0)
            except Exception:
                pass
        return result

    def _execute_step(
        self, step: ActionStep, idx: int,
        all_steps: list[tuple[str, ActionStep]] | None = None,
    ) -> ExecutorResult:
        result = ExecutorResult(step_index=idx)
        step_label = step.name or step.action

        if step.wait_for:
            from src.yaml_test.wait import wait_for

            sel_dict = step.wait_for.selector.model_dump(exclude_none=True)
            found = wait_for(
                sel_dict,
                timeout=step.wait_for.timeout,
                interval=step.wait_for.interval,
            )
            if not found:
                result.passed = False
                result.message = (
                    f"Step [{step_label}]: wait_for timed out "
                    f"({step.wait_for.timeout}ms)"
                )
                return result

        handler = ACTION_HANDLERS.get(step.action)
        if handler is None:
            result.passed = False
            result.message = f"Step [{step_label}]: unknown action '{step.action}'"
            return result

        try:
            handler(step, self.context)
        except Exception as exc:
            result.passed = False
            result.message = f"Step [{step_label}] action '{step.action}' failed: {exc}"
            return result

        if step.wait:
            if all_steps is not None:
                target = _peek_next_selector(
                    step, idx, all_steps, self.context.get("elements", {}),
                )
                if target:
                    _smart_wait(target, step.wait, self.context)
                else:
                    time.sleep(step.wait)
            else:
                time.sleep(step.wait)

        for assert_step in step.assert_steps:
            try:
                from src.yaml_test.assertions import run_assert

                run_assert(assert_step, self.context.get("elements"))
            except AssertionError as exc:
                result.passed = False
                result.message = (
                    f"Step [{step_label}] assert '{assert_step.type}' failed: {exc}"
                )
                return result
            except ValueError as exc:
                result.passed = False
                result.message = str(exc)
                return result

        if step.wait_after:
            time.sleep(step.wait_after / 1000.0)

        return result
