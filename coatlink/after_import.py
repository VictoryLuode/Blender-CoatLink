# SPDX-License-Identifier: GPL-3.0-or-later
#
# CoatLink - run inside 3D-Coat after an AppLink import (as <root>/import.py).
#
"""Drop the parent node 3D-Coat puts around an imported model.

3D-Coat groups an imported file under a node named after it (`bridge.obj` ->
`bridge`), and Blender has no equivalent: a Send of Hull and Turret arrives as
`bridge > Hull, Turret` instead of `Hull, Turret`.  This script moves the imported
objects up to the sculpt root and removes the parent that is left empty, and the
sculpt tree ends up looking like the Blender outliner.

It is started in two ways, because one of them is not enough:

  * `<root>/import.py` - the file 3D-Coat runs itself when it finds it beside the job
    file, and deletes once the import is through (see IMPORT_SHIM).  This is the
    documented mechanism and the one that works.
  * `<root>/...` + `[pythonfile ...]` in the job file - the line is read (3D-Coat
    prints it in its log) but not executed on 2025.17, so it is kept only as a spare.

Nothing is deleted except that empty parent, and every step is guarded: a failure is
written to the shared log and never interrupts the import.  This file is copied into
the exchange folder by the Blender side, so it has to work on its own - no imports
from the add-on.
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
LOG_NAME = "CoatLink.log"

#: 3D-Coat runs a file with this name when it finds one beside the job file, and deletes
#: it - with the job file - once the import is through.  It is the documented way to run
#: a script after an AppLink import, and the only one that works: the `[pythonfile ...]`
#: line the job file also carries is read but not executed on 2025.17.
IMPORT_SHIM_NAME = "import.py"

#: The generated import.py.  @HELPER@ / @MARKER@ are replaced with absolute paths: it is
#: not known whether 3D-Coat gives this file a `__file__`, and baking the paths in cannot
#: be wrong.  It says it ran before it does anything, because "3D-Coat did not run it"
#: and "it ran and stopped at once" have to be told apart.  The helper is run by hand
#: rather than by its `__name__` guard, so a job file that starts this either as a script
#: or as a module still runs it exactly once.
IMPORT_SHIM = '''\
# Written by CoatLink for one job: 3D-Coat runs a file of this name when it finds it
# beside import.txt, then deletes it together with the job file.
HELPER = @HELPER@
MARKER = @MARKER@

import time

try:
    with open(MARKER, "w", encoding="utf-8", newline="\\n") as handle:
        handle.write("%s | import.py ran\\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
except Exception:
    pass

try:
    with open(HELPER, "r", encoding="utf-8") as handle:
        source = handle.read()
    namespace = {"__name__": "coatlink_after_import", "__file__": HELPER}
    exec(compile(source, HELPER, "exec"), namespace)
    namespace["main"]()
except Exception as exc:
    try:
        with open(MARKER, "a", encoding="utf-8", newline="\\n") as handle:
            handle.write("import.py could not run the helper: %r\\n" % (exc,))
    except Exception:
        pass
'''


def import_shim_source(helper_path, marker_path):
    """The text of the import.py job's own script, with both paths baked in."""
    return (IMPORT_SHIM
            .replace("@HELPER@", repr(helper_path))
            .replace("@MARKER@", repr(marker_path)))


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
        os.path.isfile(os.path.join(folder, "CoatLink.json")),
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
    """Unparent the group the import parked the model in.  Returns the count.

    Only the *last* group under the root that carries the stem is touched.  The import
    appends the node it parks the file in, so that is the one just created; an earlier
    group with the same name is the user's own, and taking every match would empty it
    into the root and then remove it - the user's own group, with the user's own
    objects in it, silently gone.  A group we did not create is left exactly as it is.
    """
    root = coat.Scene.sculptRoot()
    parked = None
    others = 0
    for index in range(root.childCount()):
        group = root.child(index)
        try:
            if group is None or group.name() != stem:
                continue
        except Exception:
            continue
        if parked is not None:
            others += 1
        parked = group
    if parked is None:
        return 0
    if others:
        note("left %d earlier '%s' group(s) alone: not ours to flatten" % (others, stem))
    try:
        if parked.childCount() == 0:
            return 0
    except Exception:
        return 0
    moved = 0
    # always take the first child and append it: the objects keep the order
    # Blender has, and the live index cannot skip one (the group shrinks as
    # they leave it, so stepping through indexes would)
    while True:
        try:
            if parked.childCount() == 0:
                break
            child = parked.child(0)
        except Exception:
            break
        if child is None or not move_to_root(child, root):
            break
        moved += 1
    try:
        if parked.childCount() == 0:
            parked.remove()
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
