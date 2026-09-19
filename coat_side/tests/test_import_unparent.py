# SPDX-License-Identifier: GPL-3.0-or-later
"""An imported model must not end up under a "bridge" parent in 3D-Coat.

3D-Coat wraps an imported file in a node named after it, so a Send of Hull and
Turret would arrive as `bridge > Hull, Turret` while Blender shows them side by
side.  Two paths exist and both are checked here:

  * the AppLink import (Blender writes import.txt; 3D-Coat imports on its own) runs
    the script the job file carries - coat_bridge/after_import.py
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
HELPER = os.path.join(HERE, "..", "..", "coat_bridge", "after_import.py")

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
    bridge = load(LIB, "coat_bridge_unparent_lib")
    bridge.documents_bases = lambda: [os.path.join(tmp, "Documents")]
    bridge.candidate_roots = lambda: [root]
    bridge.exchange_roots = lambda: [root]

    # ---- the AppLink path: the script import.txt carries ----------------------
    helper = load(HELPER, "coatlink_after_import")
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
