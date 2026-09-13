# SPDX-License-Identifier: GPL-3.0-or-later
#
# Coat Bridge - a small, predictable Blender <-> 3D-Coat model bridge.

"""Background polling of the exchange folder.

The timer is cheap on purpose: it only reads the exchange folder when
auto-pull is on and Blender is idle in object mode.
"""

import traceback

import bpy

from . import bridge

_DEFAULT_INTERVAL = 2.0


def interval():
    p = bridge.prefs()
    return float(p.interval) if p is not None else _DEFAULT_INTERVAL


def poll(force=False):
    """One polling step.  Returns the delay before the next one (needed by
    bpy.app.timers).  force=True skips the "is it a good moment" checks; the
    test suite uses it to exercise this path headless."""
    delay = interval()
    try:
        p = bridge.prefs()
        if p is None or not p.auto_pull:
            return delay
        if not force and (bpy.app.background or bpy.app.is_job_running("RENDER")):
            return delay
        context = bpy.context
        if context.scene is None or context.mode != "OBJECT":
            return delay
        bridge.pull(context)
    except Exception:  # a broken poll must never kill the timer
        traceback.print_exc()
    return delay


def start():
    if not bpy.app.timers.is_registered(poll):
        bpy.app.timers.register(poll, first_interval=_DEFAULT_INTERVAL, persistent=True)


def stop():
    if bpy.app.timers.is_registered(poll):
        bpy.app.timers.unregister(poll)
