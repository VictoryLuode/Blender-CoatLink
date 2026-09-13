# SPDX-License-Identifier: GPL-3.0-or-later
"""Headless end-to-end test for Coat Bridge.

Run it with tests/run_tests.sh - it prepares a throwaway Blender script folder,
enables the add-on there and drives a full send/pull round trip without ever
touching the real 3D-Coat exchange folder.
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


EXCHANGE = _arg("--exchange")
REPORT = _arg("--report")
RESULTS = []


def check(name, condition, detail=""):
    RESULTS.append({"name": name, "ok": bool(condition), "detail": str(detail)})
    if condition:
        print("PASS  %s" % name)
    else:
        print("FAIL  %s   <- %s" % (name, detail))


def write(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def read(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def mesh_count():
    return len([obj for obj in bpy.data.objects if obj.type == "MESH"])


def main():
    os.makedirs(EXCHANGE, exist_ok=True)

    enabled = bpy.ops.preferences.addon_enable(module="coat_bridge")
    check("add-on enables", "FINISHED" in enabled, enabled)
    from coat_bridge import applink, bridge, transfer, watcher

    prefs = bpy.context.preferences.addons["coat_bridge"].preferences
    check("preferences reachable", prefs is not None)
    check("panel registered", hasattr(bpy.types, "COATBRIDGE_PT_main"))
    check("operators registered",
          hasattr(bpy.types, "COATBRIDGE_OT_send") and hasattr(bpy.types, "COATBRIDGE_OT_pull"))
    check("per-object link property registered", hasattr(bpy.types.Object, "coat_bridge_file"))
    check("timer registered", bpy.app.timers.is_registered(watcher.poll))
    check("defaults are painting + obj", prefs.mode == "ppp" and prefs.fmt == "obj")

    # ---- format availability ----
    if not transfer.operator("export", "fbx"):
        transfer.ensure_module("fbx")
    for fmt in ("obj", "ply", "stl"):
        check("%s export/import available" % fmt,
              transfer.operator("export", fmt) is not None and transfer.operator("import", fmt) is not None,
              transfer.missing_reason(fmt))
    check("fbx enabled on demand",
          transfer.operator("export", "fbx") is not None and transfer.operator("import", "fbx") is not None,
          transfer.missing_reason("fbx"))

    prefs.exchange_folder = EXCHANGE
    prefs.auto_pull = True
    prefs.apply_textures = False
    prefs.interval = 2.0

    # ---- clean scene ----
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    for material in list(bpy.data.materials):
        bpy.data.materials.remove(material)

    bpy.ops.mesh.primitive_cube_add(size=2)
    cube = bpy.context.active_object
    cube.name = "BridgeCube"
    material = bpy.data.materials.new("BridgeMat")
    material.use_nodes = True
    cube.data.materials.append(material)

    # ---- send ----
    out_path = bridge.send(bpy.context)
    check("send writes the model", os.path.isfile(out_path), out_path)
    check("send writes the material library", os.path.isfile(os.path.splitext(out_path)[0] + ".mtl"))
    job = applink.import_txt(EXCHANGE)
    check("send writes import.txt", os.path.isfile(job))
    lines = read(job).splitlines()
    check("import.txt: model path first", lines[0].endswith("coat_bridge_out.obj"), lines)
    check("import.txt: return path second", lines[1].endswith("coat_bridge_back.obj"), lines)
    check("import.txt: mode line", "[ppp]" in lines, lines)
    check("import.txt: export preset", any(line.startswith("[export_preset ") for line in lines), lines)
    check("import.txt: skip flags", "[SkipImport]" in lines and "[SkipExport]" in lines, lines)
    check("import.txt: posix paths only", "\\" not in "".join(lines), lines)
    app_folder = applink.app_folder(EXCHANGE)
    check("AppLink folder complete",
          all(os.path.isfile(os.path.join(app_folder, name)) for name in ("run.txt", "extension.txt")),
          os.listdir(app_folder) if os.path.isdir(app_folder) else "missing")
    check("extension.txt follows the format", read(os.path.join(app_folder, "extension.txt")).strip() == "obj")
    check("send arms exactly one pending return", len(bridge.STATE["pending"]) == 1, bridge.STATE["pending"])
    check("UV set created for painting", len(cube.data.uv_layers) == 1)
    check("cube starts with 8 vertices", len(cube.data.vertices) == 8, len(cube.data.vertices))

    # ---- simulate 3D-Coat returning a denser model ----
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=1.6)
    returned = bpy.context.active_object
    back_path = os.path.join(EXCHANGE, "coat_bridge_back.obj")
    transfer.export_model(back_path, "obj", [returned], apply_modifiers=False)
    expected = len(returned.data.vertices)
    bpy.data.objects.remove(returned, do_unlink=True)
    signal = applink.export_txt_candidates(EXCHANGE)[0]
    write(signal, back_path + "\n")

    messages = bridge.pull(bpy.context, force=True)
    check("pull reports the target object", any("BridgeCube" in message for message in messages), messages)
    check("export.txt consumed", not os.path.isfile(signal))
    check("mesh replaced in place", len(cube.data.vertices) == expected,
          "%d != %d" % (len(cube.data.vertices), expected))
    check("object keeps its name", cube.name == "BridgeCube", cube.name)
    check("object keeps its material",
          bool(cube.material_slots) and cube.material_slots[0].material is material,
          cube.material_slots[0].material if cube.material_slots else "no slots")
    check("link recorded on the object", cube.get("coat_bridge_file") == back_path, cube.get("coat_bridge_file"))
    check("no stray imported object", mesh_count() == 1, mesh_count())
    check("returned file kept for the next round trip", os.path.isfile(back_path))
    check("second pull has nothing to do", bridge.pull(bpy.context) == [])

    # ---- a foreign export.txt belongs to the official AppLink ----
    foreign = os.path.join(EXCHANGE, "official_applink_model.obj")
    shutil.copy(back_path, foreign)
    write(signal, foreign + "\n")
    messages = bridge.pull(bpy.context, force=True)
    check("foreign signal kept for the other add-on", os.path.isfile(signal), messages)
    check("foreign model not imported", mesh_count() == 1, mesh_count())
    os.remove(signal)

    # ---- format switch keeps files and AppLink folder in sync ----
    prefs.fmt = "fbx"
    fbx_out = bridge.send(bpy.context)
    check("fbx round trip exports", os.path.isfile(fbx_out), fbx_out)
    check("extension.txt follows the format", read(os.path.join(app_folder, "extension.txt")).strip() == "fbx")
    prefs.fmt = "obj"
    bridge.send(bpy.context)

    # ---- the watcher pulls on its own ----
    bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=6, radius=0.5)
    small = bpy.context.active_object
    transfer.export_model(back_path, "obj", [small], apply_modifiers=False)
    small_verts = len(small.data.vertices)
    bpy.data.objects.remove(small, do_unlink=True)
    write(signal, back_path + "\n")
    delay = watcher.poll(force=True)
    check("watcher returns the polling interval", abs(delay - prefs.interval) < 1e-6, delay)
    check("watcher pulls automatically", len(cube.data.vertices) == small_verts, len(cube.data.vertices))

    prefs.auto_pull = False
    write(signal, back_path + "\n")
    watcher.poll(force=True)
    check("auto pull off leaves the signal alone", os.path.isfile(signal))
    os.remove(signal)
    prefs.auto_pull = True

    # ---- texture hand-off ----
    texture_path = os.path.join(EXCHANGE, "BridgeMat_diffuse.png")
    image = bpy.data.images.new("bridge_test_tex", 16, 16)
    image.filepath_raw = texture_path
    image.file_format = "PNG"
    image.save()
    write(applink.textures_txt(EXCHANGE),
          "BridgeMat\nBridgeMat\ndiffuse\n%s\n"
          "BridgeMat\nBridgeMat\nroughness\n%s\n"
          "BridgeMat\nBridgeMat\nheight\n%s\n" % (texture_path, texture_path, texture_path))
    prefs.apply_textures = True
    write(signal, back_path + "\n")
    messages = bridge.pull(bpy.context, force=True)
    nodes = material.node_tree.nodes
    base = nodes.get("CoatBridge base_color")
    check("base colour map wired", base is not None and base.image is not None,
          [node.name for node in nodes])
    check("base colour reaches the Principled BSDF",
          any(link.to_socket.name == "Base Color" for link in material.node_tree.links))
    check("roughness map wired and non-colour",
          nodes.get("CoatBridge roughness") is not None
          and nodes["CoatBridge roughness"].image.colorspace_settings.name == "Non-Color")
    check("unsupported map reported", any("height" in message for message in messages), messages)
    prefs.apply_textures = False

    # ---- errors are surfaced, not swallowed ----
    prefs.exchange_folder = os.path.join(EXCHANGE, "does_not_exist")
    try:
        bridge.send(bpy.context)
        check("send fails loudly on a missing folder", False, "no exception")
    except RuntimeError as exc:
        check("send fails loudly on a missing folder", True, exc)
    prefs.exchange_folder = EXCHANGE

    # ---- status surface ----
    check("status text set", bool(bridge.status(bpy.context)), bridge.status(bpy.context))
    check("details list the exchange folder",
          any(line.startswith("Exchange:") for line in bridge.detail_lines(bpy.context)))


try:
    main()
except Exception:
    import traceback
    traceback.print_exc()
    RESULTS.append({"name": "suite ran", "ok": False, "detail": traceback.format_exc().splitlines()[-1]})

failed = [item for item in RESULTS if not item["ok"]]
print("\nRESULT: %d/%d checks passed" % (len(RESULTS) - len(failed), len(RESULTS)))
if REPORT:
    with open(REPORT, "w", encoding="utf-8") as handle:
        json.dump({"passed": len(RESULTS) - len(failed), "total": len(RESULTS), "checks": RESULTS},
                  handle, indent=2)
for item in failed:
    print("FAILED: %s -- %s" % (item["name"], item["detail"]))
sys.stdout.flush()
os._exit(1 if failed else 0)
