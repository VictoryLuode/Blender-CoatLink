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
import sys
import time
from datetime import datetime

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


def documents_folder():
    """Windows' own answer for the Documents folder, then the plain guess.

    Documents can be redirected (OneDrive, another drive), and 3D-Coat follows the
    real one - so this does too, instead of assuming ``~/Documents``.
    """
    override = os.environ.get("COATLINK_DOCS")
    if override:
        return override
    try:
        import ctypes

        buffer = ctypes.create_unicode_buffer(1024)
        # CSIDL_PERSONAL = 5
        if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buffer) == 0 and buffer.value:
            return buffer.value
    except Exception:
        pass
    return os.path.join(os.path.expanduser("~"), "Documents")


def shared_log_path():
    """The log the 3D-Coat side and the Blender side both write to.

    The folder is the one 3D-Coat is actually using.  It is named after the version
    on recent builds (``3DCoat2025``, ``3DCoat2026``) and carried a hyphen in the
    4.x line, so it is looked up rather than assumed; the folder 3D-Coat has
    already written to wins, because that is the one in use.
    """
    base = documents_folder()
    try:
        names = os.listdir(base)
    except OSError:
        names = []
    candidates = []
    for name in names:
        low = name.lower()
        if not (low.startswith("3dcoat") or low.startswith("3d-coat")):
            continue
        folder = os.path.join(base, name)
        if os.path.isdir(folder):
            candidates.append(folder)
    candidates.sort(key=lambda folder: (
        os.path.isfile(os.path.join(folder, "CoatBridge.json")),
        os.path.basename(folder).lower()), reverse=True)
    folder = candidates[0] if candidates else os.path.join(base, "3DCoat")
    return os.path.join(folder, LOG_NAME)


def note(message):
    """Append one line to the shared log.  Never raises."""
    try:
        path = shared_log_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8", newline="\n") as handle:
            handle.write("%s | 3dcoat | %s\n" % (
                datetime.now().isoformat(sep=" ", timespec="microseconds"), message))
    except Exception:
        pass


def helper_path():
    """This script's own path, or "" when 3D-Coat does not say what it ran."""
    for candidate in (globals().get("__file__"), sys.argv[0] if sys.argv else ""):
        if not candidate:
            continue
        try:
            return os.path.abspath(candidate)
        except Exception:
            pass
    return ""


def marker_path():
    """The note beside this script that says the helper ran at all."""
    path = helper_path()
    return (path + ".ran") if path else ""


def mark_started():
    '''Leave a trace before touching anything else.

    A build that ignores ``[pythonfile ...]`` leaves nothing behind, and so does a
    run whose log cannot be reached - from the outside the two look identical, which
    is why "did the step run at all?" stayed unproven for so long.  This writes a
    dated file next to the helper (a folder we know is writable: the Blender side
    just put the helper there) and, best effort, the same note in the shared log.

    It is evidence that the helper ran, and nothing more: it says nothing about
    whether the unparenting or the voxel step then succeeded.
    '''
    stamp = datetime.now().isoformat(sep=" ", timespec="microseconds")
    path = marker_path()
    if path:
        try:
            with open(path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write("%s | the after-import helper started\n" % stamp)
        except Exception:
            pass
    note("after-import helper started")



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
    mark_started()
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
    # Best-effort execution evidence; absence cannot prove the helper never ran.
    note("after-import ran: %d moved, %d to voxels, %d already voxel, %d failed"
         % (moved, converted, already, failed))
    return moved


if __name__ == "__main__":
    main()
