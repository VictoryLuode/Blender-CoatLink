# SPDX-License-Identifier: GPL-3.0-or-later
#
# Coat Bridge - Send to Blender tool button.  Runs headless: no window, no dialog.
# 3D-Coat imports a script as a module and then runs it, so the call at the
# bottom is unconditional, exactly like every script 3D-Coat ships.

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else ""
if _HERE and _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import CoatBridgeLib as lib

lib.log("entry CoatBridge_Send as %r" % __name__)
lib.run_action("CoatBridge_Send")


# 3D-Coat imports a script by module name and Python then caches it, so a second
# click on the same menu item / tool button would do nothing.  Dropping ourselves
# from sys.modules makes the next click import and run this file again.  Guarded,
# because runpy (used by the tests and by "run this file") owns its own key.
if __name__ not in ("__main__", "<run_path>"):
    sys.modules.pop(__name__, None)
