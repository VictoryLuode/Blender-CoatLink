# SPDX-License-Identifier: GPL-3.0-or-later
"""Live round trip against a real, running 3D-Coat.

    tests/live_roundtrip.sh [--timeout SECONDS]

Sends a cube named BridgeTestCube into the real exchange folder, waits for
3D-Coat to consume the job file, then waits for the return signal (you press
File > Bring object back in 3D-Coat) and pulls it, reporting whether the object
was updated in place.

Nothing is written outside the exchange folder.
"""

import json
import os
import sys
import time

import bpy


def _arg(name, default=""):
    argv = sys.argv
    if "--" in argv:
        rest = argv[argv.index("--") + 1:]
        if name in rest and rest.index(name) + 1 < len(rest):
            return rest[rest.index(name) + 1]
    return default


def main():
    exchange = _arg("--exchange")
    timeout = float(_arg("--timeout", "900"))
    report_path = _arg("--report")
    report = {"exchange": exchange, "steps": []}

    def step(name, value):
        report["steps"].append({"step": name, "value": str(value)})
        print("[live] %-34s %s" % (name + ":", value))
        sys.stdout.flush()

    bpy.ops.preferences.addon_enable(module="coat_bridge")
    from coat_bridge import applink, bridge

    prefs = bpy.context.preferences.addons["coat_bridge"].preferences
    prefs.exchange_folder = exchange
    prefs.fmt = "obj"
    prefs.mode = "ppp"
    prefs.auto_pull = False  # this script drives the pulls itself
    prefs.skip_dialogs = True
    prefs.apply_modifiers = False

    step("coat running at start", applink.is_coat_running())

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    bpy.ops.mesh.primitive_cube_add(size=2, calc_uvs=True)
    cube = bpy.context.active_object
    cube.name = "BridgeTestCube"
    material = bpy.data.materials.new("BridgeTestMat")
    material.use_nodes = True
    cube.data.materials.append(material)
    before = len(cube.data.vertices)
    step("cube ready", "%s, %d verts, %d uv layer(s)" % (cube.name, before, len(cube.data.uv_layers)))

    out_path = bridge.send(bpy.context)
    job = applink.import_txt(exchange)
    step("sent", os.path.basename(out_path))
    step("import.txt written", os.path.isfile(job))

    deadline = time.time() + 120
    while time.time() < deadline and os.path.isfile(job):
        time.sleep(2)
    consumed = not os.path.isfile(job)
    step("3D-Coat consumed the job file", consumed)
    if not consumed:
        step("hint", "job file still there: 3D-Coat did not pick it up within 120s")

    signal = applink.export_txt_candidates(exchange)[0]
    if os.path.isfile(signal):
        os.remove(signal)
    step("waiting for the return", "up to %d s - press File > Bring object back in 3D-Coat" % timeout)
    deadline = time.time() + timeout
    while time.time() < deadline and not os.path.isfile(signal):
        time.sleep(2)

    if not os.path.isfile(signal):
        step("return received", "TIMEOUT - nothing came back")
    else:
        with open(signal, "r", encoding="utf-8", errors="replace") as handle:
            content = handle.read().strip()
        step("return received", content.replace(os.linesep, " "))
        messages = bridge.pull(bpy.context, force=True)
        step("pull messages", " | ".join(messages) or "(none)")
        after = len(cube.data.vertices)
        step("vertices before -> after", "%d -> %d" % (before, after))
        step("object name kept", cube.name)
        step("material kept", cube.material_slots[0].material.name if cube.material_slots else "none")
        step("link recorded", cube.get("coat_bridge_file", ""))
        step("scene mesh count", len([o for o in bpy.data.objects if o.type == "MESH"]))
        step("returned file", [os.path.basename(p) for p in applink.read_export_paths(signal)] if os.path.isfile(signal) else "consumed")

    if report_path:
        with open(report_path, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2)
    print("[live] done")
    sys.stdout.flush()


main()
