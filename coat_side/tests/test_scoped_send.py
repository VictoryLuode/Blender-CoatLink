# SPDX-License-Identifier: GPL-3.0-or-later
"""Send hands over the node selected in the sculpt tree - and nothing else.

The bridge used to send the whole scene (3D-Coat's own export target).  Now the
default scope is the selected node plus its children, extracted straight from the
tree, so a sculpt-in-progress scene cannot leak into Blender by accident.

Fake 3D-Coat: the numbers below prove what our code asks 3D-Coat for, not what
3D-Coat does with the request.  The live round trip still has to be confirmed.
"""

import importlib.util
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fake_coat import UNSET, build_environment  # shared fake 3D-Coat API  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, "..", "CoatLinkLib.py")

FAILURES = []


def check(name, ok, detail=None):
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> %r" % (detail,)))
    if not ok:
        FAILURES.append(name)


def import_script():
    spec = importlib.util.spec_from_file_location("coatlink_scope_lib", LIB)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def obj_counts(path):
    vertices = faces = groups = 0
    with open(path, encoding="utf-8") as stream:
        for line in stream:
            if line.startswith("v "):
                vertices += 1
            elif line.startswith("f "):
                faces += 1
            elif line.startswith(("o ", "g ")):
                groups += 1
    return vertices, faces, groups


def main():
    tmp = tempfile.mkdtemp(prefix="coat_scope_send.")
    root = os.path.join(tmp, "Documents", "3DCoat", "Exchange")
    os.makedirs(root, exist_ok=True)
    coat, cmd = build_environment(tmp)
    bridge = import_script()
    bridge.documents_bases = lambda: [os.path.join(tmp, "Documents")]
    bridge.candidate_roots = lambda: [root]
    bridge.exchange_roots = lambda: [root]
    panel = bridge.CoatLinkPanel()

    check("the default scope is the selected tree node", bridge.send_scope() == "selected",
          bridge.send_scope())
    check("the panel offers the scope as a native droplist",
          any(item.startswith("SendScope,[") for item in panel.ui()), panel.ui()[:4])

    # ---- the happy path: only the selected node, with its children -----------
    model = bridge.model_path(root, "obj")
    coat.mesh_template = {"names": ["Hull", "Turret"], "faces": 2}   # a parent node with children
    panel.SendToBlender()
    mesh = coat.meshes[-1]

    check("the tree's current node is what gets exported",
          mesh.calls and mesh.calls[0][0] == "fromVolume", mesh.calls)
    check("the whole subtree comes along", mesh.calls[0][1] is True, mesh.calls)
    check("no other selection is dragged in", mesh.calls[0][2] is False, mesh.calls)
    check("the model lands in our folder", os.path.isfile(model))
    vertices, faces, groups = obj_counts(model)
    check("the exported OBJ has geometry and one group per object",
          vertices == 6 and faces == 2 and groups == 2, (vertices, faces, groups))
    check("Blender is told about it", os.path.isfile(bridge.signal_path(root)))
    check("the status names the objects and the scope",
          "Hull, Turret" in panel.status and "selected node" in panel.status, panel.status)
    check("the file it reports is the one it wrote",
          os.path.normcase(open(bridge.signal_path(root)).read().strip()) == os.path.normcase(model))

    # ---- the wrap 3D-Coat puts around a Blender import is not sent back as an object --
    def wrapped_write(path):              # the wrap first, then the objects, as measured
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("g bridge\ng Hull\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n"
                         "g Turret\nv 3 0 0\nv 4 0 0\nv 3 1 0\nf 4 5 6\n")
        return True

    cmd.volumes = {"Hull": "NothingLikeThis", "Turret": "NothingLikeThis"}
    coat.mesh_template = {"names": ["bridge", "Hull", "Turret"], "faces": 2,
                          "face_objects": [1, 2], "write": wrapped_write}
    os.remove(bridge.signal_path(root))
    panel.SendToBlender()
    body = open(model, encoding="utf-8").read()
    vertices, faces, groups = obj_counts(model)
    check("the wrap 3D-Coat made for our own model is not sent as an object",
          groups == 2 and "bridge" not in body and "Hull, Turret" in panel.status,
          (groups, panel.status))
    check("the objects it wrapped still go, with their geometry",
          vertices == 6 and faces == 2, (vertices, faces))
    sent_nodes = json.load(open(bridge.shader_map_path(root), encoding="utf-8"))["nodes"]
    check("and the shader map does not carry the wrap either",
          sorted(sent_nodes) == ["Hull", "Turret"], sent_nodes)

    # ---- a reduction percentage means the same thing to 3D-Coat --------------
    bridge.set_reduction_percent(40)
    panel.SendToBlender()
    second = coat.meshes[-1]
    check("a stored percentage goes to 3D-Coat's reduced extraction",
          second.calls == [("fromReducedVolume", 40.0, True, False)], second.calls)
    check("the status still reports the reduction",
          "reduction requested 40%" in panel.status, panel.status)

    # ---- nothing selected: refuse, and never send the whole scene ------------
    os.remove(bridge.signal_path(root))
    bridge.set_reduction_percent(0)
    coat.current_element = None           # nothing selected in the tree
    cmd.calls[:] = []
    meshes_before = len(coat.meshes)
    with open(model, "w", encoding="utf-8") as handle:
        handle.write("# the previous return, must survive\n")
    panel.SendToBlender()
    check("with no selected node nothing is exported",
          len(coat.meshes) == meshes_before and cmd.calls == [],
          (len(coat.meshes), meshes_before, cmd.calls))
    check("and no signal is written", not os.path.isfile(bridge.signal_path(root)))
    check("the previous return file is left untouched",
          open(model, encoding="utf-8").read().startswith("# the previous return"))
    check("the panel says what to do", "Sculpt Tree" in panel.detail, panel.detail)

    # ---- a node with no exportable mesh is refused the same way -------------
    coat.current_element = UNSET
    coat.mesh_template = {"faces": 0}      # a parent node that holds no geometry
    panel.SendToBlender()
    check("an empty node is refused rather than guessed at",
          not os.path.isfile(bridge.signal_path(root)), panel.status)
    check("and the reason is reported", "no exportable" in panel.status, panel.status)

    # ---- a merged result is refused: groups must survive --------------------
    def merged_write(path):               # writes one group although two were asked
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("g Hull\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n")
        return True

    coat.mesh_template = {"names": ["Hull", "Turret"], "write": merged_write}
    panel.SendToBlender()
    check("a merge that loses the object groups is refused",
          not os.path.isfile(bridge.signal_path(root)), panel.status)

    # ---- the whole-scene route is still available, explicitly ---------------
    bridge.set_send_scope("scene")
    coat.applink_present = True
    coat.applink_export = lambda exchange_root: open(bridge.signal_path(exchange_root), "w").write(
        bridge.model_path(exchange_root, "obj") + "\n")
    coat.ui.cmd.return_value = lambda *args, **kwargs: coat.applink_export(root) or True
    panel.SendToBlender()
    check("asking for the whole scene uses 3D-Coat's own export",
          "whole scene" in panel.status, panel.status)
    check("the scope survives in the state file", bridge.send_scope() == "scene",
          bridge.load_state())
    bridge.set_send_scope("selected")

    print("\nRESULT: %s" % ("selected-node send checks passed" if not FAILURES
                            else "FAILED: " + ", ".join(FAILURES)))
    sys.stdout.flush()
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
