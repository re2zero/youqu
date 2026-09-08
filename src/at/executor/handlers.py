from __future__ import annotations

import logging
import os
import re
import shlex
import signal
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from src.at.parser.models import SuiteActionStep

try:
    from src.custom_exception import ElementNotFound
except (ImportError, ModuleNotFoundError):

    class ElementNotFound(BaseException):
        """Fallback when custom_exception is unavailable."""

        pass


logger = logging.getLogger(__name__)


def resolve_ref(ref_name: str, elements: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if ref_name not in elements:
        raise ValueError(f"ref '{ref_name}' not found in elements registry")
    return elements[ref_name]


def get_mk(context: dict):
    if context.get("mk") is None:
        from src.mouse_key import MouseKey

        context["mk"] = MouseKey()
    return context["mk"]


def _bind_dog(app: str | None = None):
    from src.dogtail_utils import DogtailUtils

    if app and "/" in app:
        atspi_name = os.path.basename(app.split()[0])
    else:
        atspi_name = app
    return DogtailUtils(atspi_name) if atspi_name else DogtailUtils()


def get_dog(context: dict, app: str | None = None):
    if context.get("dog") is None:
        context["dog"] = _bind_dog(app)
        return context["dog"]
    dog = context["dog"]
    try:
        # AT-SPI 节点已失效（应用被 stopApp/重启后旧进程节点 dead）→
        # dogtail 在 dead 节点上 findChildren 静默返回空列表，导致元素
        # 误判为不存在。检测到 dead 时重新绑定当前进程。
        if dog.obj is None or dog.obj.dead:
            logger.warning("cached AT-SPI node dead (app restarted); rebinding dog")
            try:
                context["dog"] = _bind_dog(app)
            except BaseException as exc:
                # 应用可能尚未就绪，保留旧 dog，后续查找会再次触发重绑
                logger.warning("rebind dog failed: %s; keeping stale dog", exc)
    except BaseException:
        pass
    return context["dog"]


def ensure_window_focus(context: dict) -> None:
    """Focus the application window before AT-SPI element lookup."""
    app_name = context.get("app")
    if not app_name:
        return
    try:
        from src.button_center import ButtonCenter

        bc = ButtonCenter(app_name, None)
        bc.focus_windows(app_name)
    except Exception:
        pass


def resolve_step_attrs(step: SuiteActionStep, elements: dict) -> dict:
    if step.ref:
        attrs = dict(resolve_ref(step.ref, elements))
    else:
        attrs = {}

    if step.selector and not step.ref:
        if isinstance(step.selector, dict):
            attrs.update({k: v for k, v in step.selector.items() if v is not None})

    if step.x is not None:
        attrs.setdefault("x", step.x)
    if step.y is not None:
        attrs.setdefault("y", step.y)
    if step.items is not None:
        attrs["items"] = step.items

    return attrs


def _get_app_window_bounds(app_name: str) -> tuple[int, int, int, int] | None:
    """Get the bounds (x, y, width, height) of the first matching app window.

    Directly iterates the AT-SPI desktop tree to find the application and its
    top-level frame/window/dialog, then reads its screen coordinates.
    More robust than dogtail-based lookups because it always queries fresh
    AT-SPI state instead of relying on a potentially stale node reference.

    Reference: menu_utils._get_app_window_bounds()
    """
    try:
        import gi

        gi.require_version("Atspi", "2.0")
        from gi.repository import Atspi

        root = Atspi.get_desktop(0)
        for i in range(root.get_child_count()):
            try:
                app = root.get_child_at_index(i)
                if (app.get_name() or "") != app_name:
                    continue
                for j in range(app.get_child_count()):
                    try:
                        w = app.get_child_at_index(j)
                        role = w.get_role_name() or ""
                        if role in ("frame", "window", "dialog"):
                            ext = w.get_extents(Atspi.CoordType.SCREEN)
                            if ext.width > 0 and ext.height > 0:
                                return (ext.x, ext.y, ext.width, ext.height)
                    except Exception:
                        continue
            except Exception:
                continue
    except Exception:
        pass
    return None


def _node_role(node) -> str:
    try:
        return (getattr(node, "roleName", "") or "").strip()
    except BaseException:
        return ""


def _node_name(node) -> str:
    try:
        return (getattr(node, "name", "") or "").strip()
    except BaseException:
        return ""


def _select_child(parent_node, attrs):
    child_index = attrs.get("child_index")
    child_role = attrs.get("child_role")
    child_name = attrs.get("child_name")
    try:
        children = list(parent_node.children)
    except BaseException as exc:
        raise ElementNotFound(f"cannot read children: {exc}") from exc
    if child_role:
        children = [c for c in children if _node_role(c) == child_role]
    if child_name:
        children = [c for c in children if _node_name(c) == child_name]
    if not children:
        raise ElementNotFound(
            f"no matching child: child_role={child_role}, child_name={child_name}"
        )
    try:
        return children[int(child_index)]
    except IndexError:
        raise ElementNotFound(
            f"child_index {child_index} out of range (have {len(children)} children)"
        ) from IndexError
    except (TypeError, ValueError) as exc:
        raise ElementNotFound(f"invalid child_index: {exc}") from exc


def resolve_coordinates(attrs: dict, context: dict) -> tuple[int, int]:
    name = attrs.get("name")
    role = attrs.get("role")
    accessible_id = attrs.get("accessible_id")
    parent = attrs.get("parent")

    has_locator = name or role or accessible_id or parent

    if has_locator:
        try:
            dog = get_dog(context, context.get("app") or "")
            ensure_window_focus(context)

            if parent:
                element = _find_by_hierarchy(dog, attrs, attrs.get("index", 0))
                found = [element] if element else []
            elif accessible_id:
                found = dog.find_elements_by_accessible_id(accessible_id)
            elif name:
                found = dog.find_elements_by_attr(f"$//{name}/")
            elif role:
                from src.depends.dogtail.tree import predicate

                found = dog.obj.findChildren(
                    predicate.GenericPredicate(roleName=role), recursive=True
                )
            else:
                found = []

            if found:
                parent_node = None
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
                            parent_node = node
                            break
                    except BaseException:
                        pass
                if parent_node is None and found:
                    parent_node = found[0]

                if parent_node is not None:
                    if attrs.get("child_index") is not None:
                        parent_node = _select_child(parent_node, attrs)
                    try:
                        x, y, width, height = parent_node.extents
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
                        center = dog.element_center(parent_node)
                        if center and center[0] >= 0 and center[1] >= 0:
                            return center
                    except BaseException:
                        pass

            raise ElementNotFound(f"element not found, selector={attrs}")
        except ElementNotFound:
            raise
        except BaseException as exc:
            raise ElementNotFound(f"lookup error: {exc}, selector={attrs}") from exc

    if attrs.get("x") is not None and attrs.get("y") is not None:
        logger.warning(
            "coordinate fallback used (no AT-SPI locator matched): %s. "
            "This may cause test failures on different resolutions/layouts. "
            "Consider using elements.yaml to define element coordinates.",
            attrs
        )
        return attrs.get("x"), attrs.get("y")

    raise ElementNotFound(f"no locator and no coordinates: {attrs}")


def _find_by_hierarchy(dog, attrs, idx):
    """通过 parent-child 层级路径定位元素，用于同名元素消歧。"""
    parent_name = attrs.get("parent", "")
    parent_role = attrs.get("parent_role", "")
    child_name = attrs.get("name", "")
    child_role = attrs.get("role", "")

    if parent_name:
        parents = dog.find_elements_by_attr(f"$//{_escape_expr_name(parent_name)}/")
    elif parent_role:
        from src.depends.dogtail.tree import predicate

        parents = dog.obj.findChildren(
            predicate.GenericPredicate(roleName=parent_role), recursive=True
        )
    else:
        parents = [dog.obj] if dog.obj else []

    results = []
    if parents:
        from src.depends.dogtail.tree import predicate

        for p in parents:
            if child_name:
                children = p.findChildren(
                    predicate.GenericPredicate(name=child_name), recursive=True
                )
            elif child_role:
                children = p.findChildren(
                    predicate.GenericPredicate(roleName=child_role), recursive=True
                )
            else:
                children = []
            results.extend(children)

    if not results:
        raise ElementNotFound(f"hierarchy: parent={parent_name}, child={child_name}")
    try:
        return results[idx]
    except IndexError:
        raise ElementNotFound(
            f"hierarchy: parent={parent_name}, child={child_name}, idx={idx}"
        ) from IndexError


def _find_parent_element(dog, attrs, idx=0):
    name = attrs.get("name", "")
    role = attrs.get("role", "")
    accessible_id = attrs.get("accessible_id", "")
    parent = attrs.get("parent")

    if parent:
        return _find_by_hierarchy(dog, attrs, idx)
    if accessible_id:
        try:
            found = dog.find_elements_by_accessible_id(accessible_id)
            if found:
                # 同名 accessible_id 可能匹配到隐藏幽灵节点（残留窗口实例）。
                # 优先返回 showing 的节点，避免 idx=0 取到 extents=(0,0,0,0) 的
                # 隐藏节点导致坐标点击失效或被 showing 守卫拦截。
                for n in found:
                    try:
                        if n.showing:
                            return n
                    except BaseException:
                        continue
                try:
                    return found[idx]
                except IndexError:
                    pass
        except Exception:
            pass
    if name:
        expr = f"$//{_escape_expr_name(name)}/"
        return dog.find_element_by_attr(expr, idx)
    if role:
        from src.depends.dogtail.tree import predicate

        results = dog.obj.findChildren(predicate.GenericPredicate(roleName=role), recursive=True)
        if not results:
            raise ElementNotFound(f"role={role}")
        return results[idx]

    raise ElementNotFound("no name/role/accessible_id in element definition")


def find_element(dog, attrs, idx=0):
    element = _find_parent_element(dog, attrs, idx)
    if attrs.get("child_index") is not None:
        return _select_child(element, attrs)
    return element


# ---- Action Handlers ----


def _kill_running_app(app_name: str) -> None:
    if not app_name:
        return
    # 使用 pgrep（无 -f）仅按进程名匹配，避免匹配到命令行参数中包含 app_name 的框架进程自身
    pgrep = subprocess.run(
        ["pgrep", re.escape(app_name)],
        capture_output=True,
        text=True,
    )
    if not pgrep.stdout.strip():
        return
    own_pid = os.getpid()
    for pid in pgrep.stdout.strip().split():
        pid_int = int(pid)
        if pid_int == own_pid:
            continue
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


def handle_session_start(step: SuiteActionStep, context: dict) -> None:
    cmd = step.command or context.get("app", "")
    if not cmd:
        raise ValueError("session_start requires 'command' or app name")
    app_token = cmd.split()[0] if cmd else ""
    if app_token:
        _kill_running_app(os.path.basename(app_token) if "/" in app_token else app_token)
        time.sleep(0.5)
    if not any(c in cmd for c in "|&;><$`"):
        parts = cmd.split()
        if len(parts) == 1:
            cmd = shlex.quote(cmd)
    proc = subprocess.Popen(cmd, shell=True, start_new_session=True)
    context["app_process"] = proc


def handle_session_stop(step: SuiteActionStep, context: dict) -> None:
    proc = context.get("app_process")
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
    app = context.get("app", "")
    if app:
        pkill_name = os.path.basename(app) if "/" in app else app
        _kill_running_app(pkill_name)


def handle_keyboard_press(step: SuiteActionStep, context: dict) -> None:
    mk = get_mk(context)
    key = step.key if isinstance(step.key, str) else str(step.key or "")
    mk.press_key(key)


def handle_keyboard_hot_key(step: SuiteActionStep, context: dict) -> None:
    ensure_window_focus(context)
    mk = get_mk(context)
    keys = step.key
    if isinstance(keys, str):
        if "," in keys:
            key_list = [k.strip().lower() for k in keys.split(",") if k.strip()]
        else:
            parts = keys.split("+")
            # a trailing "+" is the plus key, not an empty segment
            if parts and parts[-1] == "":
                parts[-1] = "+"
            key_list = [k.strip().lower() for k in parts if k.strip()]
    elif isinstance(keys, list):
        key_list = [str(k).lower() for k in keys]
    else:
        key_list = [str(keys).lower()]
    mk.hot_key(*key_list)


def handle_keyboard_type(step: SuiteActionStep, context: dict) -> None:
    ensure_window_focus(context)
    mk = get_mk(context)
    mk.input_message(step.text or "")


def handle_mouse_click(step: SuiteActionStep, context: dict) -> None:
    mk = get_mk(context)
    attrs = resolve_step_attrs(step, context.get("elements", {}))
    x, y = resolve_coordinates(attrs, context)
    mk.click(x, y)


def handle_mouse_right_click(step: SuiteActionStep, context: dict) -> None:
    mk = get_mk(context)
    attrs = resolve_step_attrs(step, context.get("elements", {}))
    x, y = resolve_coordinates(attrs, context)
    mk.right_click(x, y)


def handle_mouse_double_click(step: SuiteActionStep, context: dict) -> None:
    mk = get_mk(context)
    attrs = resolve_step_attrs(step, context.get("elements", {}))
    x, y = resolve_coordinates(attrs, context)
    mk.double_click(x, y)


def handle_mouse_scroll(step: SuiteActionStep, context: dict) -> None:
    mk = get_mk(context)
    mk.mouse_scroll(step.value or 0)


def handle_mouse_drag(step: SuiteActionStep, context: dict) -> None:
    mk = get_mk(context)
    attrs = resolve_step_attrs(step, context.get("elements", {}))
    x, y = resolve_coordinates(attrs, context)
    mk.drag_to(x, y)


def _is_check_box(element) -> bool:
    try:
        role = getattr(element, "roleName", "") or ""
        if not role:
            role = element.get_role_name() or ""
        return "check box" in role.lower()
    except BaseException:
        return False


def _try_atspi_click(element, action: str, attrs: dict) -> bool:
    """Try to trigger an element via its AT-SPI action; True if triggered.

    DTK 对话框/菜单元素（DCheckBox、DSuggestButton 等）经 Qt AT-SPI 桥直接
    触发动作，不依赖屏幕坐标——规避坐标点击对对话框元素不可靠导致的
    "找到但没生效"（假通过）。任何候选 action 成功即返回 True；全部失败
    （控件无对应 action）返回 False，由调用方回退坐标点击。
    """
    candidates = {
        "click": ["Press", "toggle", "activate", "click", "press"],
        "right_click": ["Press", "click"],
        "double_click": ["Press", "click"],
    }.get(action, ["Press", "toggle", "activate", "click", "press"])
    tried = set()
    for name in candidates:
        if name in tried:
            continue
        tried.add(name)
        try:
            element.doActionNamed(name)
            logger.info("element_action via AT-SPI action %r (selector=%s)", name, attrs)
            return True
        except BaseException:
            continue
    return False


def _coordinate_click(element, action: str, attrs: dict) -> None:
    """坐标点击回退路径（AT-SPI action 不可用时）。

    带坐标守卫：拒绝点击 extents 全 0 的隐藏幽灵节点，避免误点屏幕左上角。
    """
    try:
        ex, ey, ew, eh = element.extents
        if ew <= 0 or eh <= 0 or (ex <= 0 and ey <= 0):
            raise ElementNotFound(
                f"element has no valid coordinates (extents={element.extents}), "
                f"refusing to click; selector={attrs}"
            )
    except ElementNotFound:
        raise
    except BaseException:
        pass
    if action == "click":
        try:
            element.click()
        except NotImplementedError:
            element.doActionNamed('click')
    elif action == "right_click":
        try:
            element.click(button=3)
        except NotImplementedError:
            element.doActionNamed('click')
    elif action == "double_click":
        try:
            element.doubleClick()
        except NotImplementedError:
            element.doActionNamed('click')


_ELEMENT_DO_WHITELIST = {"click", "right_click", "double_click", "focus", "point"}


def handle_element_action(step: SuiteActionStep, context: dict) -> None:
    app_name = context.get("app") or ""
    dog = get_dog(context, app_name)
    elements = context.get("elements") or {}

    attrs = resolve_step_attrs(step, elements)
    idx = attrs.get("index", 0)
    element = find_element(dog, attrs, idx)
    action = step.do or "click"
    if action not in _ELEMENT_DO_WHITELIST:
        raise ValueError(
            f"Unknown element action '{action}'. Supported: {sorted(_ELEMENT_DO_WHITELIST)}"
        )
    # 智能分派: accessible_id 定位到菜单项(关闭态)且要点击 → 自动菜单导航
    # (识别父菜单类型 → 打开菜单 → 键盘导航选择), 无需 dtk_dropdown_menu。
    if attrs.get("accessible_id"):
        try:
            from src.at.executor.intelligent import dispatch

            handled = dispatch(dog, attrs, action, context, element=element)
            if handled:
                return
        except ElementNotFound:
            raise
        except BaseException as exc:
            # 分派失败(如菜单导航不可用)时回退传统路径, 保留行为
            logger.warning("intelligent dispatch failed (%s); fallback", exc)
    if action in ("click", "right_click", "double_click"):
        # DCheckBox: AT-SPI action (Press/Toggle/SetFocus) 存在但实现为空
        # (假成功, 不真正 toggle), 直接坐标点击。
        if _is_check_box(element):
            _coordinate_click(element, action, attrs)
            return
        # 优先 AT-SPI action 触发（DTK 对话框/菜单元素经 Qt 桥直接触发，
        # 不依赖屏幕坐标，规避坐标点击对对话框元素不可靠导致的"假通过"）。
        # action 全部不可用时回退坐标点击（带坐标守卫）。
        if _try_atspi_click(element, action, attrs):
            return
        _coordinate_click(element, action, attrs)
        return
    if action == "focus":
        element.grabFocus()
    elif action == "point":
        dog.element_point(element)


def handle_element_set_value(step: SuiteActionStep, context: dict) -> None:
    app_name = context.get("app") or ""
    dog = get_dog(context, app_name)
    mk = get_mk(context)
    elements = context.get("elements") or {}

    attrs = resolve_step_attrs(step, elements)
    idx = attrs.get("index", 0)
    element = find_element(dog, attrs, idx)
    # 聚焦输入框: 优先 AT-SPI grabFocus（不依赖坐标，对 DTK 对话框 DLineEdit
    # 可靠），失败时回退坐标点击聚焦（带坐标守卫）。
    try:
        element.grabFocus()
    except BaseException:
        try:
            ex, ey, ew, eh = element.extents
            if ew > 0 and eh > 0 and not (ex <= 0 and ey <= 0):
                element.click()
        except BaseException:
            pass
    mk.input_message(step.text or "")


def handle_dtk_main_menu(step: SuiteActionStep, context: dict) -> None:
    from src.at.executor.menu_nav import AtMenuNavigator

    elements = context.get("elements") or {}
    attrs = resolve_step_attrs(step, elements)
    items = attrs.get("menu", []) or attrs.get("items", [])

    if not items:
        role = attrs.get("role", "")
        name = attrs.get("name", "")
        if name and "menu" in role.lower():
            items = [name]

    nav = AtMenuNavigator(context.get("app", ""), button_name=attrs.get("name") or "")
    nav.open_main_menu()
    if items:
        try:
            nav.select(items)
        except BaseException:
            nav.cancel()
            raise
    else:
        nav.cancel()
def handle_dtk_context_menu(step: SuiteActionStep, context: dict) -> None:
    from src.at.executor.menu_nav import AtMenuNavigator

    elements = context.get("elements") or {}
    attrs = resolve_step_attrs(step, elements)

    has_locator = (
        attrs.get("name") or attrs.get("role") or attrs.get("accessible_id") or attrs.get("parent")
    )
    has_coords = attrs.get("x") is not None and attrs.get("y") is not None
    if has_coords and not has_locator:
        logger.warning(
            "dtk_context_menu using pure coordinates without AT-SPI locator "
            "(quality_warning: coordinate_fallback): %s",
            attrs,
        )

    x, y = resolve_coordinates(attrs, context)
    items = attrs.get("menu", []) or attrs.get("items", [])

    if not items:
        role = attrs.get("role", "")
        name = attrs.get("name", "")
        if name and "menu" in role.lower():
            items = [name]

    nav = AtMenuNavigator(context.get("app", ""))
    if attrs.get("popup") == "click":
        # popup: click — 菜单由左键点击按钮弹出(如缩放箭头按钮), 非右键
        mk = get_mk(context)
        mk.click(x, y)
        time.sleep(0.2)
    else:
        nav.open_context_menu(x, y)
    if items:
        try:
            nav.select(items)
        except BaseException:
            # Dismiss the menu so the next spec doesn't see a stale menu
            nav.cancel()
            raise
    else:
        # No items to select — dismiss the unused menu
        nav.cancel()

def _menu_item_text_by_accessible_id(dog, accessible_id: str) -> str:
    """Resolve a menu item's display text from its objectName (accessible_id suffix).

    Qt6 bridge encodes QObject::objectName into the accessible_id dotted
    path suffix (e.g. '...DropdownMenu.UnixAction'); the same node's AT-SPI
    name is the display text ('Unix'). Menu items exist in the AT-SPI tree
    while their menu is CLOSED (persistent placeholders), so this lookup
    must happen before opening the menu. Returns "" when no match.
    """
    if not accessible_id:
        return ""
    try:
        nodes = dog.find_elements_by_accessible_id(accessible_id)
        for n in nodes:
            try:
                role = getattr(n, "roleName", "") or ""
                if "menu item" in role.lower() and getattr(n, "name", ""):
                    return n.name
            except BaseException:
                continue
    except BaseException:
        pass
    return ""


def handle_dtk_dropdown_menu(step: SuiteActionStep, context: dict) -> None:
    """Select an item from a DTK DDropdownMenu (bottom-bar dropdown).

    DDropdownMenu (used by deepin-editor for format/encoding/highlight
    selectors) pops its DMenu up on click; the popup menu items are NOT
    exposed to AT-SPI (verified: gi fresh query finds no menu item nodes
    while the menu is visibly open), so element_action by accessible_id
    cannot target them directly. The reliable path is:
      1. click the trigger button (persistent node, via selector/coords)
      2. keyboard-navigate the open DMenu (Up/Down + Return) via
         AtMenuNavigator — DMenu handles its own keyboard loop, no AT-SPI
         dependency.
    """
    app_name = context.get("app") or ""
    dog = get_dog(context, app_name)
    elements = context.get("elements") or {}

    attrs = resolve_step_attrs(step, elements)
    items = attrs.get("menu", []) or attrs.get("items", [])
    if not items:
        name = attrs.get("name", "")
        if name:
            items = [name]
    if not items:
        raise ValueError(
            "dtk_dropdown_menu requires items (menu item text or objectName "
            "suffix), selector={attrs}"
        )

    # items 若是 objectName 后缀(如 UnixAction), 菜单关闭态树里有对应节点
    # (accessible_id 后缀=objectName, name=显示文本)。在点触发按钮前反查
    # 显示文本 —— 菜单弹出后节点消失, 无法再查。
    resolved_items = []
    for item in items:
        text = _menu_item_text_by_accessible_id(dog, item)
        resolved_items.append(text if text else item)

    # 1. 点击触发按钮打开菜单
    trigger_attrs = {k: v for k, v in attrs.items() if k != "items" and k != "menu"}
    if trigger_attrs.get("name") or trigger_attrs.get("role") or trigger_attrs.get(
        "accessible_id"
    ) or trigger_attrs.get("parent") or trigger_attrs.get("x") is not None:
        try:
            idx = trigger_attrs.get("index", 0)
            element = find_element(dog, trigger_attrs, idx)
            element.click()
            time.sleep(0.5)
        except BaseException:
            # 触发按钮定位/点击失败时回退坐标
            x, y = resolve_coordinates(trigger_attrs, context)
            mk = get_mk(context)
            mk.click(x, y)
            time.sleep(0.5)
    else:
        raise ElementNotFound(f"dtk_dropdown_menu: no trigger locator: {attrs}")

    # 2. 键盘导航选择菜单项
    from src.at.executor.menu_nav import AtMenuNavigator

    nav = AtMenuNavigator(app_name)
    try:
        nav.select(resolved_items)
    except BaseException:
        nav.cancel()
        raise


def handle_dbus_call(step: SuiteActionStep, context: dict) -> None:
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


def handle_dbus_get_property(step: SuiteActionStep, context: dict) -> None:
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


def handle_wait(step: SuiteActionStep, context: dict) -> None:
    pass

def handle_file_dialog_select(step: SuiteActionStep, context: dict) -> None:
    """Select files in a native file dialog (deepin/UOS portal).

    Caller must trigger the file dialog opening first (e.g. click Import button
    or press Ctrl+O). Then this handler:

    Directory mode (path is a directory):
      1. Ctrl+L to focus path bar, Ctrl+A select all, Delete clear
      2. Types the directory path
      3. Presses Enter to navigate
      4. Ctrl+A to select all files
      5. Presses Enter to confirm

    File mode (path is a file):
      1. Ctrl+L to focus path bar, Ctrl+A select all, Delete clear
      2. Types the parent directory path
      3. Presses Enter to navigate into the directory
      4. Ctrl+L to focus path bar, Ctrl+A select all, Delete clear
      5. Types the filename
      6. Presses Enter to open the file
         (if dialog doesn't close, file type is unsupported)
    """
    import os
    import subprocess
    import time

    path = step.path or ""
    if not path:
        raise ValueError("file_dialog_select requires a 'path' argument")

    path = os.path.expanduser(path)
    # 目录模式: 目标目录不存在时先创建, 确保走目录模式 (否则 is_dir=False
    # 会误走 file 模式, 导致选择错误路径)。
    if not os.path.isdir(path):
        try:
            os.makedirs(path, exist_ok=True)
        except Exception:
            pass
    is_dir = os.path.isdir(path)

    # Wait for dialog to appear
    time.sleep(1.0)

    def _focus_and_clear():
        """Focus path bar (Ctrl+L) and clear existing text.

        多次尝试: DTK 集成的 QFileDialog 地址栏聚焦/清空可能滞后, 单次
        Ctrl+L+Ctrl+A+Delete 可能残留旧文本导致路径拼接。
        """
        for _ in range(2):
            subprocess.run(
                ["xdotool", "key", "--clearmodifiers", "ctrl+l"],
                capture_output=True, timeout=5
            )
            time.sleep(0.3)
            subprocess.run(
                ["xdotool", "key", "--clearmodifiers", "ctrl+a"],
                capture_output=True, timeout=5
            )
            time.sleep(0.1)
            subprocess.run(
                ["xdotool", "key", "--clearmodifiers", "Delete"],
                capture_output=True, timeout=5
            )
            time.sleep(0.2)

    def _type_and_enter(text: str):
        """Type text and press Enter."""
        subprocess.run(
            ["xdotool", "type", "--clearmodifiers", text],
            capture_output=True, timeout=5
        )
        time.sleep(0.3)
        subprocess.run(
            ["xdotool", "key", "--clearmodifiers", "Return"],
            capture_output=True, timeout=5
        )
        time.sleep(0.5)

    if is_dir:
        # Directory mode: navigate to dir, select all, confirm
        _focus_and_clear()
        _type_and_enter(path)
        # Select all files in the directory
        subprocess.run(
            ["xdotool", "key", "--clearmodifiers", "ctrl+a"],
            capture_output=True, timeout=5
        )
        time.sleep(0.3)
        # Press Enter to confirm
        subprocess.run(
            ["xdotool", "key", "--clearmodifiers", "Return"],
            capture_output=True, timeout=5
        )
        time.sleep(0.5)
    else:
        # File mode: navigate to parent dir, then type filename
        parent = os.path.dirname(path)
        filename = os.path.basename(path)
        _focus_and_clear()
        _type_and_enter(parent)
        # Now inside the directory — file list is focused.
        # Type the filename (dialog highlights the matching file), then Enter to open.
        subprocess.run(
            ["xdotool", "type", "--clearmodifiers", filename],
            capture_output=True, timeout=5
        )
        time.sleep(0.3)
        subprocess.run(
            ["xdotool", "key", "--clearmodifiers", "Return"],
            capture_output=True, timeout=5
        )
        time.sleep(0.5)

def handle_file_dialog_cancel(step: SuiteActionStep, context: dict) -> None:
    """Cancel the native file dialog by pressing Escape."""
    import subprocess
    import time

    time.sleep(0.5)
    subprocess.run(
        ["xdotool", "key", "--clearmodifiers", "Escape"],
        capture_output=True, timeout=5
    )
    time.sleep(1.0)


def handle_screenshot(step: SuiteActionStep, context: dict) -> None:
    from src.image_utils import ImageUtils

    try:
        mk = get_mk(context)
        w, h = mk.screen_size()
    except Exception:
        w, h = 1920, 1080
    ImageUtils.save_temporary_picture(0, 0, w, h)


def _escape_expr_name(name: str) -> str:
    """转义元素名中的 '/'，避免 __evalx 正则把 name 截断。

    元素名可含 '/'（如设置分组 "打开/保存设置"），而 __evalx 用
    ``.*?[^\\\\]/`` 解析 expr，未转义的 '/' 会被当作路径分隔符截断 name。
    转义为 ``\\/`` 后 __evalx 会还原为 '/'。
    """
    return name.replace("/", "\\/")


def _attrs_to_expr(attrs: dict) -> str:
    if not attrs:
        return "$/"
    # 优先使用 accessible_id
    accessible_id = attrs.get("accessible_id")
    if accessible_id:
        return f"$//[@accessible-id='{accessible_id}']/"
    # 支持 role+name 组合
    name = attrs.get("name", "")
    role = attrs.get("role", "")
    if name and role:
        return f"$//{_escape_expr_name(name)}[@role='{role}']/"
    if name:
        return f"$//{_escape_expr_name(name)}/"
    if role:
        return f"$//[role='{role}']/"
    return "$/"


def _assert_element_expr(step: SuiteActionStep, context: dict) -> str:
    elements = context.get("elements") or {}
    if step.ref and step.ref in elements:
        return _attrs_to_expr(elements[step.ref])
    if step.selector:
        return _attrs_to_expr(step.selector)
    return "$/"


def _assert_step_attrs(step: SuiteActionStep, context: dict) -> dict | None:
    elements = context.get("elements") or {}
    if step.ref and step.ref in elements:
        return dict(elements[step.ref])
    if step.selector:
        return {k: v for k, v in step.selector.items() if v is not None}
    return None


def handle_assert_element(step: SuiteActionStep, context: dict) -> None:
    import logging

    logger = logging.getLogger(__name__)
    dog = get_dog(context, context.get("app") or "")
    attrs = _assert_step_attrs(step, context)
    if attrs and attrs.get("accessible_id"):
        # accessible_id 断言: 用 get_accessible_id 通道 (支持菜单项关闭态)
        logger.info(f"断言元素存在(accessible_id)<{attrs['accessible_id']}>")
        if not dog.find_elements_by_accessible_id(attrs["accessible_id"]):
            raise AssertionError(
                f"元素不存在！！！accessible_id= <{attrs['accessible_id']}>"
            )
        return
    if attrs and attrs.get("child_index") is not None:
        logger.info(f"断言子元素存在<{attrs}>")
        try:
            find_element(dog, attrs, attrs.get("index", 0))
        except ElementNotFound as exc:
            raise AssertionError(f"子元素不存在！！！selector= <{attrs}>: {exc}")
        return
    expr = _assert_element_expr(step, context)
    logger.info(f"断言元素存在<{expr}>")
    if not dog.find_elements_by_attr(expr):
        raise AssertionError(f"元素不存在！！！expr= <{expr}>")


def handle_assert_not_exists(step: SuiteActionStep, context: dict) -> None:
    import logging

    dog = get_dog(context, context.get("app") or "")
    attrs = _assert_step_attrs(step, context)
    if attrs and attrs.get("accessible_id"):
        logger.info(f"断言元素不存在(accessible_id)<{attrs['accessible_id']}>")
        if dog.find_elements_by_accessible_id(attrs["accessible_id"]):
            raise AssertionError(
                f"元素不应存在！！！accessible_id= <{attrs['accessible_id']}>"
            )
        return
    if attrs and attrs.get("child_index") is not None:
        logger.info(f"断言子元素不存在<{attrs}>")
        try:
            found = find_element(dog, attrs, attrs.get("index", 0))
        except ElementNotFound:
            return
        raise AssertionError(f"子元素不应存在！！！selector= <{attrs}>: {found}")
    expr = _assert_element_expr(step, context)
    logger.info(f"断言元素不存在<{expr}>")
    try:
        dog.find_element_by_attr(expr)
        raise AssertionError(f"元素不应存在！！！expr= <{expr}>")
    except AssertionError:
        raise
    except Exception:
        pass


def handle_assert_window(step: SuiteActionStep, context: dict) -> None:
    app = step.app or context.get("app", "")
    dog = get_dog(context, app)
    ensure_window_focus(context)

    from src.depends.dogtail.tree import predicate

    frames = dog.obj.findChildren(predicate.GenericPredicate(roleName="frame"), recursive=True)
    if not frames:
        frames = dog.obj.findChildren(predicate.GenericPredicate(roleName="window"), recursive=True)
    if not frames:
        raise AssertionError(f"未找到应用 {app} 的窗口")

    pattern = step.name_pattern
    if pattern and pattern != app:
        matched = [f for f in frames if pattern.lower() in (f.name or "").lower()]
        if not matched:
            raise AssertionError(f"应用 {app} 窗口存在但名称不匹配 pattern={pattern}")


def _parse_window_count_expected(expected):
    """解析窗口数量断言期望。返回 (op, value)：
    纯数字 → (None, int) 表示严格相等（走 assert_window_amount）；
    ">2"/"<1"/">="/"<="/"=>" → (op, int)。
    """
    text = str(expected).strip()
    for op in (">=", "<=", ">", "<", "=="):
        if text.startswith(op):
            try:
                return op, int(text[len(op):].strip())
            except ValueError:
                raise ValueError(f"无效的窗口数量断言期望: {expected!r}")
    try:
        return None, int(text)
    except ValueError:
        raise ValueError(f"无效的窗口数量断言期望: {expected!r}")


def _compare_window_count(actual, op, value):
    return {
        ">": actual > value,
        "<": actual < value,
        ">=": actual >= value,
        "<=": actual <= value,
        "==": actual == value,
    }[op]


def handle_assert_window_count(step: SuiteActionStep, context: dict) -> None:
    from src.assert_common import AssertCommon
    from src.button_center import ButtonCenter

    app = step.app or context.get("app", "")
    expected = step.expected or 1

    op, value = _parse_window_count_expected(expected)
    if op is None:
        AssertCommon.assert_window_amount(app, value)
        return

    actual = ButtonCenter(app_name=app, config_path="xxx").get_windows_number(app)
    if not _compare_window_count(actual, op, value):
        raise AssertionError(f"断言应用窗口数量{app}为{actual}不满足{op}{value}")


def handle_assert_process_running(step: SuiteActionStep, context: dict) -> None:
    from src.assert_common import AssertCommon

    app = step.app or step.value or context.get("app", "")
    AssertCommon.assert_process_status(True, app)


def handle_assert_process_not_running(step: SuiteActionStep, context: dict) -> None:
    from src.assert_common import AssertCommon

    app = step.app or step.value or context.get("app", "")
    AssertCommon.assert_process_status(False, app)


def handle_assert_file_exists(step: SuiteActionStep, context: dict) -> None:
    from src.assert_common import AssertCommon

    path = step.path or step.value or ""
    AssertCommon.assert_file_exist(path)


def handle_assert_file_not_exists(step: SuiteActionStep, context: dict) -> None:
    from src.assert_common import AssertCommon

    path = step.path or step.value or ""
    AssertCommon.assert_file_not_exist(path)


def handle_assert_image_exists(step: SuiteActionStep, context: dict) -> None:
    from src.assert_common import AssertCommon

    path = step.path or step.value or ""
    AssertCommon.assert_image_exist(path)


def handle_assert_image_not_exists(step: SuiteActionStep, context: dict) -> None:
    from src.assert_common import AssertCommon

    path = step.path or step.value or ""
    AssertCommon.assert_image_not_exist(path)


def handle_assert_ocr_exists(step: SuiteActionStep, context: dict) -> None:
    from src.assert_common import AssertCommon

    text = step.value or step.expected or ""
    AssertCommon.assert_ocr_exist(str(text))


def handle_assert_ocr_not_exists(step: SuiteActionStep, context: dict) -> None:
    from src.assert_common import AssertCommon

    text = step.value or step.expected or ""
    AssertCommon.assert_ocr_not_exist(str(text))

def handle_assert_vlm_reference(step: SuiteActionStep, context: dict) -> None:
    """VLM reference-image assertion: compose expected vs actual, judge visually.

    Fields:
      path    — reference image (expected state), relative to suite dir or absolute
      text    — assertion feature description (what state is being verified)
      expected— judgment mode: "strict" (default, any style diff => FAIL)
                or "tolerant" (only specified feature matters)
    """
    from src.vlm.config import VLMConfig
    from src.vlm.vlm_locator import create_vlm_locator

    config = VLMConfig()
    if not config.is_available():
        raise AssertionError(
            "assert_vlm_reference: VLM 未启用 (VLM_ENABLED=false) 或无 httpx"
        )
    locator = create_vlm_locator(config)
    if not locator.is_available():
        raise AssertionError(
            f"assert_vlm_reference: VLM 服务不可用 ({config.backend.base_url})"
        )

    ref_path = step.path or step.value or ""
    if not ref_path:
        raise AssertionError("assert_vlm_reference: 缺少 reference 图片 (path 字段)")
    if not os.path.isabs(ref_path):
        base = Path(context.get("suite_dir") or context.get("cwd") or os.getcwd())
        candidate = base / ref_path
        if not candidate.is_file():
            # Suite files live in <output>/<module>/ while references/
            # live at the output root — search upward like _load_elements.
            for parent in base.parents:
                p = parent / ref_path
                if p.is_file():
                    candidate = p
                    break
        ref_path = str(candidate)
    if not os.path.exists(ref_path):
        raise AssertionError(f"assert_vlm_reference: 参考图不存在: {ref_path}")

    feature_raw = step.text or step.prompt or "界面整体状态"
    feature = feature_raw
    mode = str(step.expected or "strict").lower()
    if "|" in feature_raw:
        parts = feature_raw.split("|")
        feature = parts[0].strip()
        mode = parts[1].strip().lower()
    if mode not in ("strict", "tolerant"):
        mode = "strict"

    # 1. capture actual screen
    from src.vlm.screenshot import capture_screen
    import io

    raw = capture_screen()
    if not raw:
        raise AssertionError("assert_vlm_reference: 无法截取屏幕")
    actual_path = os.path.join(
        config.evidence_dir, f"vlm_ref_actual_{int(time.time())}.png"
    )
    from PIL import Image

    Image.open(io.BytesIO(raw)).convert("RGB").save(actual_path)

    # 2. judge via VLM (compose inside locator)
    result = locator.evaluate_with_reference(
        reference_path=ref_path,
        actual_path=actual_path,
        feature=feature,
        mode=mode,
        ignore_patterns=step.ignore,
    )
    if result is None:
        raise AssertionError("assert_vlm_reference: VLM 返回空结果")

    logger.info(
        "VLM 参考图断言: verdict=%s confidence=%.2f feature=%s reason=%s",
        result.verdict,
        result.confidence,
        feature,
        result.reason,
    )
    if result.verdict == "UNSURE" or result.confidence < 0.6:
        raise AssertionError(
            f"VLM 参考图断言不确定 (confidence={result.confidence:.2f}, UNSURE): "
            f"feature={feature} reason={result.reason} evidence={actual_path}"
        )
    if result.verdict == "FAIL":
        raise AssertionError(
            f"VLM 参考图断言失败: feature={feature} reason={result.reason} "
            f"evidence={actual_path}"
        )

HANDLERS: dict[str, Callable[[SuiteActionStep, dict], None]] = {
    "session_start": handle_session_start,
    "session_stop": handle_session_stop,
    "keyboard_press": handle_keyboard_press,
    "keyboard_hot_key": handle_keyboard_hot_key,
    "keyboard_type": handle_keyboard_type,
    "keyboard_type_text": handle_keyboard_type,
    "mouse_click": handle_mouse_click,
    "mouse_right_click": handle_mouse_right_click,
    "mouse_double_click": handle_mouse_double_click,
    "mouse_scroll": handle_mouse_scroll,
    "mouse_drag": handle_mouse_drag,
    "element_action": handle_element_action,
    "element_set_value": handle_element_set_value,
    "dtk_main_menu": handle_dtk_main_menu,
    "dtk_context_menu": handle_dtk_context_menu,
    "dtk_dropdown_menu": handle_dtk_dropdown_menu,
    "dbus_call": handle_dbus_call,
    "dbus_get_property": handle_dbus_get_property,
    "file_dialog_select": handle_file_dialog_select,
    "file_dialog_cancel": handle_file_dialog_cancel,
    "screenshot": handle_screenshot,
    "assert_element": handle_assert_element,
    "assert_not_exists": handle_assert_not_exists,
    "assert_window": handle_assert_window,
    "assert_window_count": handle_assert_window_count,
    "assert_process_running": handle_assert_process_running,
    "assert_process_not_running": handle_assert_process_not_running,
    "assert_file_exists": handle_assert_file_exists,
    "assert_file_not_exists": handle_assert_file_not_exists,
    "assert_image_exists": handle_assert_image_exists,
    "assert_image_not_exists": handle_assert_image_not_exists,
    "assert_ocr_exists": handle_assert_ocr_exists,
    "assert_ocr_not_exists": handle_assert_ocr_not_exists,
    "assert_vlm_reference": handle_assert_vlm_reference,
}
