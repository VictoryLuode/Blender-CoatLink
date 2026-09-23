# SPDX-License-Identifier: GPL-3.0-or-later
"""Import a real 3D-Coat export through the bridge.

    tests/test_coat_export.sh <model-file> [export-format]

Copies a model freshly exported by 3D-Coat into a throwaway exchange root,
writes the matching export.txt the way 3D-Coat does, and checks that the bridge
pulls it, enables the right I/O add-on on demand and replaces a linked object.

Use it to re-verify the return leg after a 3D-Coat update:

    tests/test_coat_export.sh "C:/Users/x/Documents/3DCoat/Exchange/CoatLink/001.fbx"
"""

import json
import os
import shutil
import sys

import bpy


def _arg(name, default=""):
    argv = sys.argv
    if "--" in argv:
        rest = argv[argv.index("--") + 1:]
        if name in rest and rest.index(name) + 1 < len(rest):
            return rest[rest.index(name) + 1]
    return default


MODEL = _arg("--model")
EXCHANGE = _arg("--exchange")
REPORT = _arg("--report")
RESULTS = []


def check(name, condition, detail=""):
    RESULTS.append({"name": name, "ok": bool(condition), "detail": str(detail)})
    print("%-4s %s%s" % ("PASS" if condition else "FAIL", name, "" if condition else "   <- %s" % detail))


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def main():
    os.makedirs(EXCHANGE, exist_ok=True)
    check("model file exists", os.path.isfile(MODEL), MODEL)

    bpy.ops.preferences.addon_enable(module="coatlink")
    from coatlink import applink, bridge, transfer

    applink._candidate_exchange_folders = lambda: [os.path.normpath(EXCHANGE)]
    prefs = bpy.context.preferences.addons["coatlink"].preferences
    prefs.exchange_folder = EXCHANGE
    prefs.auto_pull = False

    # factory-startup ships a cube; clear the scene so the inventory is exact
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    for material in list(bpy.data.materials):
        bpy.data.materials.remove(material)

    # 3D-Coat drops the export into <root>/<App>/ and points export.txt at it.
    folder = applink.app_folder(EXCHANGE)
    os.makedirs(folder, exist_ok=True)
    landed = os.path.join(folder, os.path.basename(MODEL))
    shutil.copy(MODEL, landed)
    write(os.path.join(folder, "export.txt"), landed + "\n")
    write(os.path.join(folder, "textures.txt"), "")

    fmt = transfer.format_from_path(landed)
    check("3D-Coat's format is recognised", transfer.operator("import", fmt) is not None, fmt)
    check("its I/O add-on is enabled on demand", transfer.ensure_module(fmt), transfer.missing_reason(fmt))

    # an object that the send would have created and linked
    bpy.ops.mesh.primitive_cube_add(size=2)
    cube = bpy.context.active_object
    cube.name = "RoundTripTarget"
    bpy.ops.mesh.primitive_uv_sphere_add(segments=8, ring_count=4, radius=0.5)
    filler = bpy.context.active_object
    transfer.export_model(applink.model_path(EXCHANGE, fmt), fmt, [filler], apply_modifiers=False)
    bpy.data.objects.remove(filler, do_unlink=True)
    bridge.STATE["target"] = {"object": cube.name, "file": applink.model_path(EXCHANGE, fmt)}
    before = len(cube.data.vertices)

    messages = bridge.pull(bpy.context, force=True)
    after = len(cube.data.vertices)
    check("returns a model from 3D-Coat", any(cube.name in message for message in messages), messages)
    check("signal consumed", not os.path.isfile(os.path.join(folder, "export.txt")))
    check("geometry replaced", after != before and after > 0, "%d -> %d" % (before, after))
    check("object identity kept", cube.name == "RoundTripTarget")
    check("link recorded", cube.get("coatlink_file") == landed, cube.get("coatlink_file"))
    meshes = [obj for obj in bpy.data.objects if obj.type == "MESH"]
    check("every imported part is linked to the returned file",
          bool(meshes) and all(obj.get("coatlink_file") == landed for obj in meshes),
          [(obj.name, obj.get("coatlink_file")) for obj in meshes])
    print("     3D-Coat exported %d object(s): %s" % (len(messages), ", ".join(o.name for o in meshes)))
    print("     target: %d vertices, %d polygons; file %s" % (
        after, len(cube.data.polygons), os.path.basename(landed)))


try:
    main()
except Exception:
    import traceback
    traceback.print_exc()
    RESULTS.append({"name": "suite ran", "ok": False, "detail": str(sys.exc_info()[1])})

failed = [item for item in RESULTS if not item["ok"]]
print("\nRESULT: %d/%d checks passed" % (len(RESULTS) - len(failed), len(RESULTS)))
if REPORT:
    with open(REPORT, "w", encoding="utf-8") as handle:
        json.dump({"checks": RESULTS}, handle, indent=2)
sys.stdout.flush()
os._exit(1 if failed else 0)
