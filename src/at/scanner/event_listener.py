# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only

"""Passive input event listener for X11 (XRecord) and Wayland (evdev).

Monitors mouse button presses and keyboard key presses *without*
grabbing or consuming events.  In environments where neither XRecord
nor evdev is available, degrades to a no-op with a warning.

Design reference: .trellis/tasks/07-22-at-dump-record-redesign/design.md
"""

from __future__ import annotations

import logging
import os
import struct
import threading
from dataclasses import dataclass
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Key mapping: X11 keysym -> readable name
# ---------------------------------------------------------------------------

_KEYSYM_MAP: dict[int, str] = {
    0xFF0D: "Return",
    0xFF1B: "Escape",
    0xFF08: "BackSpace",
    0xFFFF: "Delete",
    0xFF50: "Home",
    0xFF57: "End",
    0xFF51: "Left",
    0xFF52: "Up",
    0xFF53: "Right",
    0xFF54: "Down",
    0xFF09: "Tab",
    0xFF0A: "Linefeed",
    0xFFB0: "KP_0",
    0xFFB1: "KP_1",
    0xFFB2: "KP_2",
    0xFFB3: "KP_3",
    0xFFB4: "KP_4",
    0xFFB5: "KP_5",
    0xFFB6: "KP_6",
    0xFFB7: "KP_7",
    0xFFB8: "KP_8",
    0xFFB9: "KP_9",
    0xFF8D: "KP_Enter",
    0xFF9E: "KP_Begin",
    0xFF60: "F1",
    0xFF61: "F2",
    0xFF62: "F3",
    0xFF63: "F4",
    0xFF64: "F5",
    0xFF65: "F6",
    0xFF66: "F7",
    0xFF67: "F8",
    0xFF68: "F9",
    0xFF69: "F10",
    0xFF6A: "F11",
    0xFF6B: "F12",
    0xFFE1: "Shift_L",
    0xFFE2: "Shift_R",
    0xFFE3: "Control_L",
    0xFFE4: "Control_R",
    0xFFE9: "Alt_L",
    0xFFEA: "Alt_R",
    0xFFE7: "Meta_L",
    0xFFE8: "Meta_R",
    0xFE03: "ISO_Level3_Shift",
    0xFF7E: "Caps_Lock",
    0xFF7F: "Num_Lock",
    0xFF20: "Multi_key",
    0xFF13: "Pause",
    0xFF14: "Scroll_Lock",
    0xFF15: "Sys_Req",
    0xFF55: "Prior",
    0xFF56: "Next",
    0xFF5A: "Insert",
}

_MODIFIER_KEYSYMS: frozenset[int] = frozenset(
    {
        0xFFE1,
        0xFFE2,  # Shift
        0xFFE3,
        0xFFE4,  # Control
        0xFFE9,
        0xFFEA,  # Alt
        0xFFE7,
        0xFFE8,  # Meta/Super
        0xFE03,  # AltGr
    }
)


def keysym_to_name(keysym: int) -> str:
    """Convert an X11 keysym to a human-readable name."""
    if keysym in _KEYSYM_MAP:
        return _KEYSYM_MAP[keysym]
    if 0x0020 <= keysym <= 0x007E:
        return chr(keysym)
    if 0x0100 <= keysym <= 0x017F:
        return chr(keysym)
    return f"keysym_0x{keysym:04X}"


def is_modifier(keysym: int) -> bool:
    """Return True if *keysym* is a modifier key."""
    return keysym in _MODIFIER_KEYSYMS


def is_printable_char(keysym: int) -> bool:
    """Return True if *keysym* is a printable character (for type_text aggregation)."""
    if is_modifier(keysym):
        return False
    return (0x0020 <= keysym <= 0x017F) and keysym not in _KEYSYM_MAP


# ---------------------------------------------------------------------------
# Event data structure
# ---------------------------------------------------------------------------


@dataclass
class InputEvent:
    """A single input event captured by the listener."""

    event_type: str  # "mouse_press" | "key_press"
    x: int = 0
    y: int = 0
    button: int = 0  # 1=left, 2=middle, 3=right
    keysym: int = 0
    key_name: str = ""
    is_modifier: bool = False
    is_printable: bool = False


# ---------------------------------------------------------------------------
# Listener interface
# ---------------------------------------------------------------------------

MouseCallback = Callable[[int, int, int], None]
KeyCallback = Callable[[int, str, bool, bool], None]


class InputEventListener:
    """Abstract input event listener."""

    def __init__(self, on_mouse: MouseCallback, on_key: KeyCallback) -> None:
        self.on_mouse = on_mouse
        self.on_key = on_key
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> bool:
        """Start listening in a background thread. Returns True if started."""
        raise NotImplementedError

    def stop(self) -> None:
        """Stop listening."""
        self._running = False

    def is_running(self) -> bool:
        return self._running


# ---------------------------------------------------------------------------
# X11 listener via XRecord (python-xlib)
# ---------------------------------------------------------------------------

# X event type constants (wire-level)
_X_KeyPress = 2
_X_KeyRelease = 3
_X_ButtonPress = 4
_X_ButtonRelease = 5


class X11RecordListener(InputEventListener):
    """X11 passive monitoring via XRecord extension.

    Uses a single X connection for both control and data.
    No grab is performed, so user input flows to focused windows normally.
    """

    def __init__(self, on_mouse: MouseCallback, on_key: KeyCallback) -> None:
        super().__init__(on_mouse, on_key)
        self._display: Any = None
        self._context: Any = None
        self._byte_order: str = "="  # will detect from display

    def start(self) -> bool:
        try:
            from Xlib.display import Display
            from Xlib.ext import record
            from Xlib import X
        except ImportError:
            logger.warning("python-xlib not installed — X11 input events unavailable")
            return False

        try:
            self._display = Display()
        except Exception as e:
            logger.warning("Cannot open X display: %s", e)
            return False

        try:
            if not self._display.has_extension("RECORD"):
                logger.warning("XRecord extension not available on this X server")
                self._display.close()
                return False
        except Exception as e:
            logger.warning("XRecord extension check failed: %s", e)
            self._display.close()
            return False

        import sys

        if sys.byteorder == "little":
            self._byte_order = "<"
        else:
            self._byte_order = ">"

        # Build Record_Range with device_events covering KeyPress..ButtonRelease.
        # python-xlib's Struct.to_binary expects flat tuples matching structvalues per field.
        # Record_Range fields: core_requests(R8=2), core_replies(R8=2),
        # ext_requests(ExtRange=4), ext_replies(ExtRange=4),
        # delivered_events(R8=2), device_events(R8=2), errors(R8=2),
        # client_started(Bool=1), client_died(Bool=1)
        z = 0
        range_spec = (
            (z, z),  # core_requests
            (z, z),  # core_replies
            (z, z, z, z),  # ext_requests (maj_range8 + min_range16)
            (z, z, z, z),  # ext_replies
            (z, z),  # delivered_events
            (X.KeyPress, X.ButtonRelease),  # device_events: capture all input events
            (z, z),  # errors
            False,  # client_started
            False,  # client_died
        )

        try:
            self._context = record.create_context(
                self._display,
                0,  # datum_flags: no element header
                [record.AllClients],
                [range_spec],
            )
        except Exception as e:
            logger.warning("Failed to create XRecord context: %s", e)
            self._display.close()
            return False

        self._running = True
        self._thread = threading.Thread(target=self._record_loop, daemon=True)
        self._thread.start()
        logger.info("X11 XRecord listener started")
        return True

    def _record_loop(self) -> None:
        from Xlib.ext import record

        try:
            record.enable_context(self._display, self._context, self._on_record_data)
        except Exception as e:
            if self._running:
                logger.error("XRecord loop error: %s", e)
        finally:
            self._running = False

    def _on_record_data(self, reply: Any) -> None:
        """Parse XRecord reply data and dispatch to callbacks."""
        if reply is None or not reply.data:
            return

        data = reply.data
        if isinstance(data, bytes):
            raw = data
        else:
            raw = bytes(data)

        # X11 wire format for KeyPress/KeyRelease/ButtonPress/ButtonRelease:
        # Each record is exactly 32 bytes:
        #   [0]  type      BYTE   (1)
        #   [1]  detail    BYTE   (1)  keycode or button number
        #   [2]  sequence  CARD16 (2)
        #   [4]  time      CARD32 (4)
        #   [8]  root      CARD32 (4)
        #   [12] event     CARD32 (4)
        #   [16] child     CARD32 (4)
        #   [20] rootX     INT16  (2)
        #   [22] rootY     INT16  (2)
        #   [24] eventX    INT16  (2)
        #   [26] eventY    INT16  (2)
        #   [28] state     CARD16 (2)
        #   [30] sameScreen BOOL  (1)
        #   [31] pad       BYTE   (1)
        fmt = self._byte_order + "BBHIIIIhhhhHBx"
        rec_size = struct.calcsize(fmt)
        if rec_size != 32:
            logger.error("XRecord record size mismatch: %d != 32", rec_size)
            return

        offset = 0
        while offset + rec_size <= len(raw):
            chunk = raw[offset : offset + rec_size]
            offset += rec_size
            try:
                fields = struct.unpack(fmt, chunk)
            except struct.error:
                continue

            event_type = fields[0]
            detail = fields[1]
            root_x = fields[7]
            root_y = fields[8]
            state = fields[11]

            if event_type == _X_KeyPress:
                keysym = self._keycode_to_keysym(detail, state)
                key_name = keysym_to_name(keysym)
                mod = is_modifier(keysym)
                printable = is_printable_char(keysym)
                try:
                    self.on_key(keysym, key_name, mod, printable)
                except Exception as e:
                    logger.debug("key callback error: %s", e)

            elif event_type == _X_ButtonPress:
                try:
                    self.on_mouse(root_x, root_y, detail)
                except Exception as e:
                    logger.debug("mouse callback error: %s", e)

    def _keycode_to_keysym(self, keycode: int, state: int) -> int:
        """Convert keycode + modifier state to keysym via the display."""
        if self._display is None:
            return 0
        try:
            shift = bool(state & 0x01)
            index = 1 if shift else 0
            keysym = self._display.keycode_to_keysym(keycode, index)
            if keysym == 0:
                keysym = self._display.keycode_to_keysym(keycode, 0)
            return keysym or 0
        except Exception:
            return 0

    def stop(self) -> None:
        self._running = False
        try:
            if self._context is not None and self._display is not None:
                from Xlib.ext import record

                record.disable_context(self._display, self._context)
                record.free_context(self._display, self._context)
        except Exception as e:
            logger.debug("XRecord cleanup error: %s", e)
        try:
            if self._display:
                self._display.close()
                self._data_display.close()
        except Exception:
            pass
        self._display = None
        self._context = None


# ---------------------------------------------------------------------------
# Wayland listener via evdev (low-precision)
# ---------------------------------------------------------------------------


class WaylandEvdevListener(InputEventListener):
    """Wayland input listener using evdev.

    Opens /dev/input/event* devices to capture EV_KEY events.
    Mouse coordinates are reconstructed from relative movement —
    imprecise on multi-monitor setups.  Requires root or input group.

    In low-precision mode, hit-test falls back to AT-SPI focus
    events (no coordinate dependency).
    """

    def __init__(self, on_mouse: MouseCallback, on_key: KeyCallback) -> None:
        super().__init__(on_mouse, on_key)
        self._devices: list[Any] = []
        self._mouse_x = 0
        self._mouse_y = 0

    def start(self) -> bool:
        try:
            import evdev
        except ImportError:
            logger.warning("evdev not installed — Wayland input events unavailable")
            return False

        devices = []
        try:
            all_devs = [evdev.InputDevice(path) for path in evdev.list_devices()]
        except Exception as e:
            logger.warning("Cannot enumerate evdev devices: %s", e)
            return False

        for dev in all_devs:
            caps = dev.capabilities()
            if evdev.ecodes.EV_KEY in caps:
                key_codes = caps[evdev.ecodes.EV_KEY]
                # Keyboard device: has letter/number keys
                # Mouse device: has BTN_LEFT/BTN_RIGHT/BTN_MIDDLE
                has_btn = any(
                    c in (evdev.ecodes.BTN_LEFT, evdev.ecodes.BTN_RIGHT, evdev.ecodes.BTN_MIDDLE)
                    for c in key_codes
                )
                has_keys = (
                    any(evdev.ecodes.KEY_A <= c <= evdev.ecodes.KEY_Z for c in key_codes)
                    if hasattr(evdev.ecodes, "KEY_A")
                    else False
                )
                if has_btn or has_keys:
                    devices.append(dev)

        if not devices:
            logger.warning("No suitable evdev devices found (need root or input group)")
            return False

        self._devices = devices
        self._running = True
        self._thread = threading.Thread(target=self._evdev_loop, daemon=True)
        self._thread.start()
        logger.info("Wayland evdev listener started (%d devices)", len(devices))
        return True

    def _evdev_loop(self) -> None:
        import select

        try:
            import evdev
            from evdev import ecodes
        except ImportError:
            return

        dev_fds = {dev.fd: dev for dev in self._devices}
        while self._running:
            try:
                readable, _, _ = select.select(list(dev_fds.keys()), [], [], 0.5)
            except Exception:
                break

            for fd in readable:
                dev = dev_fds.get(fd)
                if dev is None:
                    continue
                try:
                    for event in dev.read():
                        if event.type == ecodes.EV_KEY:
                            self._handle_key_event(event, ecodes)
                        elif event.type == ecodes.EV_REL:
                            self._handle_rel_event(event, ecodes)
                except Exception:
                    continue

    def _handle_key_event(self, event: Any, ecodes: Any) -> None:
        """Handle EV_KEY events from evdev."""
        if event.value != 1:  # 1 = press, 0 = release, 2 = repeat
            return

        code = event.code
        btn_left = getattr(ecodes, "BTN_LEFT", 0x110)
        btn_right = getattr(ecodes, "BTN_RIGHT", 0x111)
        btn_middle = getattr(ecodes, "BTN_MIDDLE", 0x112)

        if code == btn_left:
            self.on_mouse(self._mouse_x, self._mouse_y, 1)
        elif code == btn_right:
            self.on_mouse(self._mouse_x, self._mouse_y, 3)
        elif code == btn_middle:
            self.on_mouse(self._mouse_x, self._mouse_y, 2)
        else:
            # Keyboard key — map evdev code to keysym (best-effort)
            key_name = self._evdev_code_to_name(code, ecodes)
            keysym = self._evdev_code_to_keysym(code, ecodes)
            mod = keysym in _MODIFIER_KEYSYMS
            printable = is_printable_char(keysym)
            try:
                self.on_key(keysym, key_name, mod, printable)
            except Exception as e:
                logger.debug("evdev key callback error: %s", e)

    def _handle_rel_event(self, event: Any, ecodes: Any) -> None:
        """Track mouse position from relative movement (low precision)."""
        rel_x = getattr(ecodes, "REL_X", 0)
        rel_y = getattr(ecodes, "REL_Y", 1)
        if event.code == rel_x:
            self._mouse_x += event.value
        elif event.code == rel_y:
            self._mouse_y += event.value

    def _evdev_code_to_name(self, code: int, ecodes: Any) -> str:
        """Map evdev key code to a readable name."""
        names = ecodes.KEY
        if code in names:
            return names[code]
        return f"evdev_{code}"

    def _evdev_code_to_keysym(self, code: int, ecodes: Any) -> int:
        """Best-effort mapping from evdev key code to X11 keysym."""
        # evdev KEY_A (30) -> X11 'a' keysym (0x0061)
        if hasattr(ecodes, "KEY_A"):
            if ecodes.KEY_A <= code <= ecodes.KEY_Z:
                letter = chr(ord("a") + (code - ecodes.KEY_A))
                return ord(letter) - (ord("a") - ord("A")) if False else ord(letter)
        if hasattr(ecodes, "KEY_ENTER"):
            if code == ecodes.KEY_ENTER:
                return 0xFF0D
        if hasattr(ecodes, "KEY_ESC"):
            if code == ecodes.KEY_ESC:
                return 0xFF1B
        if hasattr(ecodes, "KEY_BACKSPACE"):
            if code == ecodes.KEY_BACKSPACE:
                return 0xFF08
        if hasattr(ecodes, "KEY_TAB"):
            if code == ecodes.KEY_TAB:
                return 0xFF09
        if hasattr(ecodes, "KEY_SPACE"):
            if code == ecodes.KEY_SPACE:
                return 0x0020
        if hasattr(ecodes, "KEY_LEFTSHIFT"):
            if code in (ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTSHIFT):
                return 0xFFE1
        if hasattr(ecodes, "KEY_LEFTCTRL"):
            if code in (ecodes.KEY_LEFTCTRL, ecodes.KEY_RIGHTCTRL):
                return 0xFFE3
        if hasattr(ecodes, "KEY_LEFTALT"):
            if code in (ecodes.KEY_LEFTALT, ecodes.KEY_RIGHTALT):
                return 0xFFE9
        return 0

    def stop(self) -> None:
        self._running = False
        for dev in self._devices:
            try:
                dev.close()
            except Exception:
                pass
        self._devices = []


# ---------------------------------------------------------------------------
# Degraded listener (no-op fallback)
# ---------------------------------------------------------------------------


class DegradedListener(InputEventListener):
    """No-op listener used when XRecord and evdev are unavailable.

    The recorder falls back to AT-SPI focus events only and prints
    a warning at startup.
    """

    def start(self) -> bool:
        logger.warning(
            "Input event listener unavailable — "
            "recording will rely on AT-SPI focus events only (degraded mode). "
            "Install python-xlib (X11) or evdev (Wayland) for full input capture."
        )
        return False


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_input_listener(on_mouse: MouseCallback, on_key: KeyCallback) -> InputEventListener:
    """Create the best available input event listener for the current session.

    Detects X11 vs Wayland via XDG_SESSION_TYPE, then tries the
    appropriate backend.  Falls back to DegradedListener if neither
    is available.
    """
    session_type = os.environ.get("XDG_SESSION_TYPE", "").lower()

    if session_type == "wayland":
        listener: InputEventListener = WaylandEvdevListener(on_mouse, on_key)
        if not listener.start():
            listener = DegradedListener(on_mouse, on_key)
        return listener

    # Default to X11 (also works under XWayland)
    listener = X11RecordListener(on_mouse, on_key)
    if not listener.start():
        # If X11 fails and session is Wayland, try evdev
        if session_type != "wayland":
            listener = WaylandEvdevListener(on_mouse, on_key)
            if not listener.start():
                listener = DegradedListener(on_mouse, on_key)
        else:
            listener = DegradedListener(on_mouse, on_key)
    return listener
