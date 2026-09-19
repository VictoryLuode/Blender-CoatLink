# SPDX-License-Identifier: GPL-3.0-or-later
#
# CoatLink - run inside 3D-Coat after an AppLink import (import.txt [pythonfile]).
#
"""Drop the parent node 3D-Coat puts around an imported model.

3D-Coat groups an imported file under a node named after it (`bridge.obj` ->
"bridge"), and Blender has no equivalent: a Send of Hull and Turret arrives as
`bridge > Hull, Turret` instead of `Hull, Turret`.  This script - which import.txt
hands to 3D-Coat with `[pythonfile ...]`, so it runs right after the import - moves
the imported objects up to the sculpt root and removes the parent that is left
empty, and the sculpt tree ends up looking like the Blender outliner.

Nothing is deleted except that empty parent, and every step is guarded: a failure
is written to the shared log and never interrupts the import.  This file is copied
into the exchange folder by the Blender side, so it has to work on its own - no
imports from the add-on.
"""

import os
import time

#: the parent 3D-Coat creates is named after the model file
MODEL_STEM = "bridge"

#: Set to True by the Blender side when the job asks for a voxel import (`[vox]`).
#: 3D-Coat has been landing multi-object imports in *surface* mode whatever the mode
#: line says, so when voxel was asked for, this makes sure it is what arrives.  The
#: flag is baked into the copy that goes into the exchange folder; the file itself
#: stays neutral so it can be read and tested.
VOXELIZE = False

#: same file the 3D-Coat side writes, so both halves of a trip land in one log
LOG_NAME = "CoatBridge.log"


def note(message):
    """Append one line to the shared log.  Never raises."""
    try:
        folder = os.path.join(os.path.expanduser("~"), "Documents", "3DCoat")
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, LOG_NAME), "a", encoding="utf-8", newline="\n") as handle:
            handle.write("%s | 3dcoat | %s\n" % (time.strftime("%H:%M:%S"), message))
    except Exception:
        pass


def move_to_root(child, root):
    """Move one node under the root; returns True when it got there.

    The index 3D-Coat wants for "append" is not documented, so both spellings are
    tried and the result is checked with parent() rather than assumed.
    """
    for index in (-1, root.childCount()):
        try:
            child.moveTo(root, index)
        except Exception:
            continue
        try:
            return child.parent() is root
        except Exception:
            return True
    return False


def flatten(coat, stem=MODEL_STEM):
    """Unparent every `<stem>` group that still has children.  Returns the count."""
    root = coat.Scene.sculptRoot()
    moved = 0
    for index in range(root.childCount()):
        group = root.child(index)
        try:
            if group is None or group.name() != stem or group.childCount() == 0:
                continue
        except Exception:
            continue
        # always take the first child and append it: the objects keep the order
        # Blender has, and the live index cannot skip one (the group shrinks as
        # they leave it, so stepping through indexes would)
        while True:
            try:
                if group.childCount() == 0:
                    break
                child = group.child(0)
            except Exception:
                break
            if child is None or not move_to_root(child, root):
                break
            moved += 1
        try:
            if group.childCount() == 0:
                group.remove()
        except Exception:
            pass
    return moved


def voxelize(coat, stem=MODEL_STEM):
    """Turn the objects inside every `<stem>` group into voxel volumes.

    Only the leaves are converted: the group itself is packaging, so converting it
    would leave an extra volume behind.  Objects already voxelized are skipped, which
    makes a second run harmless.  Returns (converted, already, failed).
    """
    root = coat.Scene.sculptRoot()
    converted = already = failed = 0
    for index in range(root.childCount()):
        group = root.child(index)
        try:
            if group is None or group.name() != stem:
                continue
            count = group.childCount()
        except Exception:
            continue
        for child_index in range(count):
            try:
                child = group.child(child_index)
                volume = child.Volume()
                if volume.isVoxelized():
                    already += 1
                    continue
                volume.toVoxels()
                converted += 1
            except Exception:
                failed += 1
    return converted, already, failed


def main():
    try:
        import coat
    except Exception as exc:                      # not running inside 3D-Coat
        note("after-import helper skipped: %s" % exc)
        return 0
    converted = already = failed = 0
    if VOXELIZE:
        try:
            converted, already, failed = voxelize(coat)
        except Exception as exc:
            note("could not voxelize the import: %s" % exc)
    try:
        moved = flatten(coat)
    except Exception as exc:
        note("could not flatten the import parent: %s" % exc)
        moved = 0
    # one line on every run, including a run with nothing to do: the Blender side reads
    # it to tell "3D-Coat ran the after-import step" from "3D-Coat never ran it", and
    # that difference is invisible otherwise
    note("after-import ran: %d moved, %d to voxels, %d already voxel, %d failed"
         % (moved, converted, already, failed))
    return moved


if __name__ == "__main__":
    main()
