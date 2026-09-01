from __future__ import annotations

import logging
import os
import re
import shlex
import signal
import subprocess
import time
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


def get_dog(context: dict, app: str | None = None):
    if context.get("dog") is None:
        from src.dogtail_utils import DogtailUtils

        if app and "/" in app:
            atspi_name = os.path.basename(app.split()[0])
        else:
            atspi_name = app
        context["dog"] = DogtailUtils(atspi_name) if atspi_name else DogtailUtils()
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
        parents = dog.find_elements_by_attr(f"$//{parent_name}/")
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
                try:
                    return found[idx]
                except IndexError:
                    pass
        except Exception:
            pass
    if name:
        expr = f"$//{name}/"
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
        sep = "+" if "+" in keys else ","
        key_list = [k.strip().lower() for k in keys.split(sep) if k.strip()]
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
    elif action == "focus":
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
    element.click()
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
    is_dir = os.path.isdir(path)

    # Wait for dialog to appear
    time.sleep(1.0)

    def _focus_and_clear():
        """Focus path bar (Ctrl+L) and clear existing text."""
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
        time.sleep(0.1)

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
        return f"$//{name}[@role='{role}']/"
    if name:
        return f"$//{name}/"
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

    logger = logging.getLogger(__name__)
    dog = get_dog(context, context.get("app") or "")
    attrs = _assert_step_attrs(step, context)
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


def handle_assert_window_count(step: SuiteActionStep, context: dict) -> None:
    from src.assert_common import AssertCommon

    app = step.app or context.get("app", "")
    expected = step.expected or 1
    AssertCommon.assert_window_amount(app, int(expected))


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
}
