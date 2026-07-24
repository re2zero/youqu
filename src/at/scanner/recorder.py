# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only

"""Event-driven AT-SPI recording engine.

Replaces the old snapshot-mode recorder with a real-time event bus
that captures AT-SPI focus/window/children-changed events and input
events (mouse/keyboard) via X11 XRecord or Wayland evdev.

Events are organized into segments (automatic via window:activate,
or manual via CLI ``s``+Enter).  Structural changes trigger on-demand
subtree dumps to ``states/*.yaml``.  Output: ``record_session.yaml``.

Design reference: .trellis/tasks/07-22-at-dump-record-redesign/design.md R2.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

import pyatspi
import yaml

from src.at.scanner.atspi_dumper import (
    _MAX_NAME_LENGTH,
    _SKIP_ROLES,
    _STATE_MAP,
    _extract_node,
    _get_node_attrs,
)
from src.at.scanner.event_listener import (
    create_input_listener,
    is_modifier,
    is_printable_char,
    keysym_to_name,
)
from src.at.scanner.hit_test import ExtentsCache, _state_names, hit_test
from src.at.scanner.merger import write_runtime_dump

logger = logging.getLogger(__name__)

_DESKTOP_COORDS = 0  # pyatspi.DESKTOP_COORDS


# ---------------------------------------------------------------------------
# Segment dataclass
# ---------------------------------------------------------------------------


@dataclass
class Segment:
    """A logical grouping of events (e.g. main window, right-click menu)."""

    label: str
    trigger: Optional[dict[str, Any]] = None
    events: list[dict[str, Any]] = field(default_factory=list)
    states: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Event element extraction
# ---------------------------------------------------------------------------


def _extract_element(obj: Any) -> dict[str, Any]:
    """Extract a lightweight element dict from an AT-SPI accessible."""
    try:
        role_name = obj.get_role_name() or "unknown"
        name = obj.get_name() or ""
        object_name, accessible_id = _get_node_attrs(obj)
    except Exception:
        return {"role": "unknown", "name": "", "source": "runtime"}

    try:
        states = sorted(_state_names(obj))
    except Exception:
        states = []

    try:
        description = obj.description or ""
    except Exception:
        description = ""

    return {
        "role": role_name,
        "name": name[:_MAX_NAME_LENGTH],
        "object_name": object_name,
        "accessible_id": accessible_id,
        "description": description,
        "states": states,
        "source": "runtime",
    }


def _get_app_name(obj: Any) -> str:
    """Get the application name for an AT-SPI accessible."""
    try:
        return obj.get_application() and obj.get_application().get_name() or ""
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# RecordSession
# ---------------------------------------------------------------------------


class RecordSession:
    """Event-driven recording engine.

    Listens to AT-SPI events (focus, window, children-changed) and input
    events (mouse/keyboard via X11 XRecord or evdev), organizes them into
    segments, and outputs ``record_session.yaml`` + ``states/*.yaml``.

    In CLI mode, runs the AT-SPI main loop in the calling thread.
    In GUI mode, runs a Qt event loop with periodic AT-SPI event pumping.
    """

    _TYPE_TEXT_TIMEOUT = 0.8  # seconds of inactivity before flushing type_text

    def __init__(
        self,
        app_name: str,
        output_dir: str | Path,
        gui_mode: bool = False,
        launch_cmd: Optional[str] = None,
    ) -> None:
        self.app_name = app_name
        self.output_dir = Path(output_dir)
        self.states_dir = self.output_dir / "states"
        self.gui_mode = gui_mode
        self.launch_cmd = launch_cmd

        self.segments: list[Segment] = []
        self.current_segment: Optional[Segment] = None
        self.state_index = 0
        self.start_time = 0.0
        self._lock = threading.Lock()

        # Input listener
        self._input_listener: Any = None

        # Extents cache for hit-test optimization
        self._extents_cache = ExtentsCache()

        # type_text aggregation state
        self._type_text_buffer = ""
        self._type_text_element: Optional[dict] = None
        self._type_text_last_time = 0.0

        # Focus event deduplication state
        self._last_focus_key: str = ""
        self._last_focus_time: float = 0.0
        self._focus_dedup_window: float = 0.5  # seconds

        # Right-click context tracking for menu detection
        self._pending_right_click: bool = False
        self._right_click_time: float = 0.0

        # AT-SPI event registration state
        self._atspi_registered = False
        self._running = False
        self._stop_requested = False

        # Launched process
        self._launched_process: Optional[subprocess.Popen] = None

        # CLI input thread
        self._cli_thread: Optional[threading.Thread] = None

        # GUI state
        self._qt_app: Any = None
        self._gui_widget: Optional["EventRecorderWidget"] = None
        self._atspi_timer: Any = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start recording. Blocks until stop() or user quits."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.states_dir.mkdir(parents=True, exist_ok=True)
        self.start_time = time.monotonic()
        self._running = True

        # Launch app if specified
        if self.launch_cmd:
            self._launch_app()

        # Create initial segment
        initial_trigger = (
            {"type": "launch", "command": self.launch_cmd} if self.launch_cmd else None
        )
        self.current_segment = Segment(
            label=self.app_name,
            trigger=initial_trigger,
        )

        # Dump launch tree
        if self.launch_cmd or self.app_name:
            launch_tree = self._dump_app_tree()
            if launch_tree:
                state_path = self._write_state(launch_tree, f"{self.state_index:02d}_launch")
                if self.current_segment:
                    self.current_segment.states.append(state_path)
                launch_event = {
                    "type": "launch",
                    "command": self.launch_cmd or "",
                    "at_tree": state_path,
                }
                if self.current_segment:
                    self.current_segment.events.append(launch_event)
                self._print_event("LAUNCH", f"{self.app_name}")
                self.state_index += 1

        # Rebuild extents cache
        self._rebuild_extents_cache()

        # Register AT-SPI event listeners
        self._register_atspi_listeners()

        # Start input event listener
        self._input_listener = create_input_listener(
            on_mouse=self._on_mouse_press,
            on_key=self._on_key_press,
        )

        if self.gui_mode:
            self._run_gui()
        else:
            self._run_cli()

    def stop(self) -> None:
        """Stop recording and write output files."""
        if not self._running:
            return
        self._running = False

        # Flush pending type_text
        self._flush_type_text()

        # Close current segment
        with self._lock:
            if self.current_segment and self.current_segment.events:
                self.segments.append(self.current_segment)
            self.current_segment = None

        # Deregister AT-SPI listeners
        self._deregister_atspi_listeners()

        # Stop input listener
        if self._input_listener:
            self._input_listener.stop()

        # Terminate launched app
        if self._launched_process:
            try:
                self._launched_process.terminate()
            except Exception:
                pass

        # Stop AT-SPI main loop (if running)
        try:
            pyatspi.Registry.stop()
        except Exception:
            pass

        # Write record_session.yaml
        self._write_session()

    # ------------------------------------------------------------------
    # CLI mode
    # ------------------------------------------------------------------

    def _run_cli(self) -> None:
        """Run CLI mode: AT-SPI main loop + stdin for manual segmentation."""
        print(f"\n[RECORD] Recording started for '{self.app_name}'", file=sys.stderr)
        print(
            "[RECORD] Press 's' + Enter to create a new segment, 'q' + Enter or Ctrl+C to finish\n",
            file=sys.stderr,
        )

        # CLI input thread
        self._cli_thread = threading.Thread(target=self._cli_input_loop, daemon=True)
        self._cli_thread.start()

        # Allow Ctrl+C to stop
        def _sigint_handler(sig, frame):
            self._stop_requested = True
            try:
                pyatspi.Registry.stop()
            except Exception:
                pass

        signal.signal(signal.SIGINT, _sigint_handler)

        # Run AT-SPI main loop (blocking)
        try:
            pyatspi.Registry.start()
        except Exception as e:
            logger.error("AT-SPI main loop error: %s", e)

        self.stop()

    def _cli_input_loop(self) -> None:
        """Read stdin for manual segment commands."""
        while self._running:
            try:
                cmd = input().strip().lower()
            except (EOFError, KeyboardInterrupt):
                self._stop_requested = True
                try:
                    pyatspi.Registry.stop()
                except Exception:
                    pass
                break

            if cmd == "s":
                try:
                    name = input("  Segment name: ").strip()
                except (EOFError, KeyboardInterrupt):
                    name = ""
                self._new_segment(
                    name or f"segment_{len(self.segments)}",
                    {"type": "manual"},
                )
            elif cmd in ("q", "quit", "exit", "done"):
                self._stop_requested = True
                try:
                    pyatspi.Registry.stop()
                except Exception:
                    pass
                break

    # ------------------------------------------------------------------
    # GUI mode
    # ------------------------------------------------------------------

    def _run_gui(self) -> None:
        """Run GUI mode: Qt event loop with periodic AT-SPI event pumping."""
        try:
            from PyQt6.QtCore import Qt, QTimer, pyqtSignal  # type: ignore[import-untyped]
            from PyQt6.QtWidgets import (  # type: ignore[import-untyped]
                QApplication,
                QLabel,
                QPushButton,
                QTextEdit,
                QVBoxLayout,
                QWidget,
            )
        except ImportError:
            logger.warning("PyQt6 not installed — falling back to CLI mode")
            self.gui_mode = False
            self._run_cli()
            return

        app = QApplication.instance()
        if app is None:
            app = QApplication([])

        self._qt_app = app

        def _sigint_handler(sig, frame):
            self.stop()

        signal.signal(signal.SIGINT, _sigint_handler)

        self._gui_widget = EventRecorderWidget()
        self._gui_widget.stop_requested.connect(self.stop)
        self._gui_widget.show()
        self._gui_widget.raise_()
        self._gui_widget.activateWindow()

        # Pump AT-SPI events periodically
        self._atspi_timer = QTimer()
        self._atspi_timer.timeout.connect(self._pump_atspi_events)
        self._atspi_timer.start(50)  # 50ms interval

        app.exec()
        self.stop()

    def _pump_atspi_events(self) -> None:
        """Pump queued AT-SPI events without blocking."""
        try:
            pyatspi.Registry.pumpQueuedEvents()
        except Exception:
            pass

    def _gui_print(self, text: str) -> None:
        """Append text to the GUI event log."""
        if self._gui_widget:
            self._gui_widget.append_event(text)

    # ------------------------------------------------------------------
    # AT-SPI event registration
    # ------------------------------------------------------------------

    def _register_atspi_listeners(self) -> None:
        """Register AT-SPI event listeners."""
        pyatspi.Registry.registerEventListener(self._on_focus_event, "focus:")
        pyatspi.Registry.registerEventListener(self._on_window_event, "window:")
        pyatspi.Registry.registerEventListener(self._on_children_changed, "object:children-changed")
        self._atspi_registered = True
        logger.info("AT-SPI event listeners registered")

    def _deregister_atspi_listeners(self) -> None:
        """Deregister AT-SPI event listeners."""
        if not self._atspi_registered:
            return
        try:
            pyatspi.Registry.deregisterEventListener(self._on_focus_event, "focus:")
            pyatspi.Registry.deregisterEventListener(self._on_window_event, "window:")
            pyatspi.Registry.deregisterEventListener(
                self._on_children_changed, "object:children-changed"
            )
        except Exception as e:
            logger.debug("Deregister error: %s", e)
        self._atspi_registered = False

    # ------------------------------------------------------------------
    # AT-SPI event handlers (called from AT-SPI main loop thread)
    # ------------------------------------------------------------------

    def _on_focus_event(self, event: Any) -> None:
        """Handle AT-SPI focus events."""
        try:
            element = _extract_element(event.source)
            app_name = _get_app_name(event.source)
            is_main_app = app_name == self.app_name
        except Exception:
            return

        # Deduplicate: skip if same element focused within dedup window
        focus_key = (
            f"{element.get('role', '')}|{element.get('name', '')}|{element.get('object_name', '')}"
        )
        now = time.monotonic()
        if (
            focus_key == self._last_focus_key
            and (now - self._last_focus_time) < self._focus_dedup_window
        ):
            return
        self._last_focus_key = focus_key
        self._last_focus_time = now

        evt = {
            "type": "focus",
            "element": element,
            "app": app_name,
            "is_main_app": is_main_app,
        }

        with self._lock:
            if self.current_segment:
                self.current_segment.events.append(evt)
        self._print_event(
            "FOCUS",
            f"{'[主]' if is_main_app else '[子]'} {element.get('role', '?')} "
            f'"{element.get("name", "")}"',
        )

    def _on_window_event(self, event: Any) -> None:
        """Handle window:activate/create/close events."""
        event_type = str(event.type) if hasattr(event, "type") else ""
        try:
            element = _extract_element(event.source)
            app_name = _get_app_name(event.source)
        except Exception:
            element = {}
            app_name = ""

        is_main_app = app_name == self.app_name

        if "activate" in event_type:
            # window:activate → new segment only if genuinely different context
            label = element.get("name", "") or app_name or "unnamed"

            should_new_segment = False
            if self.current_segment is None:
                should_new_segment = True
            elif is_main_app:
                # Same main app re-activating (e.g. after menu close, titlebar
                # focus shift) — never split into a new segment.
                should_new_segment = False
            elif not is_main_app and self.current_segment.trigger:
                prev_app = self.current_segment.trigger.get("app", "")
                if prev_app != app_name:
                    should_new_segment = True

            if should_new_segment:
                trigger = {
                    "type": "window_activate",
                    "app": app_name,
                    "is_main_app": is_main_app,
                    "element": element,
                }
                self._new_segment(label, trigger)

            evt = {
                "type": "window_activate",
                "element": element,
                "app": app_name,
                "is_main_app": is_main_app,
            }
            with self._lock:
                if self.current_segment:
                    self.current_segment.events.append(evt)
            self._print_event(
                "WIN_ACTIVATE",
                f"{'[主]' if is_main_app else '[子]'} {app_name} "
                f'{element.get("role", "?")} "{element.get("name", "")}"',
            )

        elif "create" in event_type:
            # window:create → dump subtree
            state_path = self._dump_accessible_subtree(
                event.source, f"{self.state_index:02d}_window"
            )
            if state_path:
                self.state_index += 1
                with self._lock:
                    if self.current_segment:
                        self.current_segment.states.append(state_path)
            evt = {
                "type": "window_create",
                "element": element,
                "app": app_name,
                "is_main_app": is_main_app,
                "at_tree": state_path,
            }
            with self._lock:
                if self.current_segment:
                    self.current_segment.events.append(evt)
            self._print_event(
                "WIN_CREATE",
                f'app={app_name} {element.get("role", "?")} "{element.get("name", "")}"',
            )

        elif "close" in event_type or "destroy" in event_type:
            evt = {
                "type": "window_close",
                "element": element,
                "app": app_name,
                "is_main_app": is_main_app,
            }
            with self._lock:
                if self.current_segment:
                    self.current_segment.events.append(evt)
            self._print_event(
                "WIN_CLOSE",
                f'app={app_name} "{element.get("name", "")}"',
            )

    def _on_children_changed(self, event: Any) -> None:
        """Handle object:children-changed:add/remove events."""
        event_type = str(event.type) if hasattr(event, "type") else ""
        is_add = "add" in event_type
        is_remove = "remove" in event_type
        if not is_add and not is_remove:
            return

        try:
            parent_element = _extract_element(event.source)
            parent_role = parent_element.get("role", "")
        except Exception:
            parent_role = ""
            parent_element = {}

        # Detect menu open/close — check parent role AND child roles
        # Parent roles seen in practice: "static", "section", "frame", etc.
        # So we also check if children are "menu item" elements
        is_menu = False
        is_context_menu = False

        # Check parent role for menu-like containers
        menu_roles = {"menu", "popup menu", "menu bar", "list", "tree"}
        if parent_role in menu_roles or "menu" in parent_role or "popup" in parent_role:
            is_menu = True

        # Also check children for menu items (handles non-standard parent roles)
        if not is_menu and is_add:
            try:
                child_count = event.source.get_child_count()
                if child_count > 0:
                    for i in range(min(child_count, 5)):
                        child = event.source.get_child_at_index(i)
                        if child is None:
                            continue
                        child_role = child.get_role_name() or ""
                        if child_role == "menu item" or "menu" in child_role:
                            is_menu = True
                            break
            except Exception:
                pass

        # Check if this menu appeared after a right-click
        if is_menu and self._pending_right_click:
            now = time.monotonic()
            if (now - self._right_click_time) < 2.0:  # within 2 seconds
                is_context_menu = True
            self._pending_right_click = False

        if is_menu:
            if is_add:
                # Menu open — dump subtree
                state_name = (
                    f"{self.state_index:02d}_context_menu"
                    if is_context_menu
                    else f"{self.state_index:02d}_menu_open"
                )
                state_path = self._dump_accessible_subtree(event.source, state_name)
                if state_path:
                    self.state_index += 1
                    with self._lock:
                        if self.current_segment:
                            self.current_segment.states.append(state_path)

                # Extract menu items
                menu_items = self._extract_menu_items(event.source)
                evt = {
                    "type": "context_menu_open" if is_context_menu else "menu_open",
                    "at_tree": state_path,
                    "menu_items": menu_items,
                    "is_context_menu": is_context_menu,
                }
                with self._lock:
                    if self.current_segment:
                        self.current_segment.events.append(evt)
                item_names = [m.get("name", "") for m in menu_items[:5]]
                suffix = "..." if len(menu_items) > 5 else ""
                tag = "CTX_MENU" if is_context_menu else "MENU_OPEN"
                self._print_event(
                    tag,
                    f"{len(menu_items)} items: [{', '.join(item_names)}{suffix}]",
                )
            elif is_remove:
                evt = {"type": "menu_close"}
                with self._lock:
                    if self.current_segment:
                        self.current_segment.events.append(evt)
                self._print_event("MENU_CLOSE", "")

        elif is_add:
            # Generic children-changed:add — dump subtree (on-demand)
            state_path = self._dump_accessible_subtree(
                event.source, f"{self.state_index:02d}_children_changed"
            )
            if state_path:
                self.state_index += 1
                with self._lock:
                    if self.current_segment:
                        self.current_segment.states.append(state_path)
            evt = {
                "type": "children_changed",
                "detail": "add",
                "element": parent_element,
                "at_tree": state_path,
            }
            with self._lock:
                if self.current_segment:
                    self.current_segment.events.append(evt)

        # Rebuild extents cache after structural change
        if is_add:
            self._rebuild_extents_cache()

    # ------------------------------------------------------------------
    # Input event handlers (called from input listener thread)
    # ------------------------------------------------------------------

    def _on_mouse_press(self, x: int, y: int, button: int) -> None:
        """Handle mouse button press via hit-test."""
        element = None
        try:
            element = self._extents_cache.lookup(x, y)
            if element is None:
                app_root = self._find_app_root()
                if app_root is not None:
                    element = hit_test(x, y, app_root)
        except Exception as e:
            logger.debug("hit_test error: %s", e)

        button_name = {1: "left", 2: "middle", 3: "right"}.get(button, f"btn{button}")

        # Track right-click for context menu detection
        if button == 3:
            self._pending_right_click = True
            self._right_click_time = time.monotonic()

        # Skip scroll wheel events (buttons 4/5)
        if button in (4, 5):
            return

        # Determine event type
        if button == 3:
            evt_type = "right_click"
        elif button == 2:
            evt_type = "middle_click"
        else:
            evt_type = "click"

        evt = {
            "type": evt_type,
            "element": element or {},
            "coords": [x, y],
            "button": button_name,
        }

        with self._lock:
            if self.current_segment:
                self.current_segment.events.append(evt)

        label = ""
        if element:
            label = f'{element.get("role", "?")} "{element.get("name", "")}"'
        tag = {
            "click": "CLICK",
            "right_click": "RIGHT",
            "middle_click": "MIDDLE",
        }.get(evt_type, "CLICK")
        self._print_event(tag, f"{label} @ ({x},{y})")

    def _on_key_press(self, keysym: int, key_name: str, mod: bool, printable: bool) -> None:
        """Handle keyboard key press."""
        # Flush type_text if timeout passed
        now = time.monotonic()
        if self._type_text_buffer and (now - self._type_text_last_time) > self._TYPE_TEXT_TIMEOUT:
            self._flush_type_text()

        if printable and not mod:
            # Aggregate into type_text buffer
            self._type_text_buffer += key_name
            self._type_text_last_time = now
            # Update element from current focus
            if self._type_text_element is None:
                self._type_text_element = self._get_current_focus_element()
            return

        # Non-printable key — flush any pending type_text first
        if self._type_text_buffer:
            self._flush_type_text()

        # Check for CLI 's' + Enter manual segmentation
        # (only in CLI mode, not when key_name comes from actual input listener)
        # Note: In CLI mode, the 's' command is handled by stdin, not here.
        # This handler is for actual keyboard events captured by XRecord/evdev.

        evt = {
            "type": "key_press",
            "key": key_name,
            "keysym": keysym,
            "is_modifier": mod,
        }

        # Try to get current focus element
        focus_el = self._get_current_focus_element()
        if focus_el:
            evt["element"] = focus_el

        with self._lock:
            if self.current_segment:
                self.current_segment.events.append(evt)

        self._print_event("KEY", key_name)

    # ------------------------------------------------------------------
    # type_text aggregation
    # ------------------------------------------------------------------

    def _flush_type_text(self) -> None:
        """Flush accumulated printable characters as a type_text event."""
        if not self._type_text_buffer:
            return

        evt = {
            "type": "type_text",
            "text": self._type_text_buffer,
            "element": self._type_text_element or {},
        }

        with self._lock:
            if self.current_segment:
                self.current_segment.events.append(evt)

        self._print_event("TYPE", f'"{self._type_text_buffer}"')

        self._type_text_buffer = ""
        self._type_text_element = None

    def _get_current_focus_element(self) -> Optional[dict]:
        """Get the currently focused AT-SPI element (best-effort).

        Finds the active application, then drills down to the deepest
        focused descendant rather than returning the app-level element.
        """
        try:
            desktop = pyatspi.Registry.getDesktop(0)
            for i in range(desktop.get_child_count()):
                app = desktop.get_child_at_index(i)
                if app is None:
                    continue
                states = _state_names(app)
                if "active" in states or "focused" in states:
                    focused = self._find_focused_descendant(app)
                    if focused is not None:
                        return _extract_element(focused)
                    return _extract_element(app)
        except Exception:
            pass
        return None

    def _find_focused_descendant(self, obj: Any, max_depth: int = 10) -> Any:
        """Find the deepest focused descendant within max_depth levels."""
        if max_depth <= 0:
            return None
        try:
            child_count = obj.get_child_count()
            for i in range(child_count):
                child = obj.get_child_at_index(i)
                if child is None:
                    continue
                child_states = _state_names(child)
                if "focused" in child_states:
                    deeper = self._find_focused_descendant(child, max_depth - 1)
                    return deeper if deeper is not None else child
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    # Segment management
    # ------------------------------------------------------------------

    def _new_segment(self, label: str, trigger: dict) -> None:
        """Close current segment and start a new one."""
        # Flush pending type_text before segment boundary
        self._flush_type_text()

        with self._lock:
            if self.current_segment and self.current_segment.events:
                self.segments.append(self.current_segment)
            self.current_segment = Segment(label=label, trigger=trigger)

        self._print_event("SEGMENT", f'"{label}"')

    # ------------------------------------------------------------------
    # Subtree dump
    # ------------------------------------------------------------------

    def _dump_app_tree(self) -> list[dict]:
        """Dump the full AT-SPI tree for the main app."""
        from src.at.scanner.atspi_dumper import dump_at_spi_tree

        return dump_at_spi_tree(self.app_name)

    def _dump_accessible_subtree(self, accessible: Any, name_prefix: str) -> Optional[str]:
        """Dump an AT-SPI accessible's subtree to states/*.yaml."""
        if accessible is None:
            return None
        stats: dict[str, int] = {"total": 0, "skipped": 0, "errors": 0}
        try:
            tree = [_extract_node(accessible, depth=0, stats=stats)]
        except Exception as e:
            logger.debug("subtree dump error: %s", e)
            return None

        if not tree:
            return None

        safe_name = "".join(c if c.isalnum() or c in "_-" else "_" for c in name_prefix)
        state_path = self.states_dir / f"{safe_name}.yaml"
        rel_path = str(state_path.relative_to(self.output_dir))

        write_runtime_dump(
            tree,
            str(state_path),
            app_name=self.app_name,
            state_label=name_prefix,
        )
        return rel_path

    def _extract_menu_items(self, menu_accessible: Any) -> list[dict]:
        """Extract menu item names from a menu accessible."""
        items = []
        try:
            count = menu_accessible.get_child_count()
            for i in range(min(count, 50)):
                child = menu_accessible.get_child_at_index(i)
                if child is None:
                    continue
                items.append(_extract_element(child))
        except Exception:
            pass
        return items

    def _write_state(self, tree: list[dict], name_prefix: str) -> str:
        """Write a state snapshot and return its relative path."""
        safe_name = "".join(c if c.isalnum() or c in "_-" else "_" for c in name_prefix)
        state_path = self.states_dir / f"{safe_name}.yaml"
        rel_path = str(state_path.relative_to(self.output_dir))

        write_runtime_dump(
            tree,
            str(state_path),
            app_name=self.app_name,
            state_label=name_prefix,
        )
        return rel_path

    # ------------------------------------------------------------------
    # Extents cache
    # ------------------------------------------------------------------

    def _find_app_root(self) -> Any:
        """Find the AT-SPI application object for the recorded app."""
        try:
            desktop = pyatspi.Registry.getDesktop(0)
            for i in range(desktop.get_child_count()):
                app = desktop.get_child_at_index(i)
                if app and app.get_name() == self.app_name:
                    return app
        except Exception as e:
            logger.debug("find_app_root error: %s", e)
        return None

    def _rebuild_extents_cache(self) -> None:
        """Rebuild the extents cache from the target app's subtree only."""
        try:
            app_root = self._find_app_root()
            if app_root is not None:
                self._extents_cache.build(app_root)
                logger.debug(
                    "Extents cache rebuilt: %d entries (app=%s)",
                    len(self._extents_cache),
                    self.app_name,
                )
            else:
                logger.debug("App root not found for extents cache")
        except Exception as e:
            logger.debug("Extents cache rebuild error: %s", e)

    # ------------------------------------------------------------------
    # App launch
    # ------------------------------------------------------------------

    def _launch_app(self) -> None:
        """Launch the application specified by launch_cmd."""
        if not self.launch_cmd:
            return

        print(f"[RECORD] Launching: {self.launch_cmd}", file=sys.stderr)
        env = os.environ.copy()
        env["QT_LINUX_ACCESSIBILITY_ALWAYS_ON"] = "1"
        try:
            self._launched_process = subprocess.Popen(
                self.launch_cmd.split(),
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            logger.error("Failed to launch app: %s", e)
            self._launched_process = None
            return

        # Wait for app to appear in AT-SPI tree
        for _ in range(50):  # up to 5 seconds
            if not self._running:
                break
            time.sleep(0.1)
            try:
                desktop = pyatspi.Registry.getDesktop(0)
                for i in range(desktop.get_child_count()):
                    app = desktop.get_child_at_index(i)
                    if app and app.get_name() == self.app_name:
                        return
            except Exception:
                continue

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------

    def _write_session(self) -> None:
        """Write record_session.yaml."""
        data = {
            "version": "2.0",
            "app": self.app_name,
            "created_at": datetime.now().isoformat(),
            "segments": [
                {
                    "label": s.label,
                    "trigger": s.trigger,
                    "events": s.events,
                    "states": s.states,
                }
                for s in self.segments
                if s.events
            ],
        }

        session_path = self.output_dir / "record_session.yaml"
        with open(session_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        print(
            f"\n[RECORD] Session saved: {session_path} "
            f"({len(data['segments'])} segments, "
            f"{sum(len(s['events']) for s in data['segments'])} events)",
            file=sys.stderr,
        )

    # ------------------------------------------------------------------
    # Event printing
    # ------------------------------------------------------------------

    def _print_event(self, tag: str, description: str) -> None:
        """Print an event line to CLI and/or GUI."""
        elapsed = time.monotonic() - self.start_time
        mins, secs = divmod(int(elapsed), 60)
        line = f"[{mins:02d}:{secs:02d}] {tag:<12} {description}"

        if self.gui_mode and self._gui_widget:
            self._gui_print(line)
        else:
            print(line, file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# GUI Widget (PyQt6)
# ---------------------------------------------------------------------------

# Lazy Qt imports — everything stays None when PyQt6 is absent
try:
    from PyQt6.QtCore import Qt, pyqtSignal  # type: ignore[import-untyped]
    from PyQt6.QtGui import QMouseEvent  # type: ignore[import-untyped]
    from PyQt6.QtWidgets import (  # type: ignore[import-untyped]
        QApplication,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )
except ImportError:
    Qt = None  # type: ignore[assignment]
    QApplication = None  # type: ignore[assignment]
    QWidget = None  # type: ignore[assignment]
    pyqtSignal = None  # type: ignore[assignment]
    QVBoxLayout = None  # type: ignore[assignment]
    QHBoxLayout = None  # type: ignore[assignment]
    QLabel = None  # type: ignore[assignment]
    QPushButton = None  # type: ignore[assignment]
    QTextEdit = None  # type: ignore[assignment]
    QMouseEvent = None  # type: ignore[assignment]


def qt_available() -> bool:
    return QApplication is not None


class EventRecorderWidget(QWidget):  # type: ignore[misc]
    """Floating widget for GUI recording mode.

    Shows a scrollable event log and Start/Stop/New Segment buttons.
    """

    stop_requested = pyqtSignal()

    _WFLAGS = (
        Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
    )
    _WFLAGS_WAYLAND = Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._drag_pos = None
        self._setup_window()
        self._build_ui()

    def _setup_window(self) -> None:
        self.setWindowTitle("AT Recorder")
        self.setFixedSize(360, 280)
        if os.environ.get("XDG_SESSION_TYPE") == "wayland":
            self.setWindowFlags(self._WFLAGS_WAYLAND)
        else:
            self.setWindowFlags(self._WFLAGS)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setStyleSheet("QWidget { background:#2b2b2b; border-radius:8px; }")

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 6, 10, 10)
        root.setSpacing(6)

        title = QLabel(" AT Recorder")
        title.setStyleSheet(
            "background:#2b2b2b; color:#fff; border-radius:6px; padding:4px 8px; font-weight:bold;"
        )
        root.addWidget(title)

        self.event_log = QTextEdit()
        self.event_log.setReadOnly(True)
        self.event_log.setStyleSheet(
            "background:#1a1a1a; color:#4CAF50; font-family:monospace; "
            "font-size:11px; border:1px solid #444; border-radius:4px;"
        )
        root.addWidget(self.event_log)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setStyleSheet(
            "padding:6px 14px; background:#f44336; color:#fff; border-radius:4px;"
        )
        self.stop_btn.clicked.connect(self.stop_requested.emit)
        btn_row.addWidget(self.stop_btn)

        root.addLayout(btn_row)

    def append_event(self, text: str) -> None:
        """Append a line to the event log."""
        self.event_log.append(text)
        sb = self.event_log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def mousePressEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if (event.buttons() & Qt.MouseButton.LeftButton) and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        self._drag_pos = None
        event.accept()

    def closeEvent(self, event: Any) -> None:  # type: ignore[override]
        event.accept()
        self.stop_requested.emit()
