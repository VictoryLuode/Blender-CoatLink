# SPDX-License-Identifier: GPL-3.0-or-later
"""Live round trip against a real, running 3D-Coat.

    tests/live_roundtrip.sh [--timeout SECONDS]

Sends a cube named BridgeTestCube into the real exchange folder, waits for
3D-Coat to consume the job file, then waits for the return signal (you press
File > Export To > BlenderBridge in 3D-Coat - NOT the official "Bring object
back", which writes a signal for the official add-on's own folder) and pulls
it, reporting whether the object was updated in place.

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
    # the mode under question, and no remesh: a remeshed export would change the
    # vertex counts and hide whether the import itself was right
    prefs.mode = "vox"
    prefs.remesh = False
    prefs.auto_pull = False  # this script drives the pulls itself
    prefs.skip_dialogs = True
    prefs.apply_modifiers = False

    import coat_bridge as addon
    step("add-on version", ".".join(str(part) for part in addon.bl_info["version"]))
    step("coat running at start", applink.is_coat_running())

    # drop stale signals this bridge owns, so the wait below only sees the new one
    roots = applink.exchange_roots(exchange)
    for stale in applink.signal_files(roots):
        if not os.path.isfile(stale):
            continue
        if any(bridge._is_ours(path, roots) for path in applink.read_export_paths(stale)):
            os.remove(stale)
            step("removed stale signal", stale)

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
    sent_at = time.time()       # a signal older than this is a leftover, not a return
    job = applink.import_txt(exchange)
    step("sent", os.path.basename(out_path))
    step("import.txt written", os.path.isfile(job))
    # the exact job file 3D-Coat is about to read: without it a failed trip cannot be
    # diagnosed afterwards
    if os.path.isfile(job):
        with open(job, "r", encoding="utf-8", errors="replace") as handle:
            step("import.txt content", " ; ".join(handle.read().split()))

    deadline = time.time() + 120
    while time.time() < deadline and os.path.isfile(job):
        time.sleep(2)
    consumed = not os.path.isfile(job)
    step("3D-Coat consumed the job file", consumed)
    if not consumed:
        step("hint", "job file still there: 3D-Coat did not pick it up within 120s")

    step("waiting for the return", "up to %d s - in 3D-Coat press File > Export To > BlenderBridge" % timeout)
    step("exchange roots", " | ".join(roots))
    deadline = time.time() + timeout
    signal = ""
    while time.time() < deadline:
        for candidate in applink.signal_files(roots):
            # Only a signal written after our send counts.  The exchange roots
            # keep stale ones - the official add-on's export.txt outlives the
            # add-on itself - and accepting one of those reports a return that
            # never happened.
            if os.path.isfile(candidate) and os.path.getmtime(candidate) >= sent_at:
                signal = candidate
                break
        if signal:
            break
        time.sleep(2)

    if not signal:
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
