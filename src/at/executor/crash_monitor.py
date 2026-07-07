# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only
"""Process crash monitor — checks app liveness between test steps."""

from __future__ import annotations

import os


class CrashMonitor:
    def __init__(self) -> None:
        self._app_name: str = ""
        self._pid: int = -1
        self._active: bool = False
        self._crash_reason: str = ""

    def start(self, app_name: str, pid: int) -> None:
        self._app_name = app_name
        self._pid = pid
        self._active = True
        self._crash_reason = ""

    def check(self) -> bool:
        if not self._active:
            if self._crash_reason:
                return False
            return True
        if self._pid <= 0:
            return True
        try:
            os.kill(self._pid, 0)
        except ProcessLookupError:
            self._crash_reason = f"{self._app_name} (pid {self._pid}) process not found"
            self._active = False
            return False
        except PermissionError:
            return True
        return True

    @property
    def crash_reason(self) -> str:
        return self._crash_reason

    @property
    def active(self) -> bool:
        return self._active

    def stop(self) -> None:
        self._active = False
