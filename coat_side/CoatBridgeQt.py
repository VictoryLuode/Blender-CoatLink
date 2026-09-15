# SPDX-License-Identifier: GPL-3.0-or-later
#
# Coat Bridge - 3D-Coat side, Qt panel.  Copyright (C) 2026 VictoryLuode
#
# A Qt window living INSIDE 3D-Coat's process, the same way the shipped Python
# Terminal / Data Tree / AI Assistant panels work.  3D-Coat's own "QT" extension
# already pumps Qt events every frame (cModules/QT/QT.py -> app.processEvents()),
# so a plain script can create a window and it stays interactive: no cExtension,
# no event loop of our own, no second process, no IPC.  Every button talks to the
# 3D-Coat API directly through the shared logic in lib.py.
#
# Layout mirrors the Blender add-on's menu:
#
#     Send to Blender / Pull from Blender
#     Format [FBX|OBJ]
#     Detect / Folder / Start Blender / Remove launcher
#     status + detail + reopen hint
#
# The window remembers where it was left, and opening it twice raises the one
# that is already open.

import os
import sys

import coat

_HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else ""
if _HERE and _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import CoatBridgeLib as lib  # exchange logic + actions (no UI)

WINDOW_TITLE = "Coat Bridge"
WINDOW_WIDTH = 320
WINDOW_HEIGHT = 330
STATE_KEY = "window"

_window = [None]  # singleton so a second click raises instead of stacking

try:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import (QApplication, QComboBox, QFrame, QHBoxLayout, QLabel,
                                   QMainWindow, QPushButton, QVBoxLayout, QWidget)
    QT_ERROR = ""
except ImportError as exc:  # 3D-Coat built without the Qt module
    QT_ERROR = str(exc)


if not QT_ERROR:

    def _separator():
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        return line


    def _small(text):
        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet("color: palette(mid); font-size: 11px;")
        return label


    class BridgeWindow(QMainWindow):
        """The panel.  Everything it does is one call into lib."""

        def __init__(self, bridge):
            super().__init__()
            self.bridge = bridge
            self.setWindowTitle(WINDOW_TITLE)
            self.setMinimumWidth(WINDOW_WIDTH)

            central = QWidget()
            self.setCentralWidget(central)
            column = QVBoxLayout(central)
            column.setContentsMargins(10, 10, 10, 10)
            column.setSpacing(8)

            self.send_button = QPushButton("Send to Blender")
            self.send_button.setMinimumHeight(34)
            self.send_button.clicked.connect(lambda: self._run(self.bridge.SendToBlender))
            column.addWidget(self.send_button)

            self.pull_button = QPushButton("Pull from Blender")
            self.pull_button.setMinimumHeight(30)
            self.pull_button.clicked.connect(lambda: self._run(self.bridge.PullFromBlender))
            column.addWidget(self.pull_button)

            column.addWidget(_separator())

            column.addWidget(_separator())

            top = QHBoxLayout()
            self.detect_button = QPushButton("Detect")
            self.detect_button.clicked.connect(lambda: self._run(self.bridge.Detect))
            self.folder_button = QPushButton("Folder")
            self.folder_button.clicked.connect(lambda: self._run(self.bridge.OpenFolder))
            top.addWidget(self.detect_button)
            top.addWidget(self.folder_button)
            column.addLayout(top)

            bottom = QHBoxLayout()
            self.blender_button = QPushButton("Start Blender")
            self.blender_button.clicked.connect(lambda: self._run(self.bridge.StartBlender))
            self.remove_button = QPushButton("Remove launcher")
            self.remove_button.clicked.connect(lambda: self._run(self.bridge.RemoveLauncher))
            bottom.addWidget(self.blender_button)
            bottom.addWidget(self.remove_button)
            column.addLayout(bottom)

            column.addWidget(_separator())

            self.status_label = QLabel(self.bridge.status)
            self.status_label.setWordWrap(True)
            column.addWidget(self.status_label)
            self.detail_label = _small(self.bridge.detail)
            column.addWidget(self.detail_label)
            column.addWidget(_small(lib.REOPEN_HINT))
            column.addStretch(1)

            self._apply_saved_geometry()

            # keep the status fresh (a model can arrive while the panel is open)
            self.timer = QTimer(self)
            self.timer.setInterval(500)
            self.timer.timeout.connect(self.refresh)
            self.timer.start()

        # ---- behaviour ----------------------------------------------------

        def _run(self, action):
            try:
                action()
            except Exception as exc:  # surfaced, never swallowed
                self.bridge.status = "Error: %s" % exc
                self.bridge.detail = ""
            self.refresh()

        def refresh(self):
            self.status_label.setText(self.bridge.status or "")
            self.bridge.refresh_detail()
            self.detail_label.setText(self.bridge.detail or "")

        # ---- geometry -----------------------------------------------------

        def _apply_saved_geometry(self):
            saved = lib.load_state().get(STATE_KEY)
            if isinstance(saved, list) and len(saved) == 4:
                try:
                    self.setGeometry(*[int(value) for value in saved])
                    return
                except (TypeError, ValueError):
                    pass
            self.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
            screen = QApplication.primaryScreen()
            if screen is not None:
                area = screen.availableGeometry()
                # start next to the right-hand panel column
                self.move(area.right() - WINDOW_WIDTH - 30, area.top() + 80)

        def closeEvent(self, event):
            geometry = self.geometry()
            lib.save_state({STATE_KEY: [geometry.x(), geometry.y(),
                                               geometry.width(), geometry.height()]})
            if _window[0] is self:
                _window[0] = None
            super().closeEvent(event)


def main():
    """Open the panel, or bring the open one to the front."""
    if QT_ERROR:
        # no Qt in this build of 3D-Coat: the native dialog still works
        return lib.show_panel(force=True)

    if QApplication.instance() is None:
        return lib.show_panel(force=True)

    existing = _window[0]
    if existing is not None:
        existing.show()
        existing.raise_()
        existing.activateWindow()
        return existing

    lib.register_menu_item()
    lib.register_room_tools()
    window = BridgeWindow(lib.CoatBridgePanel())
    _window[0] = window
    window.show()
    return window


# 3D-Coat imports the script as a module and then runs it, so the call below is
# unconditional - exactly like every script 3D-Coat ships.  Importing this file
# from a test therefore opens the panel; use CoatBridgeLib for the logic.
lib.log("entry CoatBridgeQt as %r" % __name__)
main()

def _allow_rerun():
    """3D-Coat imports a script by module name and Python then caches it, so a
    second click on the same menu item / tool button would do nothing.

    Dropping ourselves from sys.modules makes the next click import and run this
    file again - but only from the NEXT FRAME, never during the import itself
    (popping mid-import makes the importer raise KeyError).
    """
    if __name__ in ("__main__", "<run_path>"):
        return  # runpy and direct execution cache nothing
    try:
        from PySide6.QtCore import QTimer

        QTimer.singleShot(0, lambda: sys.modules.pop(__name__, None))
    except Exception:
        pass  # no Qt in this build: the entry simply runs once per session


_allow_rerun()
