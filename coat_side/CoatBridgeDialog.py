# SPDX-License-Identifier: GPL-3.0-or-later
#
# Coat Bridge - native-dialog entry point.
#
# 3D-Coat imports a script as a module and then has it run, so the call at the
# bottom is unconditional - exactly like every script 3D-Coat ships.  The heavy
# lifting lives in CoatBridgeLib.py, which is import-safe.

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else ""
if _HERE and _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import CoatBridgeLib as lib

lib.log("entry CoatBridgeDialog as %r" % __name__)
lib.register_menu_item()
lib.register_room_tools()
lib.show_panel()
