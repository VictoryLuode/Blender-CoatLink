# SPDX-License-Identifier: GPL-3.0-or-later
"""Headless end-to-end test for Coat Bridge.

Run it with tests/run_tests.sh - it prepares a throwaway Blender script folder,
enables the add-on there and drives a full send/pull round trip against two
temporary exchange roots (3D-Coat registers more than one).  The real exchange
folders are never touched.
"""

import json
import math
import os
import shutil
import sys
import tempfile

import bpy


def _arg(name, default=""):
    argv = sys.argv
    if "--" in argv:
        rest = argv[argv.index("--") + 1:]
        if name in rest and rest.index(name) + 1 < len(rest):
            return rest[rest.index(name) + 1]
    return default


EXCHANGE = _arg("--exchange")
OTHER_ROOT = EXCHANGE + "_other"
REPORT = _arg("--report")
RESULTS = []


def check(name, condition, detail=""):
    RESULTS.append({"name": name, "ok": bool(condition), "detail": str(detail)})
    if condition:
        print("PASS  %s" % name)
    else:
        print("FAIL  %s   <- %s" % (name, detail))


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def read(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def mesh_count():
    return len([obj for obj in bpy.data.objects if obj.type == "MESH"])


def norm(path):
    return os.path.normcase(os.path.normpath(path))


def main():
    os.makedirs(EXCHANGE, exist_ok=True)
    os.makedirs(OTHER_ROOT, exist_ok=True)

    enabled = bpy.ops.preferences.addon_enable(module="coat_bridge")
    check("add-on enables", "FINISHED" in enabled, enabled)
    from coat_bridge import applink, bridge, transfer, watcher

    # Keep the suite hermetic: 3D-Coat's real roots are replaced by two temp ones.
    applink._candidate_exchange_folders = lambda: [os.path.normpath(EXCHANGE), os.path.normpath(OTHER_ROOT)]

    prefs = bpy.context.preferences.addons["coat_bridge"].preferences
    check("preferences reachable", prefs is not None)
    check("menu panel registered", hasattr(bpy.types, "COATBRIDGE_PT_menu"))
    check("menu lives in the top bar",
          bpy.types.COATBRIDGE_PT_menu.bl_space_type == "TOPBAR"
          and bpy.types.COATBRIDGE_PT_menu.bl_region_type == "HEADER")
    hook = getattr(bpy.types, "TOPBAR_HT_upper_bar", None)
    if hook is None:
        print("note  top bar hook not available in this session - skipped")
    else:
        from coat_bridge import ui as coat_ui
        check("button hooked into the top bar",
              coat_ui.HOOK_INSTALLED and callable(coat_ui.topbar_drawer))

        # the bar itself: the settings menu, then Send and Pull drawn to its right
        entries = []

        class _Row(object):
            def popover(self, **kwargs):
                entries.append(("popover", kwargs.get("panel"), kwargs.get("text"), kwargs.get("icon")))

            def operator(self, idname, **kwargs):
                entries.append(("operator", idname, kwargs.get("text"), kwargs.get("icon")))

        class _Layout(object):
            def row(self, align=False):
                return _Row()

        class _Self(object):
            layout = _Layout()

        def _context(alignment):
            return type("Ctx", (), {"region": type("Region", (), {"alignment": alignment})()})()

        coat_ui.topbar_drawer(_Self(), _context("RIGHT"))
        check("the top bar draws the settings menu", entries[:1] ==
              [("popover", coat_ui.POPOVER_ID, "Coat Bridge", "COLLAPSEMENU")], entries)
        check("Send sits to the right of it",
              entries[1] == ("operator", "coatbridge.send", "Send", "EXPORT"), entries)
        check("and Pull next to Send",
              entries[2] == ("operator", "coatbridge.pull", "Pull", "IMPORT"), entries)
        check("the bar adds nothing on the left side", (coat_ui.topbar_drawer(_Self(), _context("LEFT")),
                                                        len(entries))[1] == 3, entries)
    check("no sidebar panel left", not hasattr(bpy.types, "COATBRIDGE_PT_main"))
    check("operators registered",
          hasattr(bpy.types, "COATBRIDGE_OT_send") and hasattr(bpy.types, "COATBRIDGE_OT_pull"))
    check("per-object link property registered", hasattr(bpy.types.Object, "coat_bridge_file"))
    check("timer registered", bpy.app.timers.is_registered(watcher.poll))
    check("defaults to per-pixel painting", prefs.mode == "ppp")
    check("there is no format option any more", not hasattr(prefs, "fmt"))
    check("the send format is fixed to OBJ", bridge.SEND_FORMAT == "obj")
    for gone in ("apply_textures", "preset", "interval", "skip_import", "skip_export"):
        check("no '%s' option left" % gone, not hasattr(prefs, gone))

    check("both exchange roots are used",
          [norm(root) for root in applink.exchange_roots(EXCHANGE)] == [norm(EXCHANGE), norm(OTHER_ROOT)],
          applink.exchange_roots(EXCHANGE))

    # ---- format availability ----
    if not transfer.operator("export", "fbx"):
        transfer.ensure_module("fbx")
    for fmt in ("obj", "ply", "stl", "fbx"):
        check("%s export/import available" % fmt,
              transfer.operator("export", fmt) is not None and transfer.operator("import", fmt) is not None,
              transfer.missing_reason(fmt))

    prefs.exchange_folder = EXCHANGE
    prefs.auto_pull = True
    prefs.skip_dialogs = True

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
    check("model goes into the BlenderBridge folder",
          norm(os.path.dirname(out_path)) == norm(applink.app_folder(EXCHANGE)), out_path)
    check("model has the fixed name bridge.obj", os.path.basename(out_path) == "bridge.obj", out_path)
    check("send writes the material library", os.path.isfile(os.path.splitext(out_path)[0] + ".mtl"))
    job = applink.import_txt(EXCHANGE)
    check("send writes import.txt at the root", os.path.isfile(job))
    lines = read(job).splitlines()
    check("import.txt: model path first", lines[0].endswith("BlenderBridge/bridge.obj"), lines)
    check("import.txt: return path second", lines[1].endswith("BlenderBridge/bridge_back.obj"), lines)
    check("import.txt: mode line third", lines[2] == "[ppp]", lines)
    check("import.txt: skip flags", lines[3:] == ["[SkipImport]", "[SkipExport]"], lines)
    check("import.txt: nothing else", len(lines) == 5, lines)
    check("import.txt: posix paths only", "\\" not in "".join(lines), lines)
    check("no import.txt inside the folder",
          not os.path.isfile(os.path.join(applink.app_folder(EXCHANGE), "import.txt")))
    check("job file only in the primary root", not os.path.isfile(applink.import_txt(OTHER_ROOT)))
    for root in (EXCHANGE, OTHER_ROOT):
        folder = applink.app_folder(root)
        check("AppLink folder ready in %s" % os.path.basename(root),
              os.path.isfile(os.path.join(folder, "run.txt")),
              os.listdir(folder) if os.path.isdir(folder) else "missing")
        check("no extension.txt in %s" % os.path.basename(root),
              not os.path.isfile(os.path.join(folder, "extension.txt")))
    check("send remembers the target object", bridge.STATE["target"]["object"] == "BridgeCube",
          bridge.STATE["target"])
    sent_diagonal = bridge.STATE["target"].get("diagonal") or 0.0
    check("send records the size for the scale check", abs(sent_diagonal - math.sqrt(3) * 2) < 0.02, sent_diagonal)
    check("UV set created for painting", len(cube.data.uv_layers) == 1)
    check("cube starts with 8 vertices", len(cube.data.vertices) == 8, len(cube.data.vertices))

    # ---- simulate 3D-Coat returning a denser model into the primary root ----
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=1.6)
    returned = bpy.context.active_object
    back_path = applink.model_path(EXCHANGE, "obj", name="bridge_back")
    transfer.export_model(back_path, "obj", [returned], apply_modifiers=False)
    expected = len(returned.data.vertices)
    bpy.data.objects.remove(returned, do_unlink=True)
    signal = applink.signal_files([EXCHANGE])[0]
    back_path_fbx = applink.model_path(EXCHANGE, "fbx", name="bridge_back")
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
    check("a size mismatch is undone on the way back", "scale x" in " ".join(messages), messages)
    check("the model is exactly the size it was sent at",
          abs(bridge._diagonal(cube) - sent_diagonal) < 0.02,
          (bridge._diagonal(cube), sent_diagonal))

    # ---- a return at the same size is left alone ----
    bridge.send(bpy.context)
    transfer.export_model(back_path, "obj", [cube], apply_modifiers=False)
    write(signal, back_path + "\n")
    messages = bridge.pull(bpy.context, force=True)
    check("a same-size return is not rescaled", "scale x" not in " ".join(messages), messages)

    # ---- and the whole check can be switched off ----
    prefs.match_scale = False
    bridge.send(bpy.context)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=6, radius=5.0)
    bigger = bpy.context.active_object
    transfer.export_model(back_path, "obj", [bigger], apply_modifiers=False)
    big_diagonal = bridge._diagonal(bigger)
    bpy.data.objects.remove(bigger, do_unlink=True)
    write(signal, back_path + "\n")
    messages = bridge.pull(bpy.context, force=True)
    check("with Match scale off the returned size is kept",
          abs(bridge._diagonal(cube) - big_diagonal) < 0.05 and "scale x" not in " ".join(messages),
          (round(bridge._diagonal(cube), 3), round(big_diagonal, 3), messages))
    prefs.match_scale = True

    # ---- "Import without materials" ----
    for mat in list(bpy.data.materials):      # start clean: earlier sections left orphans
        if mat.users == 0 and mat is not material:
            bpy.data.materials.remove(mat)
    prefs.strip_materials = True
    bridge.send(bpy.context)
    transfer.export_model(back_path, "obj", [cube], apply_modifiers=False)
    write(signal, back_path + "\n")
    messages = bridge.pull(bpy.context, force=True)
    check("the returned mesh comes back without materials", len(cube.material_slots) == 0,
          [slot.material for slot in cube.material_slots])
    check("only the user's own material is left in the file",
          [mat.name for mat in bpy.data.materials] == [material.name],
          [mat.name for mat in bpy.data.materials])
    check("the pull says materials were dropped", any("no materials" in message for message in messages), messages)
    prefs.strip_materials = False

    # ---- 3D-Coat's scale and axis: detected, then matched ----
    def obj_points(path):
        points = set()
        for line in read(path).splitlines():
            if line.startswith("v "):
                parts = line.split()
                points.add(tuple(round(float(value), 4) for value in parts[1:4]))
        return points

    coat_home = tempfile.mkdtemp(prefix="coat_state.")
    os.makedirs(os.path.join(coat_home, "3DCoat"), exist_ok=True)

    def write_coat_state(info):
        write(os.path.join(coat_home, "3DCoat", "CoatBridge.json"), json.dumps({"coat": info}))

    applink_bases = applink._documents_bases
    applink._documents_bases = lambda: [coat_home]
    prefs.coat_scale = 0.0
    prefs.axis_mode = "auto"

    check("without 3D-Coat's state the bridge stays neutral",
          bridge.transfer_scale(bpy.context)[0] == 1.0 and bridge.axis_swap(bpy.context) is None,
          (bridge.transfer_scale(bpy.context), bridge.axis_swap(bpy.context)))

    write_coat_state({"scene_scale": 100.0, "scene_units": "m", "swap_yz": True})
    scale, origin = bridge.transfer_scale(bpy.context)
    check("3D-Coat's scene scale is picked up", scale == 100.0 and "3D-Coat" in origin, (scale, origin))
    check("its swap Y/Z option is picked up", bridge.axis_swap(bpy.context) is True,
          bridge.axis_swap(bpy.context))

    # the plain model, then the same model as 3D-Coat wants it
    prefs.coat_scale = 1.0
    prefs.axis_mode = "normal"
    plain_path = bridge.send(bpy.context)
    plain = obj_points(plain_path)
    prefs.coat_scale = 0.0
    prefs.axis_mode = "auto"
    scaled_path = bridge.send(bpy.context)
    scaled = obj_points(scaled_path)

    def biggest(points):
        return max(abs(value) for point in points for value in point)

    def normalised(points, factor):
        return {tuple(value / factor for value in point) for point in points}

    def same_points(left, right, tolerance=0.01):
        left, right = sorted(left), sorted(right)
        return len(left) == len(right) and all(
            all(abs(a - b) < tolerance for a, b in zip(one, other))
            for one, other in zip(left, right))

    check("the model is sent 100x bigger, as 3D-Coat's own scale demands",
          abs(biggest(scaled) / biggest(plain) - 100.0) < 0.5, (biggest(plain), biggest(scaled)))
    check("and the Y/Z axes really are swapped in the file",
          same_points(normalised(scaled, 100.0), {(x, z, y) for x, y, z in plain}),
          (sorted(plain)[:2], sorted(normalised(scaled, 100.0))[:2]))
    check("the send says what it did", "x100" in bridge.STATE["message"] and "swap Y/Z" in bridge.STATE["message"],
          bridge.STATE["message"])
    check("the log says where the scale came from",
          "3D-Coat scene scale" in read(applink.shared_log_path()), read(applink.shared_log_path()).splitlines()[-1:])

    # a manual scale still wins, and "normal" axis means untouched
    prefs.coat_scale = 2.5
    prefs.axis_mode = "normal"
    manual_path = bridge.send(bpy.context)
    manual = obj_points(manual_path)
    check("a manual scale overrides 3D-Coat's number",
          abs(biggest(manual) / biggest(plain) - 2.5) < 0.01, (biggest(plain), biggest(manual)))
    check("and no axis swap is applied then", same_points(normalised(manual, 2.5), plain),
          sorted(manual)[:2])

    prefs.coat_scale = 0.0
    prefs.axis_mode = "auto"
    applink._documents_bases = applink_bases

    # ---- and the whole round trip is written to the shared log ----
    log_path = applink.shared_log_path()
    check("the shared log exists", os.path.isfile(log_path), log_path)
    if os.path.isfile(log_path):
        log_text = read(log_path)
        check("the log records the send size", "sent BridgeCube" in log_text, log_text[-200:])
        check("the log records the correction", "scale matched" in log_text, log_text[-200:])

    # ---- the second root is watched too (3D-Coat exports into its own root) ----
    own_app_signal = os.path.join(OTHER_ROOT, "BlenderBridge", "export.txt")
    write(own_app_signal, back_path + "\n")
    messages = bridge.pull(bpy.context, force=True)
    check("second root: app folder signal pulled",
          not os.path.isfile(own_app_signal) and any("BridgeCube" in m for m in messages), messages)

    own_root_signal = os.path.join(OTHER_ROOT, "export.txt")
    write(own_root_signal, back_path + "\n")
    bridge.pull(bpy.context, force=True)
    check("second root: plain export.txt pulled", not os.path.isfile(own_root_signal))

    # ---- a signal owned by the official AppLink stays untouched ----
    official = os.path.join(OTHER_ROOT, "Blender", "export.txt")
    write(official, os.path.join(OTHER_ROOT, "Blender", "001.fbx") + "\n")
    messages = bridge.pull(bpy.context, force=True)
    check("official AppLink signal left alone", os.path.isfile(official), messages)
    check("official signal did not import anything", mesh_count() == 1, mesh_count())
    os.remove(official)

    foreign = os.path.join(EXCHANGE, "official_applink_model.obj")
    shutil.copy(back_path, foreign)
    write(signal, foreign + "\n")
    messages = bridge.pull(bpy.context, force=True)
    check("foreign path in the primary root kept", os.path.isfile(signal), messages)
    check("foreign model not imported", mesh_count() == 1, mesh_count())
    os.remove(signal)

    # ---- whatever 3D-Coat returns is read by its extension ----
    bridge.send(bpy.context)
    transfer.export_model(back_path_fbx, "fbx", [cube], apply_modifiers=False)
    write(signal, back_path_fbx + "\n")
    messages = bridge.pull(bpy.context, force=True)
    check("an FBX return is imported without any format setting",
          any("BridgeCube" in message for message in messages), messages)
    check("no extension.txt appears",
          not os.path.isfile(os.path.join(applink.app_folder(EXCHANGE), "extension.txt")))

    # ---- the watcher pulls on its own ----
    bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=6, radius=0.5)
    small = bpy.context.active_object
    transfer.export_model(back_path, "obj", [small], apply_modifiers=False)
    small_verts = len(small.data.vertices)
    bpy.data.objects.remove(small, do_unlink=True)
    write(signal, back_path + "\n")
    delay = watcher.poll(force=True)
    check("watcher returns the polling interval", abs(delay - watcher.INTERVAL) < 1e-6, delay)
    check("watcher pulls automatically", len(cube.data.vertices) == small_verts, len(cube.data.vertices))

    prefs.auto_pull = False
    write(signal, back_path + "\n")
    watcher.poll(force=True)
    check("auto pull off leaves the signal alone", os.path.isfile(signal))
    os.remove(signal)
    prefs.auto_pull = True

    # ---- linking, unlinking, error paths, status ----
    check("unlink clears the link", _unlink_clears(cube))
    cube["coat_bridge_file"] = back_path

    prefs.exchange_folder = os.path.join(EXCHANGE, "does_not_exist")
    try:
        bridge.send(bpy.context)
        check("send fails loudly on a missing folder", False, "no exception")
    except RuntimeError as exc:
        check("send fails loudly on a missing folder", True, exc)
    prefs.exchange_folder = EXCHANGE

    check("status text set", bool(bridge.status(bpy.context)), bridge.status(bpy.context))
    check("details list the job file",
          any(line.startswith("Job file:") for line in bridge.detail_lines(bpy.context)),
          bridge.detail_lines(bpy.context))


def _unlink_clears(cube):
    cube["coat_bridge_file"] = "something"
    for obj in bpy.context.selected_objects:
        obj.select_set(False)
    cube.select_set(True)
    bpy.context.view_layer.objects.active = cube
    bpy.ops.coatbridge.unlink()
    return not cube.get("coat_bridge_file")


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
