# SPDX-License-Identifier: GPL-3.0-or-later
"""Headless end-to-end test for CoatLink.

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
import time

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

    enabled = bpy.ops.preferences.addon_enable(module="coatlink")
    check("add-on enables", "FINISHED" in enabled, enabled)
    from coatlink import applink, bridge, transfer, watcher

    # The version lives in two places: the CHANGELOG heading (what package.sh names the
    # download after) and bl_info (what Blender shows).  Bumping one and not the other
    # ships a file whose name is a lie, so they are compared here.  The 3D-Coat half
    # carries no version of its own on purpose.
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    changelog = read(os.path.join(repo_root, "CHANGELOG.md"))
    heading = next((line.strip()[len("## v"):] for line in changelog.splitlines()
                    if line.strip().startswith("## v")), "")
    import coatlink
    stamped = ".".join(str(part) for part in coatlink.bl_info["version"])
    check("the CHANGELOG heading and the add-on version agree", heading == stamped,
          (heading, stamped))

    # Every download is named after CoatLink - the two setup doors, the project archive
    # (Blender-CoatLink-<version>.zip) and the add-on archive (CoatLink.zip) - because a
    # second name for the same thing is how a download link goes stale.  The folder
    # inside stays `coatlink`: it is the add-on's module name, which existing installs
    # and their preferences are keyed on.
    packaging = read(os.path.join(repo_root, "package.sh"))
    check("the add-on archive is named after CoatLink",
          "dist/CoatLink.zip" in packaging and "coatlink.zip" not in packaging,
          [line.strip() for line in packaging.splitlines() if ".zip" in line][:3])

    # Keep the suite hermetic: 3D-Coat's real roots are replaced by two temp ones.
    applink._candidate_exchange_folders = lambda: [os.path.normpath(EXCHANGE), os.path.normpath(OTHER_ROOT)]

    prefs = bpy.context.preferences.addons["coatlink"].preferences
    check("preferences reachable", prefs is not None)
    check("a send remeshes out of the box", prefs.remesh is True, prefs.remesh)
    check("with the voxel size left to the add-on", prefs.remesh_voxel == 0.0,
          prefs.remesh_voxel)
    check("and adaptivity off", prefs.remesh_adaptivity == 0.0, prefs.remesh_adaptivity)
    prefs.remesh = False        # its own section turns it back on when it gets there
    check("menu panel registered", hasattr(bpy.types, "COATBRIDGE_PT_menu"))
    check("menu lives in the top bar",
          bpy.types.COATBRIDGE_PT_menu.bl_space_type == "TOPBAR"
          and bpy.types.COATBRIDGE_PT_menu.bl_region_type == "HEADER")
    hook = getattr(bpy.types, "TOPBAR_HT_upper_bar", None)
    if hook is None:
        print("note  top bar hook not available in this session - skipped")
    else:
        from coatlink import ui as coat_ui
        check("button hooked into the top bar",
              coat_ui.HOOK_INSTALLED and callable(coat_ui.topbar_drawer))

        # the bar itself: the settings menu, then Send and Pull drawn to its right
        entries = []

        class _Row(object):
            def popover(self, **kwargs):
                entries.append(("popover", kwargs.get("panel"), kwargs.get("text"), kwargs.get("icon")))

            def operator(self, idname, **kwargs):
                entries.append(("operator", idname, kwargs.get("text"), kwargs.get("icon")))

            def prop(self, owner, name, **kwargs):
                entries.append(("prop", name, kwargs.get("text"), kwargs.get("toggle")))

        class _Layout(object):
            def row(self, align=False):
                return _Row()

        class _Self(object):
            layout = _Layout()

        def _context(alignment):
            return type("Ctx", (), {"region": type("Region", (), {"alignment": alignment})(),
                                    "preferences": bpy.context.preferences})()

        coat_ui.topbar_drawer(_Self(), _context("RIGHT"))
        check("the top bar draws the settings menu", entries[:1] ==
              [("popover", coat_ui.POPOVER_ID, "CoatLink", "COLLAPSEMENU")], entries)
        check("the bar holds nothing else: everything is inside that menu",
              len(entries) == 1, entries)
        check("the bar adds nothing on the left side", (coat_ui.topbar_drawer(_Self(), _context("LEFT")),
                                                        len(entries))[1] == 1, entries)

    # ---- the menu itself: scope, the two actions, then the settings ----
    drawn = []
    boxed_labels = []

    class _MenuLayout(object):
        def column(self, align=False):
            return _MenuColumn()

        def label(self, **kwargs):
            drawn.append(("label", kwargs.get("text")))

    class _Result(object):
        """What an operator call returns: the menu sets properties on it."""

    class _MenuColumn(object):
        def __init__(self, in_box=False):
            self.in_box = in_box

        def column(self, align=False):
            return _MenuColumn(self.in_box)

        def box(self):
            drawn.append(("box", None))
            return _MenuColumn(True)

        def prop(self, owner, name, **kwargs):
            drawn.append(("prop", name, kwargs.get("text")))

        def operator(self, idname, **kwargs):
            drawn.append(("operator", idname, kwargs.get("text")))
            return _Result()

        def label(self, **kwargs):
            drawn.append(("label", kwargs.get("text")))
            if self.in_box:
                boxed_labels.append(kwargs.get("text"))

        def row(self, align=False):
            return _MenuColumn(self.in_box)

        def separator(self):
            drawn.append(("separator", None))

    class _MenuSelf(object):
        layout = _MenuLayout()

    coat_ui.COATBRIDGE_PT_menu.draw(_MenuSelf(), bpy.context)
    check("the menu starts with the Send options heading",
          drawn[0] == ("label", "Send options"), drawn[:3])
    check("under it the scope, then the import mode",
          drawn[1] == ("prop", "scope", "Scope")
          and drawn[2] == ("prop", "mode", "Import as"), drawn[:4])
    check("then the two actions, named like the 3D-Coat panel's",
          ("operator", "coatbridge.send", "Send") in drawn
          and ("operator", "coatbridge.pull", "Pull") in drawn, drawn[:4])
    check("in that order: scope, import as, Send, Pull",
          drawn.index(("prop", "scope", "Scope"))
          < drawn.index(("prop", "mode", "Import as"))
          < drawn.index(("operator", "coatbridge.send", "Send"))
          < drawn.index(("operator", "coatbridge.pull", "Pull")), drawn[:5])

    folded = [item[1] for item in drawn if item[0] == "prop" and item[1] == "show_advanced"]
    check("nothing is hidden behind a fold-out", not folded, folded)
    labels = [item[1] for item in drawn if item[0] == "label"]
    for header in ("Send options", "Return", "Setup"):
        check("the menu has a '%s' heading" % header, header in labels, labels)
    check("the headings come before what they head",
          drawn.index(("label", "Send options")) < drawn.index(("prop", "scope", "Scope"))
          < drawn.index(("prop", "mode", "Import as"))
          < drawn.index(("label", "Return"))
          < drawn.index(("label", "Setup"))
          < drawn.index(("prop", "axis_mode", "Axis")), drawn[:8])
    # Sections must read alike: one divider before each heading, and none elsewhere.
    divider_positions = [index for index, item in enumerate(drawn) if item[0] == "separator"]
    heading_positions = [index for index, item in enumerate(drawn) if item[0] == "label"]
    check("there is one divider per section boundary",
          len(divider_positions) == 3, divider_positions)
    check("every divider introduces a section heading",
          all(drawn[index + 1][0] == "label" for index in divider_positions),
          [(drawn[i], drawn[i + 1]) for i in divider_positions])
    check("no divider sits in the middle of a section",
          all(drawn[index + 1] == ("label", None) or drawn[index + 1][0] == "label"
              for index in divider_positions), divider_positions)
    check("the four sections are all present in order",
          [drawn[index + 1][1] for index in divider_positions] == ["Return", "Setup", "Status"],
          [drawn[index + 1] for index in divider_positions])
    check("only the remesh sub-group is framed, so no section is boxed",
          [item for item in drawn if item[0] == "box"] == [("box", None)]
          and boxed_labels == [], boxed_labels)
    check("Status is a section like the others, with the readout under it",
          drawn.index(("label", "Status")) < drawn.index(("operator", "coatbridge.copy_details", "Copy details")),
          drawn[-6:])
    props = [item[1] for item in drawn if item[0] == "prop"]
    check("the remesh settings are framed as one group", ("box", None) in drawn,
          [item for item in drawn if item[0] == "box"])
    for name in ("axis_mode", "coat_scale", "match_scale", "apply_modifiers", "skip_dialogs"):
        check("the setting '%s' is drawn straight away" % name, name in props, props)
    ids = [item[1] for item in drawn if item[0] == "operator"]
    for name in ("coatbridge.detect", "coatbridge.open_folder", "coatbridge.launch",
                 "coatbridge.unlink"):
        check("the action '%s' is drawn straight away" % name, name in ids, ids)
    check("no sidebar panel left", not hasattr(bpy.types, "COATBRIDGE_PT_main"))
    check("operators registered",
          hasattr(bpy.types, "COATBRIDGE_OT_send") and hasattr(bpy.types, "COATBRIDGE_OT_pull"))
    check("a copy-details action is available without opening another window",
          hasattr(bpy.types, "COATBRIDGE_OT_copy_details"))
    formatter = getattr(coat_ui, "status_lines", None)
    check("status text has a bounded four-line readout",
          formatter is not None and len(formatter("Ready")) == 4)
    if formatter:
        lines = formatter("Long object name " * 80)
        check("long status lines fit the readout and mark truncation",
              len(lines) == 4 and all(len(line) <= 44 for line in lines)
              and lines[-1].endswith("..."), lines)
    class _FailedAction(object):
        def report(self, *args):
            pass
    saved_send = bridge.send
    saved_message = bridge.STATE["message"]
    def fail_send(context):
        raise RuntimeError("Missing exchange folder; press Detect")
    bridge.send = fail_send
    try:
        result = coat_ui.COATBRIDGE_OT_send.execute(_FailedAction(), bpy.context)
        check("send errors remain visible after the toast disappears",
              result == {"CANCELLED"} and "Missing exchange folder" in bridge.STATE["message"],
              bridge.STATE["message"])
    finally:
        bridge.send = saved_send
        bridge.STATE["message"] = saved_message
    class _PollProbe(object):
        messages = []
        @classmethod
        def poll_message_set(cls, message):
            cls.messages.append(message)
    edit_context = type("Ctx", (), {"mode": "EDIT_MESH"})()
    for operator_class in (coat_ui.COATBRIDGE_OT_send, coat_ui.COATBRIDGE_OT_pull):
        enabled = operator_class.poll.__func__(_PollProbe, edit_context)
        check("disabled %s explains how to enable it" % operator_class.bl_idname,
              not enabled and "Object Mode" in _PollProbe.messages[-1])
    class _ClipboardContext(object):
        preferences = bpy.context.preferences
        window_manager = type("WindowManager", (), {"clipboard": ""})()
    copy_context = _ClipboardContext()
    result = coat_ui.COATBRIDGE_OT_copy_details.execute(_FailedAction(), copy_context)
    check("copy details preserves full diagnostic paths without changing the real clipboard",
          result == {"FINISHED"}
          and "Job file:" in copy_context.window_manager.clipboard
          and "CoatLink" in copy_context.window_manager.clipboard)
    check("per-object link property registered", hasattr(bpy.types.Object, "coatlink_file"))
    check("timer registered", bpy.app.timers.is_registered(watcher.poll))
    check("defaults to a voxel sculpt object", prefs.mode == "vox")
    from coatlink import MODE_ITEMS
    check("and the voxel entry is the first one in the menu",
          MODE_ITEMS[0][0] == "vox", [item[0] for item in MODE_ITEMS][:3])
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
    check("import.txt: the default mode line third", lines[2] == "[vox]", lines)
    check("import.txt: skip flags", lines[3:5] == ["[SkipImport]", "[SkipExport]"], lines)
    check("import.txt: nothing else", len(lines) == 6, lines)

    # ---- the job carries the script that unparents the imported objects ----
    helper = applink.after_import_path(EXCHANGE)
    check("import.txt: the after-import script rides along",
          lines[5] == "[pythonfile %s]" % applink._slash(helper), lines)
    check("the helper is written next to the job file", os.path.isfile(helper), helper)
    check("the helper is the add-on's own file, with only the voxel flag flipped",
          read(helper) == read(applink.AFTER_IMPORT_SOURCE).replace(
              "VOXELIZE = False", "VOXELIZE = True", 1))
    check("a voxel import tells the helper to voxelize what arrives",
          "VOXELIZE = True" in read(helper))
    helper_text = read(helper)
    check("the helper names the model file it looks for",
          'MODEL_STEM = "bridge"' in helper_text, helper_text[:80])
    check("the helper holds no machine-specific path",
          "C:" not in helper_text and "Users" not in helper_text, helper_text[:200])
    check("the helper would compile inside 3D-Coat",
          bool(compile(helper_text, helper, "exec")))

    # ---- and the import.py 3D-Coat runs by itself -------------------------------
    # The job file names the helper with [pythonfile ...], but that line is read without
    # being executed on 2025.17.  What 3D-Coat does run is a file named import.py beside
    # the job, so the same work is handed over twice.  The unparenting cannot be checked
    # without a 3D-Coat tree, but this file has to exist, compile, name the helper
    # absolutely (its own __file__ is not guaranteed) and reach both notes when run.
    shim = applink.import_shim_path(EXCHANGE)
    check("send writes the import.py 3D-Coat runs itself", os.path.isfile(shim), shim)
    shim_text = read(shim)
    check("it compiles", bool(compile(shim_text, shim, "exec")))
    check("it names the helper and its own note by absolute path",
          repr(helper) in shim_text and repr(applink.import_shim_marker(EXCHANGE)) in shim_text,
          shim_text.splitlines()[:4])
    check("it says it ran before it runs the helper",
          shim_text.index("import.py ran") < shim_text.index("exec(compile("), shim_text[:120])

    shim_note = applink.import_shim_marker(EXCHANGE)
    helper_note = applink.after_import_marker(EXCHANGE)
    for stale in (shim_note, helper_note):
        if os.path.isfile(stale):
            os.remove(stale)
    os.environ["COATLINK_DOCS"] = tempfile.mkdtemp(prefix="shim_docs.")
    try:
        exec(compile(shim_text, shim, "exec"), {"__name__": "__main__"})
    finally:
        del os.environ["COATLINK_DOCS"]
    check("running it leaves its own note", os.path.isfile(shim_note), shim_note)
    check("with a date in it", read(shim_note)[:4].isdigit(), read(shim_note))
    check("and it reaches the helper, which notes itself too",
          os.path.isfile(helper_note), helper_note)
    # leave the exchange root as it was found: a fresh note here would look like evidence
    # to the detail-line checks further down
    for written in (shim_note, helper_note):
        if os.path.isfile(written):
            os.remove(written)
    check("import.txt: posix paths only", "\\" not in "".join(lines), lines)

    # a mode that is not voxel must leave the helper exactly as the add-on ships it
    prefs.mode = "uv"
    bridge.send(bpy.context)
    check("another mode leaves the voxel flag off",
          "VOXELIZE = True" not in read(helper))
    check("so the helper is byte for byte the add-on's file",
          read(helper) == read(applink.AFTER_IMPORT_SOURCE))
    prefs.mode = "vox"
    bridge.send(bpy.context)

    # the preference, not just its default, is what reaches the job file
    prefs.mode = "uv"
    bridge.send(bpy.context)
    check("choosing another mode changes the job file",
          read(job).splitlines()[2] == "[uv]", read(job).splitlines())
    prefs.mode = "vox"
    bridge.send(bpy.context)
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
    # ---- what a Send covers: the selection (default) or the whole scene ----
    check("the scope starts on the selection", prefs.scope == "selected", prefs.scope)
    check("the import mode is voxel out of the box", prefs.mode == "vox", prefs.mode)
    check("there is no fold flag left to get stuck in the old state",
          not hasattr(prefs, "show_advanced"))

    def exported_names():
        text = read(applink.model_path(EXCHANGE, "obj"))
        return sorted({line[2:].strip() for line in text.splitlines()
                       if line.startswith(("o ", "g "))})

    bpy.ops.mesh.primitive_cube_add(size=1)
    other = bpy.context.active_object
    other.name = "BridgeOther"
    cube.select_set(True)
    other.select_set(False)
    bpy.context.view_layer.objects.active = cube

    bridge.send(bpy.context)
    check("Send exports the selection", exported_names() == ["BridgeCube"], exported_names())
    check("and says which scope it used", "(selection)" in bridge.status(bpy.context),
          bridge.status(bpy.context))

    prefs.scope = "scene"
    bridge.send(bpy.context)
    check("choosing the whole scene sends every visible object",
          set(exported_names()) == {"BridgeCube", "BridgeOther"}, exported_names())
    check("and the status says so", "whole scene" in bridge.status(bpy.context),
          bridge.status(bpy.context))

    other.hide_set(True)
    bridge.send(bpy.context)
    check("a hidden object stays out of the whole-scene send",
          exported_names() == ["BridgeCube"], exported_names())
    other.hide_set(False)
    prefs.scope = "selected"
    bridge.send(bpy.context)
    check("switching it back sends the selection again",
          exported_names() == ["BridgeCube"], exported_names())
    bpy.data.objects.remove(other, do_unlink=True)

    check("send remembers the target object", bridge.STATE["target"]["object"] == "BridgeCube",
          bridge.STATE["target"])
    sent_diagonal = bridge.STATE["target"].get("diagonal") or 0.0
    check("send records the size for the scale check", abs(sent_diagonal - math.sqrt(3) * 2) < 0.02, sent_diagonal)
    check("UV set created for painting", len(cube.data.uv_layers) == 1)
    check("cube starts with 8 vertices", len(cube.data.vertices) == 8, len(cube.data.vertices))

    # ---- is the after-import step being run at all?  the log answers it ----
    real_log = bridge.applink.shared_log_path
    fake_log = os.path.join(os.path.dirname(out_path), "fake-shared.log")
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(fake_log, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("%s | 3dcoat | after-import ran: 2 moved, 1 to voxels, 0 already "
                     "voxel, 0 failed\n" % stamp)
    bridge.applink.shared_log_path = lambda: fake_log
    bridge.STATE["last_send"] = time.time() - 30
    check("a run after our send is reported as such", bridge.after_import_seen() is True,
          bridge.after_import_seen())
    bridge.STATE["last_send"] = time.time() + 30      # send after the helper's line
    check("a line from before our send does not count",
          bridge.after_import_seen() is False, bridge.after_import_seen())
    with open(fake_log, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("%s | blender | sent something\n" % stamp)
    check("a log with no such line says it was not run",
          bridge.after_import_seen() is False, bridge.after_import_seen())
    bridge.STATE["last_send"] = 0.0
    check("nothing sent yet means nothing to say", bridge.after_import_seen() is None,
          bridge.after_import_seen())
    bridge.STATE["last_send"] = time.time() - 1

    # A fresh stamp, taken here: the log line has to be dated after that send, and
    # both only carry whole seconds - reusing the stamp from the block above made
    # this check depend on how long those lines happened to take (it flaked by a
    # second on a slower run).
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(fake_log, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("%s | 3dcoat | after-import ran: 0 moved, 0 to voxels, 0 already "
                     "voxel, 0 failed\n" % stamp)
    details = bridge.detail_lines(bpy.context)
    check("the menu's detail lines say the helper ran",
          any("ran it" in line for line in details), details)
    with open(fake_log, "w", encoding="utf-8") as handle:
        handle.write("%s | 3dcoat | after-import ran: old record\n" %
                     time.strftime("%H:%M:%S"))
    check("undated logs cannot prove which day the helper ran",
          bridge.after_import_seen() is not True)
    details = bridge.detail_lines(bpy.context)
    check("missing confirmation does not claim the helper never ran",
          any("not confirmed" in line for line in details), details)
    with open(fake_log, "w", encoding="utf-8") as handle:
        handle.write("2000-01-01 23:59:59 | 3dcoat | after-import ran: old record\n")
    check("a prior day's record is not a confirmation",
          bridge.after_import_seen() is False)
    bridge.applink.shared_log_path = real_log
    os.remove(fake_log)

    # The helper's own marker counts too: it is written before the helper touches
    # anything, so it survives a machine where the shared log cannot be reached from
    # inside 3D-Coat - and "never ran" vs "ran but could not write" used to look alike.
    marker = applink.after_import_marker(EXCHANGE)
    with open(marker, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("2026-01-01 00:00:00.000000 | the after-import helper started\n")
    bridge.applink.shared_log_path = lambda: os.path.join(os.path.dirname(out_path), "no-such.log")
    bridge.STATE["last_send"] = time.time() - 30
    check("the helper's own marker counts as evidence it ran",
          bridge.after_import_seen([EXCHANGE]) is True, bridge.after_import_seen([EXCHANGE]))
    bridge.STATE["last_send"] = time.time() + 30
    check("a marker older than our send does not count",
          bridge.after_import_seen([EXCHANGE]) is not True, bridge.after_import_seen([EXCHANGE]))
    bridge.applink.shared_log_path = real_log
    os.remove(marker)

    # A line the 3D-Coat panel wrote carries the same tag but a short clock stamp, and
    # it is not execution evidence: only the helper's own full-timestamp record is.
    # Without this the panel would claim "3D-Coat ran it" for a step that never ran.
    with open(fake_log, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("08:05:01 | 3dcoat | after-import ran: 0 moved, 0 to voxels\n")
    bridge.applink.shared_log_path = lambda: fake_log
    bridge.STATE["last_send"] = time.time() - 30
    check("a panel line is not mistaken for the helper's record",
          bridge.after_import_seen() is not True, bridge.after_import_seen())
    bridge.applink.shared_log_path = real_log
    os.remove(fake_log)

    # A user modifier with our preferred name is still owned by the user.
    owned = cube.modifiers.new(bridge.REMESH_MODIFIER, "BEVEL")
    owned_pointer = owned.as_pointer()
    bridge.add_remesh([cube], 0.1)
    bridge.remove_remesh([cube])
    check("remesh cleanup preserves a same-named user modifier",
          any(m.as_pointer() == owned_pointer for m in cube.modifiers))
    check("remesh cleanup removes the actual temporary modifier",
          not any(m.type == "REMESH" for m in cube.modifiers))
    for m in list(cube.modifiers):
        cube.modifiers.remove(m)

    # ---- remesh on send: a pass over what is exported, never over the scene ----
    def vertex_count(path):
        text = open(path, encoding="utf-8", errors="replace").read()
        return len([line for line in text.splitlines() if line.startswith("v ")])

    def modifier_names(obj):
        return [item.name for item in obj.modifiers]

    user_subsurf = cube.modifiers.new("User subdivision", "SUBSURF")
    user_subsurf.levels = 1
    transfer.export_model(out_path, "obj", [cube], apply_modifiers=False)
    check("disabled modifiers export the original eight vertices",
          vertex_count(out_path) == 8, vertex_count(out_path))
    transfer.export_model(out_path, "obj", [cube], apply_modifiers=True)
    check("enabled modifiers export the evaluated geometry",
          vertex_count(out_path) > 8, vertex_count(out_path))
    cube.modifiers.remove(user_subsurf)

    check("no remesh modifier is left behind from earlier sends",
          "CoatLink Remesh" not in modifier_names(cube), modifier_names(cube))
    prefs.remesh = True
    bridge.send(bpy.context)
    remeshed_vertices = vertex_count(out_path)
    check("a remeshed export really is remeshed, not the same box",
          remeshed_vertices > 100, remeshed_vertices)
    check("the mesh in the scene is not touched (a cube is still a cube)",
          len(cube.data.vertices) == 8, len(cube.data.vertices))
    check("and the temporary modifier is taken off again",
          "CoatLink Remesh" not in modifier_names(cube), modifier_names(cube))
    check("the status says it was remeshed", "remeshed" in bridge.status(bpy.context),
          bridge.status(bpy.context))

    # Remesh does not override the user's disabled Modifiers option.
    saved_apply = prefs.apply_modifiers
    prefs.apply_modifiers = False
    prefs.remesh_voxel = 0.1
    bridge.send(bpy.context)
    remesh_only = vertex_count(out_path)
    user_subsurf = cube.modifiers.new("Disabled for export", "SUBSURF")
    user_subsurf.levels = 2
    bridge.send(bpy.context)
    check("remesh respects the disabled user-modifier setting",
          vertex_count(out_path) == remesh_only,
          (vertex_count(out_path), remesh_only))
    check("user modifier visibility is restored after export",
          user_subsurf.show_viewport and user_subsurf.show_render)
    real_export = transfer.export_model
    def failed_export(*args, **kwargs):
        raise RuntimeError("injected export failure")
    transfer.export_model = failed_export
    try:
        try:
            bridge.send(bpy.context)
        except RuntimeError as error:
            check("export failure is propagated", "injected export failure" in str(error))
        else:
            check("export failure is propagated", False)
    finally:
        transfer.export_model = real_export
    check("failed export restores user modifiers and removes temporary remesh",
          user_subsurf.show_viewport and user_subsurf.show_render
          and not any(m.type == "REMESH" for m in cube.modifiers))
    cube.modifiers.remove(user_subsurf)
    prefs.apply_modifiers = saved_apply
    prefs.remesh_voxel = 0.0

    # a modifier the user put there is theirs: it survives, and only ours is removed
    mine = cube.modifiers.new("Mine", "SUBSURF")
    bridge.send(bpy.context)
    check("a modifier the user made is still there", "Mine" in modifier_names(cube),
          modifier_names(cube))
    check("and ours is gone", "CoatLink Remesh" not in modifier_names(cube),
          modifier_names(cube))
    cube.modifiers.remove(mine)

    # what goes on the object is what the panel was set to
    probe = bpy.data.objects.new("RemeshProbe", bpy.data.meshes.new("RemeshProbeMesh"))
    bpy.context.scene.collection.objects.link(probe)
    added = bridge.add_remesh([probe], 0.02, 0.7)
    modifier = probe.modifiers[0]
    check("the remesh modifier gets the voxel size and the adaptivity",
          added == 1 and abs(modifier.voxel_size - 0.02) < 1e-6
          and abs(modifier.adaptivity - 0.7) < 1e-6,
          (modifier.voxel_size, modifier.adaptivity))
    bridge.add_remesh([probe], 0.02, 4.0)
    check("an out-of-range adaptivity is clamped, not passed on",
          probe.modifiers["CoatLink Remesh"].adaptivity <= 1.0,
          probe.modifiers["CoatLink Remesh"].adaptivity)
    bridge.remove_remesh([probe])
    bpy.data.objects.remove(probe)

    # and it reaches the export: adaptivity never adds vertices, it removes them
    prefs.remesh_voxel = 0.02
    bridge.send(bpy.context)
    plain_remesh = vertex_count(out_path)
    prefs.remesh_adaptivity = 0.5
    bridge.send(bpy.context)
    adaptive = vertex_count(out_path)
    check("adaptivity does not add work to the remesh", adaptive <= plain_remesh,
          (adaptive, plain_remesh))
    prefs.remesh_adaptivity = 0.0

    # the voxel size is honoured: coarse is coarser than fine
    prefs.remesh_voxel = 0.5
    bridge.send(bpy.context)
    coarse = vertex_count(out_path)
    prefs.remesh_voxel = 0.02
    bridge.send(bpy.context)
    fine = vertex_count(out_path)
    check("a coarse voxel size exports fewer vertices than a fine one", coarse < fine,
          (coarse, fine))
    prefs.remesh_voxel = 0.0

    prefs.remesh = False
    bridge.send(bpy.context)
    check("with remesh off the export is the plain mesh", vertex_count(out_path) == 8,
          vertex_count(out_path))
    # left off on purpose: the axis and scale sections below compare exact vertex
    # coordinates, and a remeshed mesh has slightly different ones

    # ---- simulate 3D-Coat returning a denser model into the primary root ----
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=1.6)
    returned = bpy.context.active_object
    back_path = applink.model_path(EXCHANGE, "obj", name="bridge_back")
    # 3D-Coat returns the model at the size it received it, so send it back at the
    # size Blender sent: nothing needs correcting then
    returned_scale = sent_diagonal / max(bridge._diagonal(returned), 1e-9)
    transfer.export_model(back_path, "obj", [returned], apply_modifiers=False,
                          overrides={"global_scale": returned_scale})
    expected = len(returned.data.vertices)
    bpy.data.objects.remove(returned, do_unlink=True)
    signal = applink.signal_files([EXCHANGE])[0]
    # The add-on reads 3D-Coat's state file out of "Documents"; point that at a
    # throwaway home from here on, so these checks never pick up the real
    # 3D-Coat settings (or write to its log) on this machine.
    coat_home = tempfile.mkdtemp(prefix="coat_state.")
    os.makedirs(os.path.join(coat_home, "3DCoat"), exist_ok=True)
    applink._documents_bases = lambda: [coat_home]

    def write_coat_state(info):
        write(os.path.join(coat_home, "3DCoat", "CoatBridge.json"), json.dumps({"coat": info}))

    back_path_fbx = applink.model_path(EXCHANGE, "fbx", name="bridge_back")

    # The add-on reads 3D-Coat's state file out of "Documents"; point that at a
    # throwaway home from here on, so these checks never pick up the real
    # 3D-Coat settings (or its log) on this machine.
    coat_home = tempfile.mkdtemp(prefix="coat_state.")
    os.makedirs(os.path.join(coat_home, "3DCoat"), exist_ok=True)
    applink._documents_bases = lambda: [coat_home]

    def write_coat_state(info):
        write(os.path.join(coat_home, "3DCoat", "CoatBridge.json"), json.dumps({"coat": info}))
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
    check("link recorded on the object", cube.get("coatlink_file") == back_path, cube.get("coatlink_file"))
    check("no stray imported object", mesh_count() == 1, mesh_count())
    check("returned file kept for the next round trip", os.path.isfile(back_path))
    check("second pull has nothing to do", bridge.pull(bpy.context) == [])
    check("a return of the same size needs no correction", "scale x" not in " ".join(messages), messages)
    check("and the model is exactly the size it was sent at",
          abs(bridge._diagonal(cube) - sent_diagonal) < 0.02,
          (bridge._diagonal(cube), sent_diagonal))

    # ---- settled(): does the file stop growing? --------------------------------
    # 3D-Coat's AppLink export writes the model and the signal itself, and the signal can
    # land while the model is still being written.  Importing that found no objects (or
    # half a mesh) and used to fill the log with one traceback per watcher tick.
    stable = os.path.join(os.path.dirname(back_path), "stable.obj")
    write(stable, "o cube\nv 0 0 0\n")
    check("a file nobody is writing has settled", bridge.settled(stable) is True, stable)
    growing = os.path.join(os.path.dirname(back_path), "growing.obj")
    write(growing, "o cube\n")
    real_sleep = bridge.time.sleep

    def still_arriving(_seconds):
        with open(growing, "a", encoding="utf-8", newline="\n") as handle:
            handle.write("v 1 0 0\n")

    bridge.time.sleep = still_arriving
    try:
        check("a file that keeps growing has not settled", bridge.settled(growing) is False, growing)
    finally:
        bridge.time.sleep = real_sleep
    check("a file that is not there has not settled",
          bridge.settled(growing + ".missing") is False)

    breaking = os.path.join(os.path.dirname(back_path), "still-arriving.obj")
    write(breaking, "")                        # nothing to import yet
    write(signal, breaking + "\n")
    fake_log = os.path.join(os.path.dirname(back_path), "arriving.log")
    real_settled = bridge.settled
    bridge.applink.shared_log_path = lambda: fake_log
    bridge.settled = lambda path: False        # it never stops growing
    try:
        first = bridge.pull(bpy.context, force=True)
        second = bridge.pull(bpy.context, force=True)
    finally:
        bridge.settled = real_settled
        bridge.applink.shared_log_path = real_log
    check("a return that is still being written says so",
          any("still being written" in message for message in first), first)
    check("and the next tick retries it rather than dropping it",
          any("still being written" in message for message in second), second)
    with open(fake_log, "r", encoding="utf-8") as handle:
        noise = handle.read()
    check("the traceback goes to the log once per file version, not once per tick",
          noise.count("import traceback:") == 1, noise.count("import traceback:"))
    for leftover in (stable, growing, breaking, fake_log, signal):
        if os.path.isfile(leftover):
            os.remove(leftover)

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
    check("these compare coordinates exactly, so remesh stays off here",
          prefs.remesh is False, prefs.remesh)
    def obj_points(path):
        points = set()
        for line in read(path).splitlines():
            if line.startswith("v "):
                parts = line.split()
                points.add(tuple(round(float(value), 4) for value in parts[1:4]))
        return points

    applink_bases = applink._documents_bases
    prefs.coat_scale = 0.0
    prefs.axis_mode = "auto"

    check("without 3D-Coat's state the bridge stays neutral",
          bridge.transfer_scale(bpy.context)[0] == 1.0 and bridge.axis_swap(bpy.context) is None,
          (bridge.transfer_scale(bpy.context), bridge.axis_swap(bpy.context)))

    write_coat_state({"scene_scale": 100.0, "scene_units": "m", "swap_yz": True})
    scale, origin = bridge.transfer_scale(bpy.context)
    check("3D-Coat's reported numbers are used", scale == 100.0 and "3D-Coat" in origin, (scale, origin))
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
          "units=" in read(applink.shared_log_path()), read(applink.shared_log_path()).splitlines()[-1:])



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

    # the units are what matters: centimetres need x100, millimetres x1000
    for units, expected in (("CENTIMETERS", 100.0), ("MILLIMETERS", 1000.0), ("METERS", 1.0)):
        write_coat_state({"scene_scale": 1.0, "scene_units": units, "swap_yz": False})
        check("3D-Coat units=%s means x%s" % (units, expected),
              abs(bridge.transfer_scale(bpy.context)[0] - expected) < 0.01,
              bridge.transfer_scale(bpy.context))
    write_coat_state({"scene_scale": 1.0, "scene_units": "FURLOGS", "swap_yz": False})
    check("an unknown unit name is not guessed at",
          bridge.transfer_scale(bpy.context)[0] == 1.0
          and "has not reported" in bridge.transfer_scale(bpy.context)[1],
          bridge.transfer_scale(bpy.context))

    # a model that comes home in 3D-Coat's units is converted back, and a size
    # that differs because the model itself changed is left alone
    write_coat_state({"scene_scale": 1.0, "scene_units": "CENTIMETERS", "swap_yz": False})
    cube_scale = bridge.transfer_scale(bpy.context)[0]
    transfer.export_model(back_path, "obj", [cube], apply_modifiers=False,
                          overrides={"global_scale": cube_scale})
    before_diagonal = bridge._diagonal(cube)
    write(signal, back_path + "\n")
    messages = bridge.pull(bpy.context, force=True)
    check("a model written in 3D-Coat's units comes home the right size",
          abs(bridge._diagonal(cube) - before_diagonal) < 0.02
          and "scale x" not in " ".join(messages),
          (bridge._diagonal(cube), before_diagonal, messages))

    transfer.export_model(back_path, "obj", [cube], apply_modifiers=False,
                          overrides={"global_scale": cube_scale * 1.5})
    write(signal, back_path + "\n")
    messages = bridge.pull(bpy.context, force=True)
    check("a size difference that is not a unit factor is left alone",
          any("left alone" in message for message in messages), messages)

    applink._documents_bases = applink_bases

    # ---- and the whole round trip is written to the shared log ----
    log_path = applink.shared_log_path()
    check("the shared log exists", os.path.isfile(log_path), log_path)
    if os.path.isfile(log_path):
        log_text = read(log_path)
        check("the log records the send size", "sent BridgeCube" in log_text, log_text[-200:])
        check("the log records what happened to the size",
              "scale matched" in log_text or "scale:" in log_text, log_text[-200:])

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

        # ---- self-describing formats keep their own units and axes ----
    recorded = []
    real_import = transfer.import_model

    def recording_import(path, fmt, overrides=None):
        recorded.append((fmt, dict(overrides or {})))
        return real_import(path, fmt, overrides)

    transfer.import_model = recording_import
    write_coat_state({"scene_scale": 1.0, "scene_units": "CENTIMETERS", "swap_yz": True})
    transfer.export_model(back_path, "obj", [cube], apply_modifiers=False)
    write(signal, back_path + "\n")
    bridge.pull(bpy.context, force=True)
    check("an OBJ return is converted out of 3D-Coat's units",
          abs(recorded[-1][1].get("global_scale", 1.0) - 0.01) < 1e-9, recorded[-1])
    check("and its axes are matched", recorded[-1][1].get("up_axis") == "Z", recorded[-1])

    fbx_path = applink.model_path(EXCHANGE, "fbx", name="bridge_back")
    write(fbx_path, "not a real fbx")
    write(signal, fbx_path + "\n")
    bridge.pull(bpy.context, force=True)
    check("an FBX return keeps its own units (no second conversion)",
          "global_scale" not in recorded[-1][1], recorded[-1])
    check("and its own axes",
          "up_axis" not in recorded[-1][1] and "forward_axis" not in recorded[-1][1], recorded[-1])
    transfer.import_model = real_import
    os.remove(fbx_path)
    write_coat_state({"scene_scale": 1.0, "scene_units": "CENTIMETERS", "swap_yz": False})

# ---- a return 3D-Coat wrote into its own AppLink pool is still this trip's ----
    pool = os.path.join(OTHER_ROOT, "..", "3DC2Blender", "ApplinkObjects")
    os.makedirs(pool, exist_ok=True)
    pool_model = os.path.join(pool, "3DC015.fbx")
    shutil.copy(back_path, pool_model)
    pool_signal = os.path.join(OTHER_ROOT, "export.txt")
    write(pool_signal, pool_model + "\n")
    messages = bridge.pull(bpy.context, force=True)
    check("a return in 3D-Coat's own AppLink pool is taken",
          any("own AppLink folder" in message for message in messages), messages)
    check("its signal is left for the official AppLink", os.path.isfile(pool_signal), messages)
    os.remove(pool_signal)

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

    # ---- one trip, one model: 3D-Coat leaves a signal in BOTH roots ----
    # (and the returned file matches no object, which is when a double import
    #  shows up as two copies in the scene rather than one replaced mesh)
    imported_paths = []
    real_import = transfer.import_model

    def counting_import(path, fmt, overrides=None):
        imported_paths.append(path)
        return real_import(path, fmt, overrides)

    transfer.import_model = counting_import
    lone_path = applink.model_path(EXCHANGE, "obj", name="lone_return")
    transfer.export_model(lone_path, "obj", [cube], apply_modifiers=False)
    both = [os.path.join(EXCHANGE, "BlenderBridge", "export.txt"),
            os.path.join(OTHER_ROOT, "BlenderBridge", "export.txt")]
    for target in both:
        write(target, lone_path + "\n")
    before = mesh_count()
    messages = bridge.pull(bpy.context, force=True)
    check("a signal in both roots imports the model exactly once", len(imported_paths) == 1,
          imported_paths)
    check("so no extra object is left behind", mesh_count() <= before, (before, mesh_count()))
    check("both signals are consumed", not any(os.path.isfile(target) for target in both),
          [os.path.isfile(target) for target in both])
    check("and it is reported once", len([m for m in messages if "Pulled" in m]) <= 1, messages)
    transfer.import_model = real_import
    for obj in list(bpy.data.objects):          # drop what that test added
        if obj.type == "MESH" and obj.name != cube.name:
            bpy.data.objects.remove(obj, do_unlink=True)
    os.remove(lone_path)

    # ---- the TARGET going stale mid-import (that is the real one: removing the
    #      temp object pushes an undo step, and Blender then invalidates every
    #      Python reference - with "import without materials" on, the target was
    #      used again straight after and the whole pull failed) ----
    prefs.strip_materials = True
    real_replace = bridge._replace_mesh

    def stale_target_replace(target, source):
        name = target.name
        real_replace(target, source)
        data = target.data
        bpy.data.objects.remove(target, do_unlink=True)      # undo push: refs die
        replacement = bpy.data.objects.new(name, data)
        bpy.context.scene.collection.objects.link(replacement)

    bridge._replace_mesh = stale_target_replace
    transfer.export_model(back_path, "obj", [cube], apply_modifiers=False)
    write(signal, back_path + "\n")
    messages = bridge.pull(bpy.context, force=True)
    check("a target that goes stale mid-import is survived",
          any("Pulled" in message for message in messages), messages)
    pulled = [message for message in messages if "Pulled" in message]
    pulled_name = pulled[0].split()[1] if pulled else ""
    cube = bpy.data.objects.get(pulled_name)     # our own reference died with it
    check("the geometry arrived on the re-created object",
          cube is not None and len(cube.data.vertices) > 0,
          cube.name if cube else "gone")
    bridge._replace_mesh = real_replace
    prefs.strip_materials = False

    # ---- a reference that goes stale during the import must not break the pull ----
    # (Blender invalidates Python references when an operator pushes an undo step,
    #  which is exactly what "StructRNA of type Object has been removed" means)
    real_import = transfer.import_model

    def stale_import(path, fmt, overrides=None):
        objects, dropped = real_import(path, fmt, overrides)
        for obj in objects:
            name, data = obj.name, obj.data
            bpy.data.objects.remove(obj, do_unlink=True)          # dead reference
            replacement = bpy.data.objects.new(name, data)         # same name, new struct
            bpy.context.scene.collection.objects.link(replacement)
        return objects, dropped        # ...and hand the dead ones back

    transfer.import_model = stale_import
    write(signal, back_path + "\n")
    messages = bridge.pull(bpy.context, force=True)
    check("a stale reference during the import is survived",
          any("Pulled" in message for message in messages), messages)
    check("and the pull is recorded in the shared log",
          "pull: Pulled" in read(applink.shared_log_path()),
          read(applink.shared_log_path()).splitlines()[-2:])
    transfer.import_model = real_import

    # ---- the watcher's timer and a click must not pull at the same time ----
    passes = []

    skipped_messages = []

    def reentrant_import(path, fmt, overrides=None):
        passes.append(path)
        # the watcher firing mid-flight: this one must come back empty-handed
        skipped_messages.extend(bridge.pull(bpy.context, force=True))
        return real_import(path, fmt, overrides)

    transfer.import_model = reentrant_import
    write(signal, back_path + "\n")
    messages = bridge.pull(bpy.context, force=True)
    check("a pull that arrives while one is running is skipped", len(passes) == 1, passes)
    check("and the skipped one says so",
          any("already running" in message for message in skipped_messages), skipped_messages)
    check("and the first one still finishes", any("Pulled" in message for message in messages), messages)
    transfer.import_model = real_import

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
    cube["coatlink_file"] = back_path

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

    # ---- links written by an earlier build keep working ----
    # Until the module was renamed to `coatlink`, these keys were `coat_bridge_*`.  A
    # scene saved back then must still look linked: otherwise the next returned model is
    # imported as a *new* object instead of replacing the one it came from.  Reads accept
    # both keys, writes use the new ones, unlink clears both.
    legacy = bpy.data.objects.new("legacy", None)
    bpy.context.scene.collection.objects.link(legacy)
    legacy["coat_bridge_file"] = back_path
    legacy["coat_bridge_source_name"] = "Cube"
    check("a link written by an earlier build is still readable",
          bridge.link_path(legacy) == back_path, bridge.link_path(legacy))
    check("and so is its export alias",
          bridge.source_alias(legacy) == "Cube", bridge.source_alias(legacy))
    check("the details count it as linked",
          any("legacy" in line for line in bridge.detail_lines(bpy.context)),
          bridge.detail_lines(bpy.context))
    bridge.adopt_link(legacy)
    check("touching it moves the link onto the new keys",
          legacy.get("coatlink_file") == back_path
          and legacy.get("coatlink_source_name") == "Cube", dict(legacy.items()))
    check("unlink clears an old-build link too", _unlink_clears(legacy))
    bpy.data.objects.remove(legacy)


def _unlink_clears(cube):
    from coatlink import bridge  # main()'s import is local to main()
    cube["coatlink_file"] = "something"
    cube["coat_bridge_file"] = "something from the older build"
    for obj in bpy.context.selected_objects:
        obj.select_set(False)
    cube.select_set(True)
    bpy.context.view_layer.objects.active = cube
    bpy.ops.coatbridge.unlink()
    left = [key for key in (bridge.LINK_KEY, bridge.LEGACY_LINK_KEY,
                            bridge.SOURCE_KEY, bridge.LEGACY_SOURCE_KEY)
            if key in cube.keys()]
    return not bridge.link_path(cube) and not left


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
