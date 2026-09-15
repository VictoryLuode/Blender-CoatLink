# SPDX-License-Identifier: GPL-3.0-or-later
#
# Coat Bridge - setup / Detect tool button.  Runs headless: no window, no dialog.
# 3D-Coat imports a script as a module and then runs it, so the call at the
# bottom is unconditional, exactly like every script 3D-Coat ships.

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else ""
if _HERE and _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import CoatBridgeLib as lib

lib.log("entry CoatBridge_Setup as %r" % __name__)
lib.run_action("CoatBridge_Setup")
