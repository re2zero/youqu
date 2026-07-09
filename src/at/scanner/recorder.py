# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
#
# SPDX-License-Identifier: GPL-2.0-only

"""AT-SPI recording floating widget.

Provides a stay-on-top GUI for interactive state recording during
`youqu at dump`.  Replaces the terminal-based Enter/done loop.

Qt bindings are optional — import errors are caught at module level
so the rest of `src.at.scanner` remains usable without a GUI toolkit.
"""

import logging
import os
import signal
import time
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy Qt imports — everything stays None when PyQt6 is absent
# ---------------------------------------------------------------------------
try:
    from PyQt6.QtCore import Qt, QTimer, QPoint, pyqtSignal  # type: ignore[import-untyped]
    from PyQt6.QtGui import QMouseEvent  # type: ignore[import-untyped]
    from PyQt6.QtWidgets import (  # type: ignore[import-untyped]
        QApplication,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )
except ImportError:
    Qt = None  # type: ignore[assignment]
    QApplication = None  # type: ignore[assignment,misc]
    QWidget = None  # type: ignore[assignment,misc]
    QTimer = None  # type: ignore[assignment,misc]
    pyqtSignal = None  # type: ignore[assignment,misc]
    QVBoxLayout = None  # type: ignore[assignment,misc]
    QHBoxLayout = None  # type: ignore[assignment,misc]
    QLabel = None  # type: ignore[assignment,misc]
    QLineEdit = None  # type: ignore[assignment,misc]
    QPushButton = None  # type: ignore[assignment,misc]
    QMouseEvent = None  # type: ignore[assignment,misc]


def ensure_qapp() -> Any:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def qt_available() -> bool:
    return QApplication is not None


class ATRecorderWidget(QWidget):  # type: ignore[misc]

    stop_requested = pyqtSignal(str)
    finish_requested = pyqtSignal()

    _WFLAGS = (
        Qt.WindowType.Tool
        | Qt.WindowType.FramelessWindowHint
        | Qt.WindowType.WindowStaysOnTopHint
    )
    _WFLAGS_WAYLAND = (
        Qt.WindowType.Tool
        | Qt.WindowType.FramelessWindowHint
    )

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._drag_pos: Optional[QPoint] = None
        self._recording = False
        self._finished = False
        self._elapsed = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._setup_window()
        self._build_ui()

    def _setup_window(self) -> None:
        self.setWindowTitle("AT Recorder")
        self.setFixedSize(300, 155)
        if os.environ.get("XDG_SESSION_TYPE") == "wayland":
            logger.warning("Wayland detected: WindowStaysOnTopHint may not work")
            self.setWindowFlags(self._WFLAGS_WAYLAND)
        else:
            self.setWindowFlags(self._WFLAGS)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setStyleSheet(
            "QWidget { background:#2b2b2b; border-radius:8px; }"
        )

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 6, 10, 10)
        root.setSpacing(6)

        title = QLabel(" AT Recorder")
        title.setStyleSheet(
            "background:#2b2b2b; color:#fff; border-radius:6px; "
            "padding:4px 8px; font-weight:bold;"
        )
        root.addWidget(title)

        self.count_label = QLabel("Recorded: 0")
        self.count_label.setStyleSheet("color:#aaa; font-size:12px;")
        root.addWidget(self.count_label)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("State name (module or feature)")
        self.name_input.setStyleSheet(
            "padding:4px; border:1px solid #555; border-radius:4px; background:#3c3c3c; color:#fff;"
        )
        self.name_input.returnPressed.connect(self._on_toggle)
        root.addWidget(self.name_input)

        self.timer_label = QLabel("")
        self.timer_label.setStyleSheet("color:#4CAF50; font-size:14px; font-weight:bold;")
        self.timer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.timer_label)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self.toggle_btn = QPushButton("Start")
        self.toggle_btn.setStyleSheet(
            "padding:6px 14px; background:#4CAF50; color:#fff; border-radius:4px;"
        )
        self.toggle_btn.clicked.connect(self._on_toggle)
        btn_row.addWidget(self.toggle_btn)

        self.finish_btn = QPushButton("Done")
        self.finish_btn.setStyleSheet(
            "padding:6px 14px; background:#f44336; color:#fff; border-radius:4px;"
        )
        self.finish_btn.clicked.connect(self.finish_requested.emit)
        btn_row.addWidget(self.finish_btn)

        root.addLayout(btn_row)

    def _on_toggle(self) -> None:
        if self._recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self) -> None:
        self._recording = True
        self._elapsed = 0.0
        self.timer_label.setText("00:00")
        self.toggle_btn.setText("Stop")
        self.toggle_btn.setStyleSheet(
            "padding:6px 14px; background:#ff9800; color:#fff; border-radius:4px;"
        )
        self.name_input.setEnabled(False)
        self._timer.start(1000)

    def _stop_recording(self) -> None:
        self._recording = False
        self._timer.stop()
        label = self.name_input.text().strip() or ""
        self.stop_requested.emit(label)
        self.timer_label.setText("")
        self.toggle_btn.setText("Start")
        self.toggle_btn.setStyleSheet(
            "padding:6px 14px; background:#4CAF50; color:#fff; border-radius:4px;"
        )
        self.name_input.clear()
        self.name_input.setEnabled(True)
        self.name_input.setFocus()

    def _tick(self) -> None:
        self._elapsed += 1.0
        mins, secs = divmod(int(self._elapsed), 60)
        self.timer_label.setText(f"{mins:02d}:{secs:02d}")

    def update_count(self, n: int) -> None:
        self.count_label.setText(f"Recorded: {n}")

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
        if not self._finished:
            self.finish_requested.emit()


class ATRecorderManager:

    def __init__(
        self,
        app_name: str,
        states_dir: Path,
        on_capture: Callable[[str, int, Path], None],
    ) -> None:
        self.app_name = app_name
        self.states_dir = states_dir
        self.on_capture = on_capture
        self.state_index = 0
        self.widget: Optional[ATRecorderWidget] = None
        self._finished = False

    def start(self) -> None:
        if not qt_available():
            raise RuntimeError(
                "PyQt6 is required for GUI recording. "
                "Install it or use --no-record."
            )

        app = ensure_qapp()

        # Allow CTRL+C to quit the Qt event loop
        def _sigint_handler(sig, frame):
            if not self._finished:
                self._finished = True
            app.quit()

        signal.signal(signal.SIGINT, _sigint_handler)

        self.widget = ATRecorderWidget()
        self.widget.stop_requested.connect(self._handle_stop)
        self.widget.finish_requested.connect(self._handle_finish)
        self.widget.show()
        self.widget.raise_()
        self.widget.activateWindow()
        self.name_input = self.widget.name_input

        app.exec()
        logger.info("Recording finished, %d states captured", self.state_index)

    def _handle_stop(self, label: str) -> None:
        from src.at.scanner.atspi_dumper import dump_at_spi_tree
        from src.at.scanner.merger import write_runtime_dump

        if not label:
            label = f"unnamed_{self.state_index}"

        safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in label)
        state_tree = dump_at_spi_tree(self.app_name)

        if not state_tree:
            logger.warning(
                "App '%s' not found in AT-SPI tree — capture skipped", self.app_name
            )
            return

        state_path = self.states_dir / f"{self.state_index:02d}_{safe}.yaml"
        write_runtime_dump(
            state_tree,
            str(state_path),
            app_name=self.app_name,
            state_label=label,
        )
        logger.info("Captured state %d: %s -> %s", self.state_index, label, state_path)
        self.on_capture(label, self.state_index, state_path)
        self.state_index += 1
        if self.widget:
            self.widget.update_count(self.state_index)

    def _handle_finish(self) -> None:
        if self._finished:
            return
        self._finished = True
        if self.widget and self.widget._recording:
            self.widget._timer.stop()
            self.widget._recording = False
        if self.widget:
            self.widget.close()
        app = QApplication.instance()
        if app:
            app.quit()
