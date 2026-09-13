# SPDX-License-Identifier: GPL-3.0-or-later
#
# Coat Bridge - a small, predictable Blender <-> 3D-Coat model bridge.

"""Background polling of the exchange folder.

Cheap on purpose: it only looks at the exchange folder when auto-pull is on and
Blender is idle in object mode.
"""

import traceback

import bpy

from . import bridge

INTERVAL = 2.0  # seconds between two checks


def poll(force=False):
    """One polling step.  Returns the delay before the next one (needed by
    bpy.app.timers).  force=True skips the "is it a good moment" checks; the
    test suite uses it to exercise this path headless."""
    try:
        p = bridge.prefs()
        if p is None or not p.auto_pull:
            return INTERVAL
        if not force and (bpy.app.background or bpy.app.is_job_running("RENDER")):
            return INTERVAL
        context = bpy.context
        if context.scene is None or context.mode != "OBJECT":
            return INTERVAL
        bridge.pull(context)
    except Exception:  # a broken poll must never kill the timer
        traceback.print_exc()
    return INTERVAL


def start():
    if not bpy.app.timers.is_registered(poll):
        bpy.app.timers.register(poll, first_interval=INTERVAL, persistent=True)


def stop():
    if bpy.app.timers.is_registered(poll):
        bpy.app.timers.unregister(poll)
