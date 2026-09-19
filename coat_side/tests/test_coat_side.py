# SPDX-License-Identifier: GPL-3.0-or-later
"""Logic tests for the 3D-Coat side, using a fake coat module.

The panel is imported the way 3D-Coat imports it (the script runs on import),
but `coat` / `CMD` are stand-ins that record calls, and the home directory
points at a throwaway tree.  So the exchange layout, the signal files, the
queue handling and the panel layout are all exercised without 3D-Coat.

    python coat_side/tests/test_coat_side.py
"""

import importlib.util
import json
import os
import shutil
import sys
import tempfile
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fake_coat import FakeCoat, UNSET, build_environment  # shared fake 3D-Coat API

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, "..", "CoatBridgeLib.py")
PANEL_ENTRY = os.path.join(HERE, "..", "CoatBridge_Setup.py")

RESULTS = []


def check(name, condition, detail=""):
    RESULTS.append((name, bool(condition), detail))
    print("%-4s %s%s" % ("PASS" if condition else "FAIL", name,
                         "" if condition else "   <- %s" % (detail,)))


def import_script():
    spec = importlib.util.spec_from_file_location("coat_bridge_lib", LIB)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    tmp = tempfile.mkdtemp(prefix="coat_side_test.")
    own_root = os.path.join(tmp, "Documents", "3DCoat", "Exchange")
    job_root = os.path.join(tmp, "Documents", "AppLinks", "3D-Coat", "Exchange")
    os.makedirs(own_root, exist_ok=True)
    os.makedirs(job_root, exist_ok=True)

    coat, cmd = build_environment(tmp)
    bridge = import_script()

    # ---- importing must do nothing: 3D-Coat runs the file as a script ----
    check("importing the module opens nothing", coat.dialog_log == [], coat.dialog_log)

    # ---- the dialog entry runs unconditionally, the way 3D-Coat runs a script ----
    import runpy

    runpy.run_path(PANEL_ENTRY)
    steps = [name for name, _args in coat.dialog_log]
    check("panel is shown when run as a script", bool(steps) and steps[-1] == "show", steps)
    check("panel caption matches the Blender side",
          any(name == "caption" and args[0] == "CoatLink" for name, args in coat.dialog_log))
    check("panel is pinned to the top-right", "topRight" in steps and "noModal" in steps)
    check("panel width is set", any(name == "width" for name, _ in coat.dialog_log))
    check("panel has a close button",
          any(name == "buttons" and args[0] == "Close" for name, args in coat.dialog_log))
    # The panel must never query the host scene or touch the state file while it
    # is merely being redrawn; control edits persist through ui(), not a per-frame
    # callback (a per-frame mesh read was observed to disturb the sculpt tree).
    check("panel installs no per-frame callback",
          not any(name == "process" and callable(args[0]) for name, args in coat.dialog_log))
    idle_panel = bridge.CoatBridgePanel()
    probe_scene, probe_state = coat.Scene.current, bridge.load_state
    coat.Scene.current = lambda: (_ for _ in ()).throw(AssertionError("scene touched during redraw"))
    bridge.load_state = lambda: (_ for _ in ()).throw(AssertionError("state read during redraw"))
    for _ in range(50):
        idle_panel.ui()
        idle_panel.process()
    coat.Scene.current, bridge.load_state = probe_scene, probe_state
    check("50 idle redraws touch no scene and no state file", True)

    # ---- exchange discovery ----
    roots = bridge.exchange_roots()
    check("both exchange roots are found",
          [os.path.normcase(r) for r in roots] == [os.path.normcase(own_root), os.path.normcase(job_root)],
          roots)
    check("3D-Coat's own root is primary", os.path.normcase(bridge.primary_root()) == os.path.normcase(own_root))

    folder = bridge.ensure_folder(own_root)
    check("the BlenderBridge folder is created", os.path.isdir(folder), folder)
    check("run.txt marker exists and is empty",
          os.path.isfile(os.path.join(folder, "run.txt")) and os.path.getsize(os.path.join(folder, "run.txt")) == 0)

    # ---- Blender's queue file ----
    queued_model = os.path.join(folder, "bridge.obj")
    with open(queued_model, "w", encoding="utf-8") as handle:
        handle.write("# fake model\n")
    with open(bridge.import_txt(job_root), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(os.path.abspath(queued_model).replace("\\", "/") + "\n" + "x/y.obj\n[ppp]\n")
    check("the queue file is parsed", os.path.normcase(bridge.read_import_model(job_root)) == os.path.normcase(queued_model),
          bridge.read_import_model(job_root))
    check("an empty queue file yields nothing",
          bridge.read_import_model(os.path.join(job_root, "nope.txt")) == "")

    # ---- pull ----
    panel = bridge.CoatBridgePanel()
    panel.PullFromBlender()
    check("pull imports the queued model", coat.scene_imports == [queued_model], coat.scene_imports)
    check("pull reports what it took", "Pulled" in panel.status, panel.status)
    check("the queue file is consumed so 3D-Coat does not import it twice",
          not os.path.isfile(bridge.import_txt(job_root)))

    panel.PullFromBlender()
    check("pull with an empty queue imports the sent model instead",
          len(coat.scene_imports) == 2 and os.path.normcase(coat.scene_imports[-1]) == os.path.normcase(queued_model),
          coat.scene_imports)

    # ---- signal + sent model index ----
    signal = bridge.write_signal(own_root, queued_model)
    check("the export signal points at the model",
          os.path.isfile(signal) and os.path.normcase(open(signal).read().strip()) == os.path.normcase(queued_model))
    check("sent models are indexed", [os.path.basename(p) for p in bridge.sent_models(own_root)] == ["bridge.obj"],
          bridge.sent_models(own_root))

    # ---- send, whole-scene route (3D-Coat exports and announces it itself) ----
    # The default send scope is the selected tree node; the dialog/texture route
    # below belongs to the whole-scene export, so ask for it explicitly.
    def use_scope(name):
        """Pick the send scope, panel included: process() writes its own controls
        back, and later state resets forget what was stored."""
        bridge.set_send_scope(name)
        panel.SendScope = bridge.SEND_SCOPES.index(name)
        panel.process()
        return bridge.send_scope()

    check("the whole-scene scope can be chosen", use_scope("scene") == "scene", bridge.load_state())
    os.remove(signal)

    def applink_export(root):
        with open(bridge.model_path(root, "fbx"), "w", encoding="utf-8") as handle:
            handle.write("# exported by 3D-Coat\n")
        with open(bridge.signal_path(root), "w", encoding="utf-8", newline="\n") as handle:
            handle.write(bridge.model_path(root, "fbx") + "\n")

    coat.applink_present = True
    coat.applink_export = applink_export
    coat.ui.cmd.return_value = lambda *a, **k: applink_export(own_root) or True
    panel.SendToBlender()
    check("send uses the AppLink target when it exists", "AppLink" in panel.status, panel.status)
    check("send leaves 3D-Coat's own signal in place",
          os.path.isfile(bridge.signal_path(own_root))
          and bool(open(bridge.signal_path(own_root)).read().strip()))
    check("send tells 3D-Coat which file to use",
          any(args and "bridge.obj" in str(args[0]) for args in coat.ui.setFileForFileDialog.calls),
          coat.ui.setFileForFileDialog.calls)

    # ---- send, direct export fallback ----
    os.remove(bridge.signal_path(own_root))
    coat.applink_present = False

    def direct_export(path):
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("# exported directly\n")

    coat.direct_export = direct_export
    panel.SendToBlender()
    check("send falls back to the direct export", bool(cmd.calls) and cmd.calls[-1].endswith("bridge.obj"), cmd.calls[-1:])
    check("send writes the signal Blender watches", os.path.isfile(bridge.signal_path(own_root)))
    check("send reports the file", "Sent to Blender" in panel.status and "bridge.obj" in panel.status, panel.status)

    # ---- there is exactly one export format ----
    check("the panel keeps no format state", not hasattr(panel, "format"))
    check("3D-Coat hands back OBJ, the same format Blender sends",
          bridge.EXPORT_FORMAT == "obj", bridge.EXPORT_FORMAT)

    # ---- panel layout mirrors the Blender menu ----
    items = panel.ui()
    plain = [item for item in items if not item.startswith(("[", "#", "---"))]
    for name in plain:
        if "," in name:
            name = name.split(",", 1)[0]
        check("layout item '%s' exists on the panel" % name, hasattr(panel, name))
    check("layout starts with the send scope",
          items[0].startswith("SendScope,[#"), items[0])
    check("the panel keeps no fold-out either", not hasattr(panel, "Advanced"))
    check("so the advanced controls are on screen without unfolding",
          all(name in items for name in ("Detect", "OpenFolder", "StartBlender",
                                         "RemoveLauncher")),
          [item for item in items if item in ("Detect", "OpenFolder", "StartBlender",
                                              "RemoveLauncher", "Advanced")])
    check("the scope says what it will send",
          items[1] == "##" + bridge.SEND_SCOPE_HINTS[int(panel.SendScope)], items[:2])
    check("then the two actions in one row, like the Blender menu",
          items[2] == "[1 1]" and items[3] == "SendToBlender" and items[4] == "PullFromBlender",
          items[:5])
    check("with the sections headed like the Blender menu's",
          "Send options" in [item[1:] for item in items if item.startswith("#")]
          and "Setup" in [item[1:] for item in items if item.startswith("#")],
          [item for item in items if item.startswith("#")])
    panel.SendScope = bridge.SEND_SCOPES.index("selected")
    check("choosing another scope changes the hint",
          any(item == "##" + bridge.SEND_SCOPE_HINTS[0] for item in panel.ui()),
          [item for item in panel.ui() if item.startswith("##")][:2])
    panel.SendScope = bridge.SEND_SCOPES.index("scene")
    check("layout offers the same actions as Blender",
          {"SendToBlender", "PullFromBlender", "Detect", "OpenFolder", "StartBlender"} <=
          {item.split(",", 1)[0] for item in plain}, plain)
    check("the layout has no format control",
          not any(item.startswith("format,") for item in items), items)
    check("layout shows the status line", any(item.startswith("#") for item in items))
    check("layout tells the user how to reopen the panel",
          any(bridge.REOPEN_HINT in item for item in items), items)

    # ---- the two menus are meant to read the same ----
    translations = {args[0]: args[1] for args in coat.ui.addTranslation.calls if len(args) >= 2}
    check("the panel's buttons read Send / Pull, like the Blender menu",
          translations.get("SendToBlender") == "Send"
          and translations.get("PullFromBlender") == "Pull",
          {key: value for key, value in translations.items()
           if key in ("SendToBlender", "PullFromBlender")})
    check("the tool-strip buttons keep their longer labels",
          translations.get("CoatBridge_Send") == "Send to Blender"
          and translations.get("CoatBridge_Pull") == "Pull from Blender",
          {key: value for key, value in translations.items() if key.startswith("CoatBridge")})
    check("the scope droplist reads like the Blender menu's",
          bridge.SEND_SCOPE_LABELS == "#Selected|#Whole scene", bridge.SEND_SCOPE_LABELS)
    check("and both scopes are explained under it",
          len(bridge.SEND_SCOPE_HINTS) == 2, bridge.SEND_SCOPE_HINTS)
    for name in ("SendScope", "ReductionPercent", "Textures", "RefreshStats",
                 "Detect", "OpenFolder", "StartBlender", "RemoveLauncher"):
        check("the panel control '%s' has a readable label" % name,
              translations.get(name), translations)

    # ---- "To voxels": the one click that fixes a surface-mode import ----
    class _FakeVolume(object):
        def __init__(self, voxel):
            self.voxel = voxel
            self.converted = 0

        def isVoxelized(self):
            return self.voxel

        def toVoxels(self):
            self.converted += 1
            self.voxel = True

        def getPolycount(self):
            return 12

    class _FakeNode(object):
        def __init__(self, name, volumes, children=()):
            self._name = name
            self.volumes = volumes
            self.children = list(children)

        def name(self):
            return self._name

        def Volume(self):
            return self.volumes

        def childCount(self):
            return len(self.children)

        def child(self, index):
            return self.children[index] if 0 <= index < len(self.children) else None

    surface = _FakeVolume(False)
    voxel = _FakeVolume(True)
    group = _FakeNode("bridge", surface,
                      [_FakeNode("Cube.169", _FakeVolume(False)),
                       _FakeNode("Cube.170", voxel)])
    coat.current_element = group       # what 3D-Coat reports as the current object
    panel.VoxelizeSelected()
    check("To voxels converts the objects under the group",
          group.children[0].volumes.converted == 1, group.children[0].volumes.converted)
    check("and does not convert the packaging node itself",
          surface.converted == 0, surface.converted)
    check("and leaves one that is already a voxel volume alone",
          voxel.converted == 0, voxel.converted)
    check("and says what it did",
          panel.status == "To voxels: 1 to voxels, 1 already voxel", panel.status)
    panel.VoxelizeSelected()
    check("running it again converts nothing new",
          group.children[0].volumes.converted == 1 and panel.status == "To voxels: 2 already voxel",
          (group.children[0].volumes.converted, panel.status))

    class _EmptyNode(object):
        def name(self):
            return "nothing"

        def Volume(self):
            raise RuntimeError("no volume")

        def childCount(self):
            return 0

    coat.current_element = _EmptyNode()
    panel.VoxelizeSelected()
    check("an object with no volume is reported, not thrown",
          "could not be converted" in panel.status, panel.status)
    coat.current_element = None
    panel.VoxelizeSelected()
    check("nothing selected is a sentence, not a crash",
          panel.status == "Select an object in the Sculpt Tree first", panel.status)
    coat.current_element = UNSET        # back to "the fake decides"

    # ---- menu registration (the panel entry already ran it) ----
    bridge.save_state({"menus": [], "tools": []})   # forget the entry's registration
    coat.menu_inserted = False      # and that 3D-Coat reports the menu missing again
    coat.inserted = []
    check("first run registers Scripts and Windows",
          bridge.register_menu_item() == ["Scripts", "Windows"]
          and coat.inserted[:2] == [("Scripts", "CoatBridge", ""), ("Windows", "CoatBridge", "")],
          (bridge.load_state().get("menus"), coat.inserted))
    check("registering again adds nothing", bridge.register_menu_item() == [])
    check("the menu record is kept in the state file",
          bridge.load_state().get("menus") == ["Scripts", "Windows"], bridge.load_state())

    # a fresh state (entries gone) must bring both launchers back.
    # Write the file directly: save_state() merges on purpose, so it cannot
    # drop a key - the test has to simulate the file itself.
    import json as _json

    def write_state(keys):
        with open(bridge.state_path(), "w", encoding="utf-8", newline="\n") as handle:
            _json.dump(keys, handle)

    coat.inserted = []
    write_state({"format": "FBX"})
    check("a fresh state re-registers both menus",
          bridge.register_menu_item() == ["Scripts", "Windows"] and len(coat.inserted) == 2, coat.inserted)

    # with the shipped XML in place, Scripts is reported as already provided
    coat.inserted = []
    coat.menu_inserted = True
    write_state({"format": "FBX"})
    check("an existing menu entry is detected instead of duplicated",
          bridge.register_menu_item() == ["Windows"] and coat.inserted == [("Windows", "CoatBridge", "")],
          coat.inserted)

    # ---- room tool button ----
    write_state({"format": "FBX"})  # fresh: nothing recorded yet
    added = bridge.register_room_tools()
    check("the tool button is inserted into the listed rooms", added == ["Voxels"], added)
    check("insertInToolset is called with the room and our id",
          ("Voxels", "", "CoatBridge") in coat.ui.insertInToolset.calls, coat.ui.insertInToolset.calls)
    check("tool registration is idempotent", bridge.register_room_tools() == [])
    check("the room list is recorded", bridge.load_state().get("tools") == ["Voxels"], bridge.load_state())

    # Removal takes both launchers back out and clears the record
    coat.ui.removeCommandFromMenu.calls = []
    panel.RemoveLauncher()
    check("removal calls the API with our id",
          coat.ui.removeCommandFromMenu.calls == [("CoatBridge",)], coat.ui.removeCommandFromMenu.calls)
    check("removal clears the records",
          bridge.load_state().get("tools") == [] and bridge.load_state().get("menus") == [],
          bridge.load_state())
    check("removal reports back", "removed" in panel.status.lower(), panel.status)

    # and a fresh state puts the tool button back
    write_state({"format": "FBX"})
    check("a fresh state re-inserts the tool button", bridge.register_room_tools() == ["Voxels"])

    # ---- the size block: read the object, scale it to a target ----
    coat.current_size = [2.0, 1.0, 0.5]
    check("the panel reads the current size", bridge.current_size()[:3] == (2.0, 1.0, 0.5),
          bridge.current_size())
    check("and shows it with units", bridge.size_line() == "Size: 2.000 x 1.000 x 0.500 m",
          bridge.size_line())
    check("the panel has no scene-scaling controls",
          "TargetSize,[0.001,1000]" not in panel.ui() and "ApplySize" not in panel.ui(), panel.ui())

    coat.transforms = []
    panel.TargetSize = 4.0
    panel.ApplySize()
    check("applying scales the current object in 3D-Coat", len(coat.transforms) == 1, coat.transforms)
    operation, origin, factor = coat.transforms[0]
    check("it scales about the object's own centre", operation == "ScalingAt", coat.transforms[0])
    check("by the ratio target/longest side", abs(factor - 2.0) < 1e-6, factor)
    check("the status line reports the change", "2.000 -> 4.000" in panel.status, panel.status)
    check("the log keeps the factor", "longest side 2.0000 -> 4.0000" in bridge.log_text(),
          bridge.log_text()[-160:])

    panel.TargetSize = 0
    check("a zero target is refused", "above zero" in bridge.scale_to_size(0), bridge.scale_to_size(0))
    check("a junk target is refused", "not a number" in bridge.scale_to_size("big"),
          bridge.scale_to_size("big"))

    coat.current_size = [0.0, 0.0, 0.0]
    check("an empty object is not divided by zero",
          "no measurable size" in bridge.scale_to_size(4.0), bridge.scale_to_size(4.0))
    coat.current_size = [2.0, 1.0, 0.5]

    saved_current = coat.Scene.current
    coat.Scene.current = lambda: (_ for _ in ()).throw(RuntimeError("nothing selected"))
    check("nothing selected is reported, not crashed",
          bridge.size_line() == "Size: no object selected" and
          "select something" in bridge.scale_to_size(4.0), bridge.size_line())
    coat.Scene.current = saved_current

    # ---- 3D-Coat's own size / axis settings, shared with Blender ----
    info = bridge.coat_settings_info()
    check("the scene scale is read from 3D-Coat", info.get("scene_scale") == 1.0, info)
    check("so are the units", info.get("scene_units") == "m", info)
    check("and the swap Y/Z option", info.get("swap_yz") is True, info)
    check("they land in the state file Blender reads",
          (bridge.load_state().get("coat") or {}).get("swap_yz") is True, bridge.load_state())
    check("the log records them", "coat settings: scale=" in bridge.log_text(), bridge.log_text()[-160:])

    saved = coat.settings_values
    coat.settings_values = {}          # a 3D-Coat build without that option
    info = bridge.coat_settings_info()
    check("a missing setting is reported, not fatal", info.get("swap_yz") is None, info)
    check("the readable settings still come through", info.get("scene_scale") == 1.0, info)
    coat.settings_values = saved

    # ---- the reduction percentage (3D-Coat's own slider) ----
    use_scope("scene")      # the dialog route below belongs to the whole-scene export
    slider = bridge.REDUCTION_SLIDER
    check("the slider id is 3D-Coat's own", slider == "$DecimationParams::ReductionPercent", slider)

    # nothing stored yet: the export dialog is left alone, nothing is pressed
    bridge.set_reduction_percent(0)
    coat.applink_present = True
    cmd.calls = []
    panel.SendToBlender()
    check("with no stored percentage nothing is pushed into 3D-Coat",
          ("slider", slider, 50.0) not in cmd.calls and bridge.reduction_percent() == 0,
          [call for call in cmd.calls if isinstance(call, tuple)])

    # first real export: we read the value 3D-Coat's dialog shows and remember it
    cmd.sliders[slider] = 40.0
    panel.SendToBlender()
    check("the first export remembers the percentage from 3D-Coat",
          bridge.reduction_percent() == 40, bridge.load_state())
    check("and says so in the log", "remembered reduction 40%" in bridge.log_text(), bridge.log_text()[-200:])
    # a freshly opened panel picks the stored value up (its layout is built from
    # the panel's own attributes, so a panel that is merely constructed - not
    # shown - must not be asked to persist anything)
    bridge.set_reduction_percent(40)
    check("that number field starts at the stored value",
          bridge.CoatBridgePanel().ReductionPercent == 40,
          bridge.CoatBridgePanel().ReductionPercent)
    check("the panel carries a native number field for the percentage",
          "ReductionPercent,[0,100]" in panel.ui(), panel.ui())
    check("the panel carries a native choice for textures",
          any(item.startswith("Textures,[") for item in panel.ui()), panel.ui())
    bridge.set_reduction_percent(40)
    panel.ReductionPercent = 35
    panel.process()
    check("a number typed in the panel is stored", bridge.reduction_percent() == 35, bridge.load_state())
    bridge.set_reduction_percent(50)

    # from now on our value is pushed in and the dialog is confirmed automatically
    cmd.calls = []
    bridge.set_reduction_percent(50)
    panel.SendToBlender()
    check("a stored percentage is pushed into 3D-Coat's slider", ("slider", slider, 50.0) in cmd.calls,
          [call for call in cmd.calls if isinstance(call, tuple)])
    check("the export dialog is still confirmed for the user",
          ("$DialogButton#1",) in coat.ui.cmd.calls, coat.ui.cmd.calls[-3:])
    check("the slider really holds our value", cmd.sliders.get(slider) == 50.0, cmd.sliders)
    check("the status line reports the reduction", "reduction requested 50%" in panel.status, panel.status)

    # 0 in the number field hands the choice back to 3D-Coat's own dialog
    panel.ReductionPercent = 0
    panel.process()
    check("0 means 3D-Coat's dialog decides again", bridge.reduction_percent() == 0,
          bridge.load_state())

    # ---- the texture switch (same idea, one state further) ----
    use_scope("scene")
    field = bridge.TEXTURES_FIELD
    check("the textures field is 3D-Coat's own", field == "$ExportOpt::ExportTextures", field)

    bridge.set_export_textures(None)
    check("unset means 3D-Coat decides", bridge.export_textures() is None, bridge.export_textures())
    cmd.calls = []
    panel.SendToBlender()
    check("with nothing set the textures field is untouched",
          ("bool", field, False) not in cmd.calls, [call for call in cmd.calls if isinstance(call, tuple)])

    panel.Textures = 1
    panel.process()
    check("the second entry asks for textures on", bridge.export_textures() is True, bridge.load_state())
    panel.Textures = 2
    panel.process()
    check("the third entry asks for textures off", bridge.export_textures() is False, bridge.load_state())
    panel.Textures = 0
    panel.process()
    check("the first entry hands it back to 3D-Coat", bridge.export_textures() is None, bridge.load_state())

    bridge.set_export_textures(False)
    cmd.calls = []
    panel.SendToBlender()
    check("textures off is pushed into 3D-Coat's dialog", ("bool", field, False) in cmd.calls,
          [call for call in cmd.calls if isinstance(call, tuple)])
    check("3D-Coat really holds textures off", cmd.bools.get(field) is False, cmd.bools)
    check("the status line mentions textures", "textures off" in panel.status, panel.status)
    bridge.set_export_textures(None)

    # ---- the Setup button opens 3D-Coat's own panel, never a Qt window ----
    coat.dialog_log = []
    coat.ui.cmd.calls = []
    check("no Qt module is pulled in by the panel", "PySide6" not in sys.modules,
          [name for name in sys.modules if "PySide" in name])
    status = bridge.run_action("CoatBridge_Setup")
    steps = [name for name, _args in coat.dialog_log]
    check("Setup opens 3D-Coat's own dialog", "show" in steps and "caption" in steps, coat.dialog_log)
    check("the panel is anchored in 3D-Coat's window", "topRight" in steps, coat.dialog_log)
    check("the panel carries the reduction controls",
          any(str(item).startswith("ReductionPercent,") for item in bridge.CoatBridgePanel().ui()),
          bridge.CoatBridgePanel().ui())
    check("Setup reports back", bool(status), status)

    # ---- blender lookup ----
    check("no Blender found -> empty path", bridge.find_blender_executable() == "")

    failed = [item for item in RESULTS if not item[1]]
    print("\nRESULT: %d/%d checks passed" % (len(RESULTS) - len(failed), len(RESULTS)))
    for name, _ok, detail in failed:
        print("FAILED: %s -- %s" % (name, detail))
    shutil.rmtree(tmp, ignore_errors=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
