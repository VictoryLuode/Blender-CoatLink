# SPDX-License-Identifier: GPL-3.0-or-later
"""An imported model must not end up under a "bridge" parent in 3D-Coat.

3D-Coat wraps an imported file in a node named after it, so a Send of Hull and
Turret would arrive as `bridge > Hull, Turret` while Blender shows them side by
side.  Two paths exist and both are checked here:

  * the AppLink import (Blender writes import.txt; 3D-Coat imports on its own) runs
    the script the job file carries - coatlink/after_import.py
  * our own Pull button imports with Scene.importMesh and then unparents in code

Fake 3D-Coat: the tree operations are simulated, so this proves what the two code
paths do to a tree of this shape, not what 3D-Coat does with a live scene.
"""

import importlib.util
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fake_coat import TreeNode, build_environment  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, "..", "CoatBridgeLib.py")
HELPER = os.path.join(HERE, "..", "..", "coatlink", "after_import.py")

FAILURES = []


def check(name, ok, detail=None):
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> %r" % (detail,)))
    if not ok:
        FAILURES.append(name)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def bridge_imported_tree(coat, children=("Hull", "Turret"), group="bridge"):
    """The shape 3D-Coat leaves behind: Root > <group> > children."""
    coat.root.children.clear()
    wrapper = TreeNode(group, coat, coat.root)
    for name in children:
        TreeNode(name, coat, wrapper)
    return wrapper


def main():
    tmp = tempfile.mkdtemp(prefix="coat_unparent.")
    root = os.path.join(tmp, "Documents", "3DCoat", "Exchange")
    os.makedirs(root, exist_ok=True)
    coat, cmd = build_environment(tmp)
    bridge = load(LIB, "coatlink_unparent_lib")
    bridge.documents_bases = lambda: [os.path.join(tmp, "Documents")]
    bridge.candidate_roots = lambda: [root]
    bridge.exchange_roots = lambda: [root]

    # ---- the AppLink path: the script import.txt carries ----------------------
    # loaded from a copy, the way the Blender side puts it in the exchange root: the
    # helper writes its "I started" marker next to itself, and that must not land in
    # the checkout
    helper_copy = os.path.join(tmp, "CoatLink_AfterImport.py")
    with open(HELPER, "r", encoding="utf-8") as source, \
            open(helper_copy, "w", encoding="utf-8", newline="\n") as target:
        target.write(source.read())
    helper = load(helper_copy, "coatlink_after_import")
    wrapper = bridge_imported_tree(coat)
    moved = helper.flatten(coat)
    check("the helper finds the imported group and moves both objects", moved == 2, moved)
    check("the objects sit at the sculpt root now",
          [node.name() for node in coat.root.children] == ["Hull", "Turret"],
          [node.name() for node in coat.root.children])
    check("the empty wrapper is gone", "bridge" in coat.removed, coat.removed)
    check("moving out of a group is what 3D-Coat was asked to do",
          all(target == "Root" for _name, target, _index in coat.moves), coat.moves)

    # a second import of the same file: nothing left to flatten, nothing breaks
    check("running it again does nothing", helper.flatten(coat) == 0)

    # somebody else's group is left alone, even if it has children
    bridge_imported_tree(coat, children=("Something",), group="KeepMe")
    check("a group that is not ours is never touched", helper.flatten(coat) == 0,
          [node.name() for node in coat.root.children])
    check("and it is not removed", "KeepMe" not in coat.removed, coat.removed)

    # a tree with no wrapper at all: nothing happens, nothing raises
    coat.root.children.clear()
    check("a tree without a wrapper is fine", helper.flatten(coat) == 0)

    # ---- a voxel import: the same helper also voxelizes what arrived ----------
    class _Volume(object):
        def __init__(self, voxel):
            self.voxel = voxel
            self.converted = 0

        def isVoxelized(self):
            return self.voxel

        def toVoxels(self):
            self.converted += 1
            self.voxel = True

    coat.root.children.clear()
    wrapper = bridge_imported_tree(coat, children=("Hull", "Turret"))
    hull, turret = wrapper.children
    hull_volume, turret_volume = _Volume(False), _Volume(True)
    hull.Volume = lambda: hull_volume
    turret.Volume = lambda: turret_volume
    result = helper.voxelize(coat)
    check("a surface object in the group is converted", result == (1, 1, 0), result)
    check("the wrapper itself is not converted, only its objects",
          hull_volume.converted == 1 and turret_volume.converted == 0,
          (hull_volume.converted, turret_volume.converted))
    check("running it again converts nothing", helper.voxelize(coat) == (0, 2, 0))
    bridge_imported_tree(coat, children=("Something",), group="KeepMe")
    check("a group that is not ours is not converted", helper.voxelize(coat) == (0, 0, 0),
          helper.voxelize(coat))
    check("the add-on's copy ships with the flag off", helper.VOXELIZE is False)
    with open(HELPER, "r", encoding="utf-8") as handle:
        helper_text = handle.read()
    check("the flag is one plain line, so the Blender side can flip it",
          "VOXELIZE = False" in helper_text and "VOXELIZE = True" not in helper_text)

    # ---- and it always says it ran, even when there was nothing to do ----------
    coat.root.children.clear()
    helper.main()
    log_path = os.path.join(tmp, "Documents", "3DCoat", "CoatBridge.log")
    with open(log_path, "r", encoding="utf-8") as handle:
        log_text = handle.read()
    check("the helper leaves a line saying it ran",
          "after-import ran" in log_text, log_text[-200:])
    check("with the counts, so the Blender side can tell what it did",
          "0 moved, 0 to voxels" in log_text, log_text[-200:])
    bridge_imported_tree(coat, children=("Hull",))
    helper.main()
    with open(log_path, "r", encoding="utf-8") as handle:
        log_text = handle.read()
    check("and the counts follow the real work", "1 moved" in log_text, log_text[-200:])

    # ---- and the marker that says it ran at all --------------------------------
    # 3D-Coat only runs this file on a build that honours [pythonfile ...].  Without
    # the marker, "the step never ran" and "it ran with nowhere to write" look the
    # same from the Blender side, which is why the question stayed open so long.  It
    # is written before anything else is touched, and it claims only that: running.
    marker = helper.marker_path()
    check("the helper leaves a marker beside itself",
          marker == os.path.join(tmp, "CoatLink_AfterImport.py.ran") and os.path.isfile(marker),
          marker)
    with open(marker, "r", encoding="utf-8") as handle:
        marker_text = handle.read()
    check("dated, and saying it started rather than that it worked",
          marker_text[:4].isdigit() and "helper started" in marker_text, marker_text)

    # ---- and the import.py 3D-Coat runs by itself ------------------------------
    # The job file names the helper with [pythonfile ...], but that line is read without
    # being executed on 2025.17; what 3D-Coat does run is a file named import.py sitting
    # beside the job.  Generate the one the Blender side writes and run it against this
    # fake 3D-Coat: the tree has to come out unparented, and both notes have to appear.
    shim_path = os.path.join(tmp, "import.py")
    shim_marker = shim_path + ".ran"
    with open(shim_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(helper.import_shim_source(helper_copy, shim_marker))
    coat.root.children.clear()
    coat.moves.clear()
    coat.removed.clear()
    bridge_imported_tree(coat, children=("Hull", "Turret"))
    shim_text = open(shim_path, "r", encoding="utf-8").read()
    check("the generated import.py compiles inside 3D-Coat",
          bool(compile(shim_text, shim_path, "exec")))
    check("it names the helper by absolute path, so it needs no __file__ of its own",
          repr(helper_copy) in shim_text and os.path.isabs(helper_copy),
          shim_text.splitlines()[:6])
    exec(compile(shim_text, shim_path, "exec"), {"__name__": "__main__"})
    names = [node.name() for node in coat.root.children]
    check("running it unparents the import the way the helper does", names == ["Hull", "Turret"], names)
    check("the empty wrapper is gone", "bridge" in coat.removed, coat.removed)
    check("it says it ran before it did anything", os.path.isfile(shim_marker), shim_marker)
    check("and the helper behind it says so too",
          os.path.isfile(helper.marker_path()), helper.marker_path())

    # ---- our own Pull button: the same result through code --------------------
    coat.root.children.clear()
    coat.moves.clear()
    coat.removed.clear()
    model = os.path.join(root, "BlenderBridge", "bridge.obj")
    os.makedirs(os.path.dirname(model), exist_ok=True)
    with open(model, "w", encoding="utf-8") as handle:
        handle.write("o bridge\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n")
    bridge.write_signal(root, model)
    # the queue file names the model, so Pull takes exactly it
    with open(bridge.import_txt(root), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(os.path.abspath(model).replace("\\", "/") + "\n")
    panel = bridge.CoatBridgePanel()
    panel.PullFromBlender()
    names = [node.name() for node in coat.root.children]
    check("the pulled object is unparented too", names == ["Volume1"], names)
    check("the wrapper 3D-Coat created is gone", "bridge" in coat.removed, coat.removed)
    check("the panel says the object was unparented",
          "unparented 1 object" in panel.detail, panel.detail)
    check("the pull still reports the object",
          "Pulled" in panel.status and "bridge.obj" in panel.status, panel.status)

    # an import that comes back already flat must not be damaged
    coat.root.children.clear()
    coat.moves.clear()
    flat = TreeNode("Hull", coat, coat.root)
    check("an already flat import is left alone",
          bridge.flatten_imported_group(flat) == [] and coat.moves == [], coat.moves)

    print("\nRESULT: %s" % ("import-group checks passed" if not FAILURES
                            else "FAILED: " + ", ".join(FAILURES)))
    sys.stdout.flush()
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
