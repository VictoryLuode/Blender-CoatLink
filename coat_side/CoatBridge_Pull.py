# SPDX-License-Identifier: GPL-3.0-or-later
#
# Coat Bridge - Pull from Blender tool button.  Runs headless: no window, no dialog.
# 3D-Coat imports a script as a module and then runs it, so the call at the
# bottom is unconditional, exactly like every script 3D-Coat ships.

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else ""
if _HERE and _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import CoatBridgeLib as lib

lib.log("entry CoatBridge_Pull as %r" % __name__)
lib.run_action("CoatBridge_Pull")


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
