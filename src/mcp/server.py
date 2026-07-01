#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
# SPDX-FileCopyrightText: 2023 UnionTech Software Technology Co., Ltd.
# SPDX-License-Identifier: GPL-2.0-only

"""YouQu MCP Server - expose desktop automation tools via MCP protocol."""

import os
import re
import sys
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from typing import Any, cast

os.environ.setdefault("DISPLAY", ":0")
logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
logging.root.setLevel(logging.WARNING)

_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# Prevent src/mcp/ from shadowing the real `mcp` package.
# When youqu injects src/ into sys.path, `import mcp` resolves to
# src/mcp/ instead of the MCP SDK, breaking fastmcp's `import mcp.types`.
_src_path = str(Path(__file__).resolve().parent.parent)  # src/
_original_syspath = sys.path.copy()
try:
    sys.path[:] = [p for p in sys.path if p != _src_path]
    from fastmcp import FastMCP
except ImportError as exc:
    sys.path[:] = _original_syspath
    print(f"Error: fastmcp is required for MCP server mode: {exc}")
    print("Install it with: pip install youqu-ai")
    sys.exit(1)
finally:
    sys.path[:] = _original_syspath

# YouQu framework exceptions inherit BaseException, not Exception.
# Bare "except Exception" cannot catch them — must use a combined tuple.
_TOOL_ERRORS = (Exception,)
try:
    from src.custom_exception import (
        ApplicationError,
        ApplicationStartError,
        ElementExpressionError,
        ElementNotFound,
        GetWindowInformation,
        NoIconOfThisSize,
        NoSetReferencePoint,
        NoSuchSkipMethodFound,
        NoSuchWindowPositionParameter,
        OcrTextRecognitionError,
        ParamError,
        ShellExecutionFailed,
        TemplateElementFound,
    )
    _TOOL_ERRORS = (Exception, ApplicationError, ApplicationStartError,
                    ElementExpressionError, ElementNotFound,
                    GetWindowInformation, NoIconOfThisSize,
                    NoSetReferencePoint, NoSuchSkipMethodFound,
                    NoSuchWindowPositionParameter, OcrTextRecognitionError,
                    ParamError, ShellExecutionFailed, TemplateElementFound)
except ImportError:
    pass


# ============================================================
# Job Manager Singleton
# ============================================================

_JOB_MANAGER = None


def _get_job_manager():
    """Get or create the global JobManager singleton."""
    global _JOB_MANAGER
    if _JOB_MANAGER is None:
        from src.mcp.jobs import JobManager
        _JOB_MANAGER = JobManager()
    return _JOB_MANAGER


@asynccontextmanager
async def youqu_lifespan(server: FastMCP) -> AsyncIterator[dict]:
    state = {}  # type: dict
    try:
        from src.mouse_key import MouseKey
        state["screen_size"] = MouseKey.screen_size()
    except Exception:
        pass
    yield state


mcp = FastMCP(
    name="YouQu Desktop Automation",
    instructions=(
        "YouQu Linux desktop automation tools. "
        "Use these tools to control desktop applications via AT-SPI, mouse/keyboard, "
        "image recognition, OCR, and VLM (Vision Language Model)."
    ),
    lifespan=youqu_lifespan,
)


# ============================================================
# AT-SPI Tools
# ============================================================

@mcp.tool
def atspi_find_element(app_name: str, expr: str, index: int = 0) -> dict:
    """Find UI element by AT-SPI path expression.

    Args:
        app_name: Application name (e.g. 'deepin-music')
        expr: Element path expression (e.g. '$//name/role')
        index: Element index when multiple matches found (default 0)
    """
    from src.dogtail_utils import DogtailUtils
    try:
        dog = DogtailUtils(name=app_name)
        element = dog.find_element_by_attr(expr, index)
        return {"success": True, "element": str(element)}
    except _TOOL_ERRORS as e:
        return {"success": False, "error": str(e)}


@mcp.tool
def atspi_find_and_click(app_name: str, expr: str, index: int = 0) -> dict:
    """Find and click a UI element by AT-SPI path expression.

    Args:
        app_name: Application name
        expr: Element path expression
        index: Element index (default 0)
    """
    from src.dogtail_utils import DogtailUtils
    try:
        dog = DogtailUtils(name=app_name)
        dog.find_element_by_attr_and_click(expr, index)
        return {"success": True}
    except _TOOL_ERRORS as e:
        return {"success": False, "error": str(e)}


@mcp.tool
def atspi_find_and_right_click(app_name: str, expr: str, index: int = 0) -> dict:
    """Find and right-click a UI element by AT-SPI path expression.

    Args:
        app_name: Application name
        expr: Element path expression
        index: Element index (default 0)
    """
    from src.dogtail_utils import DogtailUtils
    try:
        dog = DogtailUtils(name=app_name)
        dog.find_element_by_attr_and_right_click(expr, index)
        return {"success": True}
    except _TOOL_ERRORS as e:
        return {"success": False, "error": str(e)}


@mcp.tool
def atspi_get_children_text(app_name: str, element_expr: str) -> dict:
    """Get all children text of a UI element.

    Args:
        app_name: Application name
        element_expr: Element path to get children from
    """
    from src.dogtail_utils import DogtailUtils
    try:
        dog = DogtailUtils(name=app_name)
        text = dog.get_element_children_text(element_expr)
        return {"success": True, "text": text}
    except _TOOL_ERRORS as e:
        return {"success": False, "error": str(e)}


@mcp.tool
def atspi_dump_tree(app_name: str) -> dict:
    """Dump the full AT-SPI accessibility tree of an application.

    Args:
        app_name: Application name
    """
    from src.dogtail_utils import DogtailUtils
    try:
        dog = DogtailUtils(name=app_name)
        node = dog.app_element()
        tree_text = node.dump(type="plain")
        return {"success": True, "tree": tree_text}
    except _TOOL_ERRORS as e:
        return {"success": False, "error": str(e)}


# ============================================================
# Mouse/Keyboard Tools
# ============================================================

@mcp.tool
def mouse_click(x: int, y: int) -> dict:
    """Left click at screen coordinates (x, y).

    Args:
        x: X coordinate
        y: Y coordinate
    """
    from src.mouse_key import MouseKey
    try:
        MouseKey.click(_x=x, _y=y)
        return {"success": True}
    except _TOOL_ERRORS as e:
        return {"success": False, "error": str(e)}


@mcp.tool
def mouse_right_click(x: int, y: int) -> dict:
    """Right click at screen coordinates (x, y).

    Args:
        x: X coordinate
        y: Y coordinate
    """
    from src.mouse_key import MouseKey
    try:
        MouseKey.right_click(_x=x, _y=y)
        return {"success": True}
    except _TOOL_ERRORS as e:
        return {"success": False, "error": str(e)}


@mcp.tool
def mouse_double_click(x: int, y: int) -> dict:
    """Double click at screen coordinates (x, y).

    Args:
        x: X coordinate
        y: Y coordinate
    """
    from src.mouse_key import MouseKey
    try:
        MouseKey.double_click(_x=x, _y=y)
        return {"success": True}
    except _TOOL_ERRORS as e:
        return {"success": False, "error": str(e)}


@mcp.tool
def mouse_move_to(x: int, y: int, duration: float = 0.4) -> dict:
    """Move mouse to coordinates (x, y) with optional duration.

    Args:
        x: X coordinate
        y: Y coordinate
        duration: Move duration in seconds (default 0.4)
    """
    from src.mouse_key import MouseKey
    try:
        MouseKey.move_to(_x=x, _y=y, duration=duration)
        return {"success": True}
    except _TOOL_ERRORS as e:
        return {"success": False, "error": str(e)}


@mcp.tool
def mouse_scroll(amount: int) -> dict:
    """Scroll mouse wheel. Positive = up, negative = down.

    Args:
        amount: Scroll amount (positive=up, negative=down)
    """
    from src.mouse_key import MouseKey
    try:
        MouseKey.mouse_scroll(amount_of_scroll=amount)
        return {"success": True}
    except _TOOL_ERRORS as e:
        return {"success": False, "error": str(e)}


@mcp.tool
def keyboard_type_text(text: str) -> dict:
    """Type text using keyboard input. Supports Chinese input.

    Args:
        text: Text to type
    """
    from src.mouse_key import MouseKey
    try:
        MouseKey.input_message(text)
        return {"success": True}
    except _TOOL_ERRORS as e:
        return {"success": False, "error": str(e)}


@mcp.tool
def keyboard_press_key(key: str) -> dict:
    """Press a keyboard key or key combination.
    Examples: 'Return', 'Escape', 'ctrl+a', 'alt+F4'.
    Dangerous key combos (alt+F4, ctrl+alt+del, etc.) are blocked.

    Args:
        key: Key name or combination
    """
    key_lower = key.lower().replace(" ", "")
    if key_lower in _DANGEROUS_KEY_COMBOS:
        return {"success": False, "error": "Dangerous key combo '{}' blocked".format(key)}
    from src.mouse_key import MouseKey
    try:
        MouseKey().press_key(key)
        return {"success": True}
    except _TOOL_ERRORS as e:
        return {"success": False, "error": str(e)}


@mcp.tool
def keyboard_hot_key(keys: str) -> dict:
    """Press a key combination. Examples: keys="ctrl,c" or keys="alt,Tab".
    Dangerous key combos (alt+F4, ctrl+alt+del, etc.) are blocked.

    Args:
        keys: Comma-separated key names, e.g. "ctrl,c" or "alt,Tab"
    """
    key_list = [k.strip() for k in keys.split(",") if k.strip()]
    if _check_dangerous_keys(key_list):
        return {"success": False, "error": "Dangerous key combo blocked"}
    from src.mouse_key import MouseKey
    try:
        MouseKey.hot_key(*key_list)
        return {"success": True}
    except _TOOL_ERRORS as e:
        return {"success": False, "error": str(e)}


@mcp.tool
def get_screen_size() -> dict:
    """Get current screen resolution. Returns {width, height}."""
    from src.mouse_key import MouseKey
    try:
        w, h = MouseKey.screen_size()
        return {"success": True, "width": w, "height": h}
    except _TOOL_ERRORS as e:
        return {"success": False, "error": str(e)}


# ============================================================
# Window Tools
# ============================================================

@mcp.tool
def window_get_info(app_name: str, config_path: str = "") -> dict:
    """Get window information for an application.

    Args:
        app_name: Application name to get window info for
        config_path: Path to the UI config file (ui.ini), must be within project dir
    """
    from src.button_center import ButtonCenter
    try:
        ui = ButtonCenter(app_name=app_name, config_path=_validate_config_path(config_path))
        info = ui.window_info()
        return {"success": True, "info": str(info)}
    except _TOOL_ERRORS as e:
        return {"success": False, "error": str(e)}


@mcp.tool
def window_focus(app_name: str, config_path: str = "") -> dict:
    """Focus (bring to front) an application window.

    Args:
        app_name: Application name to focus
        config_path: Path to the UI config file (ui.ini), must be within project dir
    """
    from src.button_center import ButtonCenter
    try:
        ui = ButtonCenter(app_name=app_name, config_path=_validate_config_path(config_path))
        ui.focus_windows(app_name)
        return {"success": True}
    except _TOOL_ERRORS as e:
        return {"success": False, "error": str(e)}


@mcp.tool
def window_get_center(app_name: str, config_path: str = "") -> dict:
    """Get the center coordinates of an application window.

    Args:
        app_name: Application name
        config_path: Path to the UI config file (ui.ini), must be within project dir
    """
    from src.button_center import ButtonCenter
    try:
        ui = ButtonCenter(app_name=app_name, config_path=_validate_config_path(config_path))
        cx, cy = ui.window_center()
        return {"success": True, "x": cx, "y": cy}
    except _TOOL_ERRORS as e:
        return {"success": False, "error": str(e)}


@mcp.tool
def window_get_count(app_name: str, config_path: str = "") -> dict:
    """Get the number of windows for an application.

    Args:
        app_name: Application name
        config_path: Path to the UI config file (ui.ini), must be within project dir
    """
    from src.button_center import ButtonCenter
    try:
        ui = ButtonCenter(app_name=app_name, config_path=_validate_config_path(config_path))
        count = ui.get_windows_number(app_name)
        return {"success": True, "count": count}
    except _TOOL_ERRORS as e:
        return {"success": False, "error": str(e)}


@mcp.tool
def window_close(app_name: str, config_path: str = "") -> dict:
    """Close an application window gracefully.

    Attempts to close via AT-SPI close action first (cross-protocol), then
    falls back to xdotool (X11 only).

    Args:
        app_name: Application name
        config_path: Path to the UI config file (ui.ini), must be within project dir
    """
    from src.dogtail_utils import DogtailUtils
    try:
        dog = DogtailUtils(name=app_name)
        node = dog.app_element()
        for action in node.actions:
            if action == "close":
                node.doActionNamed("close")
                return {"success": True, "method": "atspi_action"}
        from src.cmdctl import CmdCtl
        CmdCtl.run_cmd(f"xdotool search --name {app_name} windowclose")
        return {"success": True, "method": "xdotool"}
    except _TOOL_ERRORS as e:
        return {"success": False, "error": str(e)}


# ============================================================
# Assertion Tools
# ============================================================

@mcp.tool
def assert_element_exists(expr: str) -> dict:
    """Assert that a UI element exists via AT-SPI.

    Args:
        expr: Element path expression to check (e.g. '$/app-name//element')
    """
    from src.assert_common import AssertCommon
    try:
        AssertCommon.assert_element_exist(expr)
        return {"success": True, "assertion": "PASS"}
    except AssertionError as e:
        return {"success": True, "assertion": "FAIL", "reason": str(e)}
    except _TOOL_ERRORS as e:
        return {"success": False, "error": str(e)}


@mcp.tool
def assert_element_not_exists(expr: str) -> dict:
    """Assert that a UI element does NOT exist via AT-SPI.

    Args:
        expr: Element path expression to check
    """
    from src.assert_common import AssertCommon
    try:
        AssertCommon.assert_element_not_exist(expr)
        return {"success": True, "assertion": "PASS"}
    except AssertionError as e:
        return {"success": True, "assertion": "FAIL", "reason": str(e)}
    except _TOOL_ERRORS as e:
        return {"success": False, "error": str(e)}


@mcp.tool
def assert_process_running(app_name: str) -> dict:
    """Assert that an application process is running.

    Args:
        app_name: Process name to check
    """
    from src.assert_common import AssertCommon
    try:
        AssertCommon.assert_process_status(True, app_name)
        return {"success": True, "assertion": "PASS"}
    except AssertionError as e:
        return {"success": True, "assertion": "FAIL", "reason": str(e)}
    except _TOOL_ERRORS as e:
        return {"success": False, "error": str(e)}


@mcp.tool
def assert_window_count(app_name: str, expected: int) -> dict:
    """Assert the number of windows for an application.

    Args:
        app_name: Application name
        expected: Expected window count
    """
    from src.assert_common import AssertCommon
    try:
        AssertCommon.assert_window_amount(app_name, expected)
        return {"success": True, "assertion": "PASS"}
    except AssertionError as e:
        return {"success": True, "assertion": "FAIL", "reason": str(e)}
    except _TOOL_ERRORS as e:
        return {"success": False, "error": str(e)}


@mcp.tool
def assert_image_exists(image_path: str, rate: float = 0.8) -> dict:
    """Assert that an image exists on screen by template matching.

    Args:
        image_path: Path to template image file
        rate: Match confidence threshold (0.0-1.0, default 0.8)
    """
    from src.assert_common import AssertCommon
    try:
        AssertCommon.assert_image_exist(image_path, rate)
        return {"success": True, "assertion": "PASS"}
    except AssertionError as e:
        return {"success": True, "assertion": "FAIL", "reason": str(e)}
    except _TOOL_ERRORS as e:
        return {"success": False, "error": str(e)}


@mcp.tool
def assert_file_exists(file_path: str) -> dict:
    """Assert that a file exists on disk.

    Args:
        file_path: File path to check
    """
    from src.assert_common import AssertCommon
    try:
        AssertCommon.assert_file_exist(file_path)
        return {"success": True, "assertion": "PASS"}
    except AssertionError as e:
        return {"success": True, "assertion": "FAIL", "reason": str(e)}
    except _TOOL_ERRORS as e:
        return {"success": False, "error": str(e)}


_ALLOWED_QUERY_COMMANDS = frozenset([
    "dpkg-query", "ps", "pgrep", "which", "whereis",
    "gsettings", "dbus-send", "dconf", "lsusb", "lspci",
    "xrandr", "xdpyinfo", "fc-list", "locale", "ls", "cat", "find",
    "env", "echo", "ss",
])

_PROTECTED_PROCESSES = frozenset([
    "systemd", "init", "Xorg", "Xwayland", "Wayland", "sshd",
    "cron", "dbus-daemon", "lightdm", "dde-session", "startdde",
    "deepin-desktop", "pulseaudio", "pipewire", "kwin", "mutter",
    "gnome-shell", "deepin-wm", "networkd", "udevd",
])

_DANGEROUS_KEY_COMBOS = frozenset([
    "alt+f4", "ctrl+alt+del", "ctrl+alt+t", "ctrl+alt+backspace",
    "ctrl+alt+f1", "ctrl+alt+f2", "ctrl+alt+f3", "ctrl+alt+f4",
    "ctrl+alt+f5", "ctrl+alt+f6", "ctrl+alt+escape", "ctrl+shift+escape",
    "super+l", "super+d", "super+q", "ctrl+z",
])


def _check_dangerous_keys(keys) -> bool:
    combo = "+".join(str(k).lower().strip() for k in keys)
    return combo in _DANGEROUS_KEY_COMBOS


_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _validate_config_path(config_path: str) -> str:
    if not config_path:
        return config_path
    resolved = Path(config_path).resolve()
    try:
        resolved.relative_to(_PROJECT_ROOT)
    except ValueError:
        raise ValueError("config_path must be within project directory")
    return str(resolved)


# ============================================================
# System Tools
# ============================================================

@mcp.tool
def system_run_command(command: str) -> dict:
    """Execute a limited shell command and return output.
    Only read-only query commands are allowed (ps, dpkg-query, gsettings, etc.).

    Args:
        command: Shell command to execute (restricted to allowed commands)
    """
    parts = command.strip().split(maxsplit=1)
    if not parts:
        return {"success": False, "error": "Empty command"}
    base = os.path.basename(parts[0])
    if base not in _ALLOWED_QUERY_COMMANDS:
        return {"success": False, "error": "Command '{}' not in allowlist".format(base)}
    from src.cmdctl import CmdCtl
    try:
        output = CmdCtl.run_cmd(command)
        return {"success": True, "output": output}
    except _TOOL_ERRORS as e:
        return {"success": False, "error": str(e)}


@mcp.tool
def system_kill_process(process_name: str) -> dict:
    """Kill a running process by name.
    System-critical processes are protected and cannot be killed.

    Args:
        process_name: Process name to kill
    """
    base = os.path.basename(process_name).strip()
    if not re.match(r"^[\w\-.]+$", base):
        return {"success": False, "error": "Invalid process name"}
    if base in _PROTECTED_PROCESSES or any(base.startswith(p) for p in _PROTECTED_PROCESSES):
        return {"success": False, "error": "Protected process '{}' cannot be killed".format(base)}
    from src.cmdctl import CmdCtl
    try:
        CmdCtl.kill_process(process_name)
        return {"success": True}
    except _TOOL_ERRORS as e:
        return {"success": False, "error": str(e)}


@mcp.tool
def system_get_process_status(process_name: str) -> dict:
    """Check if a process is running.

    Args:
        process_name: Process name to check
    """
    from src.cmdctl import CmdCtl
    try:
        status = CmdCtl.get_process_status(process_name)
        return {"success": True, "running": status}
    except _TOOL_ERRORS as e:
        return {"success": False, "error": str(e)}


@mcp.tool
def app_launch(command: str, wait_seconds: int = 3) -> dict:
    """Launch a desktop application in background.

    Args:
        command: Full command with arguments (e.g. '/usr/bin/deepin-reader /path/to/doc.pdf')
        wait_seconds: Seconds to wait for the window to appear (default 3, max 30)
    """
    import shlex
    parts = shlex.split(command)
    base = os.path.basename(parts[0]).strip()
    if not re.match(r"^[\w\-.]+$", base):
        return {"success": False, "error": "Invalid command name"}
    if base in _PROTECTED_PROCESSES or any(base.startswith(p) for p in _PROTECTED_PROCESSES):
        return {"success": False, "error": "Protected process '{}' cannot be launched".format(base)}
    wait_seconds = min(max(wait_seconds, 0), 30)
    from src.cmdctl import CmdCtl
    try:
        CmdCtl.run_cmd(f"nohup {command} &>/dev/null &")
        if wait_seconds > 0:
            import time
            time.sleep(wait_seconds)
        return {"success": True}
    except _TOOL_ERRORS as e:
        return {"success": False, "error": str(e)}


# ============================================================
# DBus Tools
# ============================================================

@mcp.tool
def dbus_get_property(
    bus_type: str,
    service: str,
    path: str,
    interface_name: str,
    property_name: str,
) -> dict:
    """Get a D-Bus property value.

    Args:
        bus_type: Bus type, 'session' or 'system'
        service: D-Bus service name (e.g. 'com.deepin.daemon.Appearance')
        path: Object path (e.g. '/com/deepin/daemon/Appearance')
        interface_name: Interface name (e.g. 'com.deepin.daemon.Appearance')
        property_name: Property name to read
    """
    from src.dbus_utils import DbusUtils
    if bus_type not in ("session", "system"):
        return {"success": False, "error": "bus_type must be 'session' or 'system'"}
    try:
        dbus = DbusUtils(
            dbus_name=service,
            object_path=path,
            interface=interface_name,
        )
        if bus_type == "system":
            value = dbus.get_system_properties_value(property_name)
        else:
            value = dbus.get_session_properties_value(property_name)
        return {"success": True, "value": str(value)}
    except _TOOL_ERRORS as e:
        return {"success": False, "error": str(e)}


# ============================================================
# VLM Tools (optional, graceful degradation)
# ============================================================

@mcp.tool
def vlm_click(description: str) -> dict:
    """Locate and click a UI element using VLM (Vision Language Model).
    Falls back to error if VLM is not available.

    Args:
        description: Natural language description of the element to click,
                     e.g. "main menu button", "copy icon in toolbar"
    """
    try:
        from src.vlm.config import VLMConfig  # type: ignore[import-untyped]
    except ImportError:
        return {"success": False, "error": "VLM module not available."}
    config = VLMConfig()
    if not config.is_available():
        return {
            "success": False,
            "error": "VLM not available. Enable in globalconfig.ini [vlm] section.",
        }
    try:
        from src.vlm.vlm_locator import create_vlm_locator  # type: ignore[import-untyped]
        from src.vlm.vlm_executor import VLMExecutor  # type: ignore[import-untyped]
        locator = create_vlm_locator(config)
        executor = VLMExecutor(locator, config)
        result = executor.click_by_description(description)
        return {
            "success": result.success,
            "x": result.x,
            "y": result.y,
            "confidence": result.confidence,
            "message": result.message,
        }
    except _TOOL_ERRORS as e:
        return {"success": False, "error": str(e)}


@mcp.tool
def vlm_assert_visual(assertion: str, expected: str) -> dict:
    """Evaluate a visual assertion using VLM on the current screen.

    Args:
        assertion: What to assert, e.g. "dialog is visible"
        expected: Expected state, e.g. "dialog title shows 'Save'"
    """
    try:
        from src.vlm.config import VLMConfig  # type: ignore[import-untyped]
    except ImportError:
        return {"success": False, "error": "VLM module not available."}
    config = VLMConfig()
    if not config.is_available():
        return {
            "success": False,
            "error": "VLM not available. Enable in globalconfig.ini [vlm] section.",
        }
    try:
        from src.vlm.vlm_locator import create_vlm_locator  # type: ignore[import-untyped]
        from src.vlm.screenshot import capture_for_vlm  # type: ignore[import-untyped]
        locator = create_vlm_locator(config)
        img_path = str(config.evidence_dir / "vlm_assert.png")
        capture_for_vlm(output_path=img_path)
        result = locator.evaluate_assertion(img_path, assertion, expected)
        if result:
            return {
                "success": True,
                "verdict": result.verdict,
                "confidence": result.confidence,
                "reason": result.reason,
            }
        return {"success": False, "error": "VLM returned no result"}
    except _TOOL_ERRORS as e:
        return {"success": False, "error": str(e)}


@mcp.tool
def vlm_agent_run(instruction: str, max_iterations: int = 10) -> dict:
    """Run VLM Agent for autonomous test execution.
    The agent will observe the screen and autonomously perform actions
    to complete the given instruction.

    Args:
        instruction: Natural language test instruction,
                     e.g. "open file menu and click save"
        max_iterations: Maximum number of action iterations (clamped to 1-20)
    """
    max_iterations = min(max(max_iterations, 1), 20)
    try:
        from src.vlm.config import VLMConfig  # type: ignore[import-untyped]
    except ImportError:
        return {"success": False, "error": "VLM module not available."}
    config = VLMConfig()
    if not config.is_available():
        return {
            "success": False,
            "error": "VLM not available. Enable in globalconfig.ini [vlm] section.",
        }
    try:
        from src.vlm.vlm_locator import create_vlm_locator  # type: ignore[import-untyped]
        from src.vlm.vlm_agent import VLMAgent  # type: ignore[import-untyped]
        locator = create_vlm_locator(config)
        agent = VLMAgent(locator, config)
        result = agent.run(instruction, max_iterations=max_iterations)
        return result
    except _TOOL_ERRORS as e:
        return {"success": False, "error": str(e)}


# ============================================================
# Screenshot Tools
# ============================================================

@mcp.tool
def screenshot_save() -> dict:
    """Take a screenshot of the entire screen and save to evidence directory."""
    try:
        from src.vlm.screenshot import capture_for_vlm  # type: ignore[import-untyped]
    except ImportError:
        return {"success": False, "error": "screenshot module not available"}
    try:
        evidence_dir = _PROJECT_ROOT / "report" / "vlm_evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        path = str(evidence_dir / "screenshot.png")
        capture_for_vlm(output_path=path)
        return {"success": True, "path": path}
    except _TOOL_ERRORS as e:
        return {"success": False, "error": str(e)}


# ============================================================
# YAML Test Execution Tools (async batch)
# ============================================================

def _find_yaml_dir():
    """Find yaml directory from common locations.

    Priority: YOUQU_AUTOTEST_DIR env var > CWD/yaml + pytest.ini > CWD/autotest/yaml.
    """
    import os as _os

    env_dir = _os.environ.get("YOUQU_AUTOTEST_DIR", "")
    if env_dir:
        ep = Path(env_dir)
        if (ep / "yaml").is_dir():
            pytest_dir = ep if (ep / "pytest.ini").exists() else ep.parent if (ep.parent / "pytest.ini").exists() else ep
            return ep / "yaml", pytest_dir

    cwd = Path.cwd()
    if (cwd / "yaml").is_dir() and (cwd / "pytest.ini").exists():
        return cwd / "yaml", cwd
    if (cwd / "autotest" / "yaml").is_dir():
        atd = cwd / "autotest"
        return atd / "yaml", atd
    return None, None


@mcp.tool
def yaml_list_tests(
    app: str = "",
    module: str = "",
    feature: str = "",
    tags: str = "",
) -> dict:
    """List available YAML test cases with optional filtering.

    Args:
        app: Filter by app name (e.g. 'deepin-music')
        module: Filter by module (e.g. '播放')
        feature: Filter by feature (e.g. '本地文件')
        tags: Comma-separated tags (e.g. 'L1,smoke')
    """
    yaml_dir, _ = _find_yaml_dir()
    if not yaml_dir:
        return {"success": False, "error": "No YAML test directory found"}
    try:
        from src.yaml_test.index import YamlIndex
        idx = YamlIndex(yaml_dir)
        tags_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
        tests = idx.query(
            app=app or None,
            module=module or None,
            feature=feature or None,
            tags=tags_list,
        )
        stats = idx.get_stats()
        return {"success": True, "total": len(tests), "tests": tests, "stats": stats}
    except _TOOL_ERRORS as e:
        return {"success": False, "error": str(e)}


@mcp.tool
def yaml_run_batch(
    test_ids: str,
    batch_size: int = 5,
) -> dict:
    """Run YAML test cases asynchronously in batches.

    Returns a job_id immediately — use yaml_get_status(job_id) to poll.
    """
    yaml_dir, pytest_ini_dir = _find_yaml_dir()
    if not yaml_dir:
        return {"success": False, "error": "No YAML test directory found"}

    try:
        from src.yaml_test.index import YamlIndex
        idx = YamlIndex(yaml_dir)

        if test_ids.strip().upper() == "ALL":
            query_results = idx.query()
            ids = [t["id"] for t in query_results]
            file_map = {t["id"]: t["file"] for t in query_results}
        elif test_ids.startswith("module:"):
            query_results = idx.query(module=test_ids[len("module:"):].strip())
            ids = [t["id"] for t in query_results]
            file_map = {t["id"]: t["file"] for t in query_results}
        elif test_ids.startswith("tag:"):
            tag_list = [t.strip() for t in test_ids[len("tag:"):].strip().split(",") if t.strip()]
            query_results = idx.query(tags=tag_list)
            ids = [t["id"] for t in query_results]
            file_map = {t["id"]: t["file"] for t in query_results}
        else:
            ids = [tid.strip() for tid in test_ids.split(",") if tid.strip()]
            known = {t["id"]: t["file"] for t in idx.load()}
            file_map = {tid: known[tid] for tid in ids if tid in known} or None

        if not ids:
            return {"success": False, "error": "No test IDs resolved"}

        from src.mcp.jobs import execute_batches
        jm = _get_job_manager()
        total_batches = (len(ids) + batch_size - 1) // batch_size

        def _run():
            return execute_batches(
                test_ids=ids, yaml_dir=str(yaml_dir),
                pytest_ini_dir=str(pytest_ini_dir), batch_size=batch_size,
                progress_callback=None, cancel_event=None,
                file_map=file_map,
            )

        job = jm.submit(_run)
        if job.status == "rejected":
            return {"success": False, "error": job.error, "running_job_id": job.running_job_id}

        return {
            "success": True, "job_id": job.job_id, "status": job.status,
            "total_batches": total_batches, "total_cases": len(ids), "batch_size": batch_size,
        }
    except _TOOL_ERRORS as e:
        return {"success": False, "error": str(e)}


@mcp.tool
def yaml_get_status(job_id: str) -> dict:
    """Get status of a running or completed test job.

    Poll every 5 seconds until status is 'completed' or 'failed'.
    """
    import time
    jm = _get_job_manager()
    job = jm.get_status(job_id)
    if not job:
        return {"success": False, "error": f"Job '{job_id}' not found"}

    resp = {
        "job_id": job.job_id,
        "status": job.status,
        "progress": job.progress,
        "elapsed_ms": int((time.time() - job.created_at) * 1000),
    }
    if job.status in ("completed", "failed", "cancelled") and job.result:
        resp["result"] = job.result
    if job.error:
        resp["error"] = job.error
    return resp


@mcp.tool
def yaml_cancel(job_id: str) -> dict:
    """Cancel a running test job.

    Completes the current batch, then stops.
    """
    jm = _get_job_manager()
    ok = jm.cancel_job(job_id)
    return {"success": True, "job_id": job_id, "cancelled": ok}


# ============================================================
# Dev-mode Suite Tools
# ============================================================


def _find_dev_yaml_dir():
    from youqu.cli.dev import _find_dev_yaml_dir as _cli_find
    return _cli_find()


@mcp.tool
def dev_list_suites() -> dict:
    """List available dev-mode suites from dev-yaml/ directory."""
    _dev_dir = _find_dev_yaml_dir()
    if not _dev_dir:
        return {"success": False, "error": "No dev-yaml/ directory found"}
    try:
        suites = []
        for p in sorted(_dev_dir.rglob("*.suite.yaml")):
            from src.yaml_test.suite.parser import parse_suite
            try:
                suite = parse_suite(p)
                suites.append({
                    "name": p.stem,
                    "file": str(p),
                    "title": suite.name,
                    "app": suite.app,
                    "module": suite.module,
                    "tags": suite.tags,
                    "spec_count": len(suite.specs),
                    "specs": [
                        {"id": s.id, "name": s.name, "tags": s.tags,
                         "skip": s.skip, "timeout": s.timeout}
                        for s in suite.specs
                    ],
                })
            except Exception as exc:
                suites.append({
                    "name": p.stem, "file": str(p),
                    "error": str(exc),
                })
        return {"success": True, "dev_dir": str(_dev_dir), "suites": suites}
    except _TOOL_ERRORS as e:
        return {"success": False, "error": str(e)}


@mcp.tool
def dev_run_suite(
    name: str,
    spec_ids: str = "",
    tags: str = "",
    skip_env_check: bool = False,
) -> dict:
    """Execute a dev-mode suite synchronously.

    Runs the suite in-process.

    Args:
        name: Suite name (filename without .suite.yaml suffix)
        spec_ids: Comma-separated spec IDs to filter (optional)
        tags: Comma-separated tags to filter (optional)
        skip_env_check: Skip environment pre-checks
    """
    _dev_dir = _find_dev_yaml_dir()
    if not _dev_dir:
        return {"success": False, "error": "No dev-yaml/ directory found"}

    from youqu.cli.dev import _find_suite_path as _cli_find_suite

    target_file = _cli_find_suite(name)
    if target_file is None:
        _stems = [p.stem for p in _dev_dir.rglob("*.suite.yaml")]
        return {"success": False, "error": f"Suite '{name}' not found",
                "available": _stems}

    try:
        from src.yaml_test.suite.executor import SuiteExecutor
        from src.yaml_test.suite.parser import parse_suite
        suite = parse_suite(target_file)
        executor = SuiteExecutor(suite)
        result = executor.run(
            spec_ids=spec_ids or None,
            tags=tags or None,
            skip_env_check=skip_env_check,
        )
        return {
            "success": True,
            "data": result.model_dump(),
        }
    except _TOOL_ERRORS as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"suite execution failed: {e}"}


# ============================================================
# Entry Point
# ============================================================

def start(transport: str = "stdio", port: int = 8000, host: str = "127.0.0.1"):
    """Start the MCP server.

    Args:
        transport: 'stdio' for Claude Desktop, 'sse' for HTTP+SSE,
                   'http' for Streamable HTTP (recommended for remote).
        port: HTTP port (only used when transport='sse' or 'http').
        host: Bind address (only used when transport='sse' or 'http').
    """
    logging.getLogger("fastmcp").setLevel(logging.WARNING)
    logging.getLogger("mcp").setLevel(logging.WARNING)
    logging.root.setLevel(logging.WARNING)
    kwargs = {"transport": transport}
    if transport != "stdio":
        kwargs["port"] = port
        kwargs["host"] = host
    mcp.run(**kwargs)
