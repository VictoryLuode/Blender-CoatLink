# SPDX-License-Identifier: GPL-3.0-or-later
#
# CoatLink - read-only report of 3D-Coat's Sculpt Tree.
#
"""Write down what is actually in 3D-Coat's Sculpt Tree, and of what kind.

The one question this answers: did an AppLink import land as a *voxel volume* or as
a *surface*?  A node shows `V` for a voxel volume and `S` for a surface, which is the
same letter 3D-Coat prints next to the node itself, so the report can be checked
against the screen.

Run it inside 3D-Coat, either from the Python console::

    exec(open(r"<path to this file>", encoding="utf-8").read())

or drop a copy of it next to an empty ``import.txt`` in the AppLink exchange folder
named ``import.py`` - 3D-Coat runs that on its own and deletes both files.

Read-only, deliberately: it walks the tree, reads names, kinds and polygon counts,
and writes one text file.  It does not import, export, select, move, hide, delete or
change any geometry, and it does not touch the bridge's own signals.

The report goes to::

    ~/Documents/3DCoat/CoatLink-TreeReport.txt

"""
import os
import time

import coat

REPORT_NAME = "CoatLink-TreeReport.txt"


def report_path(root=None):
    """Where the report is written: 3D-Coat's own documents folder."""
    if root is None:
        root = os.path.join(os.path.expanduser("~"), "Documents", "3DCoat")
    return os.path.join(root, REPORT_NAME)


def kind_of(element):
    """`V` for a voxel volume, `S` for a surface, `?` when it cannot be told."""
    try:
        volume = element.Volume()
    except Exception:
        return "?"
    for name, letter in (("isVoxelized", "V"), ("isSurface", "S")):
        try:
            if getattr(volume, name)():
                return letter
        except Exception:
            continue
    return "?"


def polycount_of(element):
    try:
        return int(element.Volume().getPolycount())
    except Exception:
        return -1


def walk(element, depth, lines):
    if element is None:
        return
    try:
        name = element.name()
    except Exception:
        name = "?"
    try:
        sculpt = element.isSculptObject()
    except Exception:
        sculpt = False
    lines.append("%s%s[%s] %s  polys=%s%s"
                 % ("  " * depth, kind_of(element), "sculpt" if sculpt else "-",
                    name, polycount_of(element), "" if sculpt else ""))
    try:
        count = element.childCount()
    except Exception:
        return
    for index in range(count):
        walk(element.child(index), depth + 1, lines)


def build_report():
    lines = ["CoatLink - Sculpt Tree report",
             "written %s" % time.strftime("%Y-%m-%d %H:%M:%S"),
             ""]
    # every field is looked up and called inside the guard: the published stubs and
    # the running build do not always agree (Scene.currentRoom is in the stub for
    # 3D-Coat 2025.17 but not in the build), and a missing one must not end the report
    for label, name in (("scene file", "currentSceneFilepath"),
                        ("scene units", "GetSceneUnits"),
                        ("scene scale", "GetSceneScale")):
        try:
            lines.append("%s: %s" % (label, getattr(coat.Scene, name)()))
        except Exception as error:
            lines.append("%s: ? (%s)" % (label, error))
    lines.append("")
    lines.append("Sculpt Tree (V = voxel volume, S = surface):")
    walk(coat.Scene.sculptRoot(), 0, lines)
    try:
        current = coat.Scene.current()
        lines.append("")
        lines.append("current object: [%s] %s" % (kind_of(current), current.name()))
    except Exception as error:
        lines.append("current object: ? (%s)" % error)
    return "\n".join(lines) + "\n"


def main():
    text = build_report()
    path = report_path()
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    print(text)
    print("written to %s" % path)
    return path


main()
