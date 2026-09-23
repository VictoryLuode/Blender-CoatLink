# SPDX-License-Identifier: GPL-3.0-or-later
"""Live round trip against a real, running 3D-Coat.

    tests/live_roundtrip.sh [--timeout SECONDS]

Sends a cube named BridgeTestCube into the real exchange folder, waits for
3D-Coat to consume the job file, then waits for the return signal (you press
File > Export To > CoatLink in 3D-Coat - NOT the official "Bring object
back", which writes a signal for the official add-on's own folder) and pulls
it, reporting whether the object was updated in place.

With --origin the cube starts away from the origin and "Send to origin" is on:
the report then also says where the model sits in the file that went out and
where the object is after the pull, which is what a round trip must not change.

Nothing is written outside the exchange folder.
"""

import json
import os
import sys
import time

import bpy
from mathutils import Vector

#: where the --origin run starts the cube: off the origin on all three axes, so a shift
#: that did nothing and a shift applied twice both show up in the report
HOME = (3.0, 2.0, 1.0)


def _file_centre(path):
    """The model's bounding-box centre in coordinates of the file the bridge wrote."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            points = [[float(part) for part in line.split()[1:4]]
                      for line in handle.read().splitlines() if line.startswith("v ")]
    except OSError:
        return None
    if not points:
        return None
    return [round((min(point[axis] for point in points)
                   + max(point[axis] for point in points)) / 2.0, 4) for axis in range(3)]


def _world_centre(obj):
    """Where the object's geometry really is, in scene coordinates."""
    bpy.context.view_layer.update()
    corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    return [round((min(corner[axis] for corner in corners)
                   + max(corner[axis] for corner in corners)) / 2.0, 4) for axis in range(3)]


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
    origin = "--origin" in sys.argv      # also exercise "Send to origin"
    report = {"exchange": exchange, "origin": origin, "steps": []}

    def step(name, value):
        report["steps"].append({"step": name, "value": str(value)})
        print("[live] %-34s %s" % (name + ":", value))
        sys.stdout.flush()

    bpy.ops.preferences.addon_enable(module="coatlink")
    from coatlink import applink, bridge

    prefs = bpy.context.preferences.addons["coatlink"].preferences
    prefs.exchange_folder = exchange
    # the mode under question, and no remesh: a remeshed export would change the
    # vertex counts and hide whether the import itself was right
    prefs.mode = "vox"
    prefs.remesh = False
    prefs.auto_pull = False  # this script drives the pulls itself
    prefs.skip_dialogs = True
    prefs.apply_modifiers = False
    prefs.send_origin = origin

    import coatlink as addon
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
    if origin:
        cube.location = HOME
        bpy.context.view_layer.update()
    material = bpy.data.materials.new("BridgeTestMat")
    material.use_nodes = True
    cube.data.materials.append(material)
    before = len(cube.data.vertices)
    step("cube ready", "%s, %d verts, %d uv layer(s)" % (cube.name, before, len(cube.data.uv_layers)))
    step("send to origin", prefs.send_origin)
    step("where the cube is", _world_centre(cube))

    out_path = bridge.send(bpy.context)
    sent_at = time.time()       # a signal older than this is a leftover, not a return
    job = applink.import_txt(exchange)
    step("sent", os.path.basename(out_path))
    step("model centre in the sent file", _file_centre(out_path))
    step("where the cube is after the send", _world_centre(cube))
    if origin:
        centre = _file_centre(out_path)
        step("and it is on the file's origin",
             bool(centre) and all(abs(part) < 1e-3 for part in centre))
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

    step("waiting for the return", "up to %d s - in 3D-Coat press File > Export To > CoatLink" % timeout)
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
        step("where the cube's geometry is after the pull", _world_centre(cube))
        if origin:
            landed = _world_centre(cube)
            step("came home", all(abs(landed[axis] - HOME[axis]) < 1e-3 for axis in range(3)))
        step("object name kept", cube.name)
        step("material kept", cube.material_slots[0].material.name if cube.material_slots else "none")
        step("link recorded", cube.get("coatlink_file", ""))
        step("scene mesh count", len([o for o in bpy.data.objects if o.type == "MESH"]))
        step("returned file", [os.path.basename(p) for p in applink.read_export_paths(signal)] if os.path.isfile(signal) else "consumed")

    if report_path:
        with open(report_path, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2)
    print("[live] done")
    sys.stdout.flush()


main()
