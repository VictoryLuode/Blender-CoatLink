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
from fake_coat import FakeCoat, TreeNode, UNSET, build_environment  # shared fake 3D-Coat API

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, "..", "CoatLinkLib.py")
PANEL_ENTRY = os.path.join(HERE, "..", "CoatLink_Setup.py")

RESULTS = []


def check(name, condition, detail=""):
    RESULTS.append((name, bool(condition), detail))
    print("%-4s %s%s" % ("PASS" if condition else "FAIL", name,
                         "" if condition else "   <- %s" % (detail,)))


def import_script():
    spec = importlib.util.spec_from_file_location("coatlink_lib", LIB)
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
    idle_panel = bridge.CoatLinkPanel()
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
          [os.path.normcase(r) for r in roots] == [os.path.normcase(job_root), os.path.normcase(own_root)],
          roots)
    # the shared root leads: 3D-Coat's engine only polls the job file there
    check("the shared root is primary", os.path.normcase(bridge.primary_root()) == os.path.normcase(job_root))

    folder = bridge.ensure_folder(own_root)
    check("the exchange folder is created", os.path.isdir(folder), folder)
    check("run.txt marker exists and is empty",
          os.path.isfile(os.path.join(folder, "run.txt")) and os.path.getsize(os.path.join(folder, "run.txt")) == 0)

    # ---- the export target name, and the name it replaced ----
    # 3D-Coat lists a target because of this marker, so the old name only leaves
    # File > Export To once the marker goes - and the name must not be the one
    # 3D-Coat's Scripts menu uses for this same extension.
    check("the export target is not named like the Scripts entry",
          bridge.APP_FOLDER != bridge.MENU_ID, (bridge.APP_FOLDER, bridge.MENU_ID))
    check("the folder carries the name 3D-Coat lists",
          os.path.basename(folder) == bridge.APP_FOLDER == "CoatLinkBridge", folder)
    legacy = os.path.join(own_root, bridge.LEGACY_APP_FOLDERS[0])
    os.makedirs(legacy, exist_ok=True)
    with open(os.path.join(legacy, bridge.RUN_MARKER), "w", encoding="utf-8") as handle:
        handle.write("")
    old_model = os.path.join(legacy, "bridge.obj")
    with open(old_model, "w", encoding="utf-8") as handle:
        handle.write("# fake model\\n")
    bridge.ensure_folder(own_root)
    check("the old target name leaves the export list",
          not os.path.isfile(os.path.join(legacy, bridge.RUN_MARKER)), legacy)
    check("retiring a name keeps the folder and what it holds",
          os.path.isdir(legacy) and os.path.isfile(old_model))
    check("a model handed back into the old folder is still ours",
          bridge.is_our_model(own_root, old_model))

    # the primary root needs its folder too: the queue readout and the pull below
    # both look there first
    bridge.ensure_folder(bridge.primary_root())

    # ---- Blender's queue file ----
    queued_model = os.path.join(folder, "bridge.obj")
    with open(queued_model, "w", encoding="utf-8") as handle:
        handle.write("# fake model\n")
    with open(bridge.import_txt(own_root), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(os.path.abspath(queued_model).replace("\\", "/") + "\n" + "x/y.obj\n[ppp]\n")
    check("the queue file is parsed", os.path.normcase(bridge.read_import_model(own_root)) == os.path.normcase(queued_model),
          bridge.read_import_model(own_root))
    check("an empty queue file yields nothing",
          bridge.read_import_model(os.path.join(own_root, "nope.txt")) == "")

    # ---- pull ----
    panel = bridge.CoatLinkPanel()
    check("the native panel exposes Copy details", "CopyDetails" in panel.ui())
    check("refresh label describes sizes and voxel/surface statistics",
          bridge.PANEL_LABELS["RefreshStats"] == "Refresh info")
    panel.status = "A very long status " * 60
    panel.detail = "C:/a/very/long/path/" * 60
    long_layout = panel.ui()
    check("the status section uses bounded native text rows",
          "#Status" in long_layout and max(map(len, long_layout)) <= 100,
          max(map(len, long_layout)))
    original_run = bridge.subprocess.run
    clipboard_calls = []
    before_status, before_detail = panel.status, panel.detail
    bridge.subprocess.run = lambda *args, **kwargs: clipboard_calls.append((args, kwargs))
    try:
        panel.CopyDetails()
        check("copy includes untruncated diagnostic text and preserves the readout",
              len(clipboard_calls) == 1
              and before_detail in clipboard_calls[0][1]["input"].decode("utf-16")
              and panel.status == before_status and panel.detail == before_detail)
        def clipboard_failure(*args, **kwargs):
            raise OSError("clipboard unavailable")
        bridge.subprocess.run = clipboard_failure
        panel.CopyDetails()
        check("clipboard errors stay visible instead of escaping the native callback",
              "Could not copy details" in panel.status, panel.status)
    finally:
        bridge.subprocess.run = original_run
    panel.status = "Ready"
    panel.detail = ""
    check("short and long diagnostics occupy the same number of native rows",
          len(panel.ui()) == len(long_layout))

    # ---- Queue readout: what Blender left for us, without reading disk per frame ----
    queue_root = bridge.primary_root()
    panel.refresh_detail()
    check("an empty queue is reported as such",
          "nothing" in panel.QueueLabel, panel.QueueLabel)
    queued_path = os.path.join(bridge.app_folder(queue_root), "queued.obj")
    with open(queued_path, "w", encoding="utf-8") as handle:
        handle.write("# fake model\n")
    with open(bridge.import_txt(queue_root), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(os.path.abspath(queued_path).replace("\\", "/") + "\n[ppp]\n")
    panel.refresh_detail()
    check("a queued model is named, so Pull is obviously the next step",
          "queued.obj" in panel.QueueLabel, panel.QueueLabel)
    check("the queue readout is drawn in the panel",
          any(item.startswith("##") and "queued.obj" in item for item in panel.ui()), panel.ui()[-8:])
    os.remove(queued_path)
    os.remove(bridge.import_txt(queue_root))
    panel.PullFromBlender()
    check("pull imports the queued model", coat.scene_imports == [queued_model], coat.scene_imports)
    check("pull reports what it took", "Pulled" in panel.status, panel.status)
    check("the queue file is consumed so 3D-Coat does not import it twice",
          not os.path.isfile(bridge.import_txt(own_root)))

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
    coat.ui.cmd.return_value = lambda *a, **k: applink_export(bridge.primary_root()) or True
    panel.SendToBlender()
    check("send uses the AppLink target when it exists", "AppLink" in panel.status, panel.status)
    check("send leaves 3D-Coat's own signal in place",
          os.path.isfile(bridge.signal_path(bridge.primary_root()))
          and bool(open(bridge.signal_path(bridge.primary_root())).read().strip()))
    check("send tells 3D-Coat which file to use",
          any(args and "bridge.obj" in str(args[0]) for args in coat.ui.setFileForFileDialog.calls),
          coat.ui.setFileForFileDialog.calls)

    # ---- send, direct export fallback ----
    os.remove(bridge.signal_path(bridge.primary_root()))
    coat.applink_present = False

    def direct_export(path):
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("# exported directly\n")

    coat.direct_export = direct_export
    panel.SendToBlender()
    check("send falls back to the direct export", bool(cmd.calls) and cmd.calls[-1].endswith("bridge.obj"), cmd.calls[-1:])
    check("send writes the signal Blender watches", os.path.isfile(bridge.signal_path(bridge.primary_root())))
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
    check("layout starts with the two actions in one row, like the Blender menu",
          items[:3] == ["[1 1]", "SendToBlender", "PullFromBlender"], items[:3])
    check("the panel keeps no fold-out either", not hasattr(panel, "Advanced"))
    check("so the advanced controls are on screen without unfolding",
          all(name in items for name in ("Detect", "OpenFolder", "StartBlender",
                                         "RemoveLauncher")),
          [item for item in items if item in ("Detect", "OpenFolder", "StartBlender",
                                              "RemoveLauncher", "Advanced")])
    scope_index = next(index for index, item in enumerate(items)
                       if item.startswith("SendScope,[#"))
    check("the scope is the first thing inside the Send options block, like Blender's",
          items.index("#Send options") < scope_index < items.index("#" + panel.SizeLabel),
          items[:8])
    check("the scope says what it will send",
          items[scope_index + 1] == "##" + bridge.SEND_SCOPE_HINTS[int(panel.SendScope)],
          items[scope_index:scope_index + 2])
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
          translations.get("CoatLink_Send") == "Send to Blender"
          and translations.get("CoatLink_Pull") == "Pull from Blender",
          {key: value for key, value in translations.items() if key.startswith("CoatLink")})
    check("the scope droplist reads like the Blender menu's",
          bridge.SEND_SCOPE_LABELS == "#Selected|#Whole scene", bridge.SEND_SCOPE_LABELS)
    check("and both scopes are explained under it",
          len(bridge.SEND_SCOPE_HINTS) == 2, bridge.SEND_SCOPE_HINTS)
    for name in ("SendScope", "ReductionPercent", "Textures", "RefreshStats",
                 "Detect", "OpenFolder", "StartBlender", "RemoveLauncher"):
        check("the panel control '%s' has a readable label" % name,
              translations.get(name), translations)

    # ---- the readout says voxel or surface, so V/S need not be hunted for ----
    class _ModeVolume(object):
        def __init__(self, voxel=False, surface=False):
            self.voxel, self.surface = voxel, surface

        def getPolycount(self):
            return 42

        def isVoxelized(self):
            return self.voxel

        def isSurface(self):
            return self.surface

    class _ModeElement(object):
        def __init__(self, volume):
            self.volume = volume

        def Volume(self):
            return self.volume

    for volume, expected in ((_ModeVolume(surface=True), "surface mode"),
                             (_ModeVolume(voxel=True), "voxel volume")):
        coat.current_element = _ModeElement(volume)
        panel.RefreshStats()
        check("the readout says '%s'" % expected, expected in panel.StatsLabel,
              panel.StatsLabel)
    coat.current_element = _ModeElement(_ModeVolume())      # neither answers yes
    panel.RefreshStats()
    check("a volume that answers neither adds nothing",
          panel.StatsLabel.startswith("Snapshot: 42 faces"),
          panel.StatsLabel)
    coat.current_element = _ModeElement(None)
    panel.RefreshStats()
    check("an unreadable object is a sentence, not a crash",
          panel.StatsLabel.startswith("Statistics unavailable"), panel.StatsLabel)
    coat.current_element = UNSET

    # ---- "To voxels": one click for everything the tree is showing ----
    class _FakeVolume(object):
        def __init__(self, voxel=True, broken=False):
            self.voxel = voxel
            self.broken = broken
            self.converted = 0

        def isVoxelized(self):
            return self.voxel

        def toVoxels(self):
            if self.broken:
                raise RuntimeError("cannot voxelize")
            self.converted += 1
            self.voxel = True

        def getPolycount(self):
            return 12

    def node(name, fake_volume, parent=None, visible=True):
        """A tree node with the parts the action reads, faked per instance."""
        element = TreeNode(name, coat, parent)
        element.Volume = lambda: fake_volume
        element.visible = lambda: visible
        return element

    # a scene like the real one: a packaging group from an import, one plain visible
    # object, and one switched off in the tree
    coat.root.children.clear()
    coat.removed.clear()
    wrapper = node("bridge", _FakeVolume(True), coat.root)
    surface_obj = node("Cube.169", _FakeVolume(False), wrapper)
    voxel_obj = node("Cube.170", _FakeVolume(True), wrapper)
    plain = node("Box", _FakeVolume(False), coat.root)
    hidden = node("Cube.171", _FakeVolume(False), coat.root, visible=False)

    panel.VoxelizeVisible()
    check("To voxels converts every visible surface object",
          surface_obj.Volume().converted == 1 and plain.Volume().converted == 1,
          (surface_obj.Volume().converted, plain.Volume().converted))
    check("and leaves the ones that are already voxel volumes",
          voxel_obj.Volume().converted == 0, voxel_obj.Volume().converted)
    check("and does not convert the packaging node itself",
          wrapper.Volume().converted == 0, wrapper.Volume().converted)
    check("and does not touch an object that is switched off in the tree",
          hidden.Volume().converted == 0, hidden.Volume().converted)
    check("and says exactly what it did",
          panel.status == "To voxels: 2 to voxels, 1 already voxel, 1 hidden/unreadable branches, left alone",
          panel.status)

    panel.VoxelizeVisible()
    check("running it again converts nothing new",
          surface_obj.Volume().converted == 1
          and panel.status == "To voxels: 3 already voxel, 1 hidden/unreadable branches, left alone",
          panel.status)

    broken = node("Broken", _FakeVolume(False, broken=True), coat.root)
    panel.VoxelizeVisible()
    check("an object that cannot be converted is reported, not thrown",
          "1 could not be converted" in panel.status, panel.status)
    broken.remove()

    coat.root.children.clear()
    panel.VoxelizeVisible()
    check("an empty tree is a sentence, not a crash",
          panel.status == "Nothing in the Sculpt Tree to convert", panel.status)

    # Hidden parents hide their descendants, even when a child's local flag is on.
    coat.root.children.clear()
    hidden_group = node("Hidden group", _FakeVolume(False), coat.root, visible=False)
    hidden_child = node("Child", _FakeVolume(False), hidden_group)
    panel.VoxelizeVisible()
    check("a hidden parent's child is never converted",
          hidden_child.Volume().converted == 0, panel.status)

    # Unknown visibility is not permission to modify geometry.
    coat.root.children.clear()
    unknown = node("NoVisibility", _FakeVolume(False), coat.root)
    del unknown.visible
    panel.VoxelizeVisible()
    check("unknown visibility leaves geometry untouched",
          unknown.Volume().converted == 0, panel.status)
    check("and the old selection-only name is gone",
          not hasattr(panel, "VoxelizeSelected"))

    # ---- To voxels should press 3D-Coat's own tree badge, not just the API ----
    # The badge is the button in a tree row (id `$VoxTreeBranch.VoxSurf.<name>`)
    # whose own tooltip reads "Press this button to transform surface to voxel
    # representation" - the conversion the user does by hand and reports as more
    # accurate than the Volume API, so it is tried first and verified afterwards.
    coat.root.children.clear()
    pressed = []
    real_cmd = coat.ui.cmd
    converts = []

    def record_and_maybe_convert(*args):
        if args and isinstance(args[0], str) and args[0].startswith("$VoxTreeBranch"):
            pressed.append(args[0])
            for element in converts:
                if args[0] == bridge.VOXEL_TOGGLE_ID % element.name():
                    element.Volume().voxel = True      # 3D-Coat's own button did it
        return real_cmd(*args)

    coat.ui.cmd = record_and_maybe_convert
    try:
        badged = node("Badged", _FakeVolume(False), coat.root)
        converts.append(badged)
        silently_ignored = node("Ignored by host", _FakeVolume(False), coat.root)
        already_voxel = node("AlreadyVoxel", _FakeVolume(True), coat.root)
        def confirm_clicks():
            return [call for call in real_cmd.calls
                    if call and call[0] == "$DialogButton#1"]
        confirms_before = len(confirm_clicks())
        panel.VoxelizeVisible()
        check("the conversion dialog is accepted without the user clicking OK",
              len(confirm_clicks()) > confirms_before, real_cmd.calls[-4:])
        check("the accept is handed to 3D-Coat as the press's callback",
              any(len(call) > 1 and callable(call[1]) for call in real_cmd.calls
                  if call and str(call[0]).startswith("$VoxTreeBranch")),
              [call for call in real_cmd.calls if call and len(call) > 1])
        check("the tree row's own badge is pressed for a surface object",
              (bridge.VOXEL_TOGGLE_ID % "Badged") in pressed, pressed)
        check("and the conversion it caused is what the panel counts",
              badged.Volume().voxel is True and badged.Volume().converted == 0,
              (badged.Volume().voxel, badged.Volume().converted))
        check("the status says the tree button did it",
              "via 3D-Coat's tree button" in panel.status, panel.status)
        check("an object the badge does nothing for falls back to the API",
              silently_ignored.Volume().converted == 1
              and silently_ignored.Volume().voxel is True,
              (silently_ignored.Volume().converted, panel.status))
        check("an object that is already voxel is not pressed",
              (bridge.VOXEL_TOGGLE_ID % "AlreadyVoxel") not in pressed, pressed)
        check("the badge id is the one 3D-Coat logs for its own clicks",
              bridge.VOXEL_TOGGLE_ID.endswith("%s")
              and bridge.VOXEL_TOGGLE_ID.startswith("$VoxTreeBranch.VoxSurf."),
              bridge.VOXEL_TOGGLE_ID)
    finally:
        coat.ui.cmd = real_cmd

    # ---- the panel can say how much of the tree is still in surface mode ----
    coat.root.children.clear()
    packaging = node("bridge", _FakeVolume(True), coat.root)
    node("SurfaceA", _FakeVolume(False), packaging)      # inside the import group
    node("SurfaceB", _FakeVolume(False), coat.root)
    node("VoxelC", _FakeVolume(True), coat.root)
    node("HiddenD", _FakeVolume(False), coat.root, visible=False)
    panel.RefreshStats()
    check("Refresh info reports how much of the tree is still surface",
          panel.ModeLabel == "2 of 3 visible objects in surface mode - press To voxels",
          panel.ModeLabel)
    check("the mode summary is drawn for the user",
          any(item.startswith("##") and "surface mode" in item for item in panel.ui()),
          panel.ui()[-9:])
    panel.VoxelizeVisible()
    check("and it reads clear once they are voxel volumes",
          panel.ModeLabel == "0 of 3 visible objects in surface mode", panel.ModeLabel)
    coat.root.children.clear()
    panel.RefreshStats()
    check("an empty tree claims nothing about modes", panel.ModeLabel == "", panel.ModeLabel)

    # ---- the menu entry: an XML file 3D-Coat reads at every start ----
    # It used to be inserted at run time.  Only the file survives a restart, and an
    # id that is in both the file and 3D-Coat's own insertion file is listed twice.
    scripts = os.path.join(bridge.user_data_dir(), "UserPrefs", "Scripts")
    extra = os.path.join(scripts, "ExtraMenuItems")
    # the XML has to name the copy that is running, not the Scripts root
    where = os.path.dirname(os.path.abspath(bridge.__file__)).replace("\\", "/")
    os.makedirs(extra, exist_ok=True)
    menu_xml = os.path.join(extra, "CoatLink.xml")
    tools_xml = os.path.join(extra, "CoatLinkTools.xml")

    def read(path):
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()

    check("the first run writes the menu file", bridge.register_menu_item() == ["CoatLink.xml"],
          bridge.register_menu_item())
    text = read(menu_xml)
    check("the file carries one entry, in the Scripts menu",
          text.count("<ExtraMenuItem>") == 1 and "<MenuPath>Scripts</MenuPath>" in text
          and "Windows" not in text,
          text)
    check("its command points at this copy's own setup script",
          "script:%s/CoatLink_Setup.py" % where in text, text)
    check("writing it again changes nothing", bridge.register_menu_item() == [])

    # the files coming back is the whole repair path: nothing is reinstalled
    import json as _json

    def write_state(keys):
        with open(bridge.state_path(), "w", encoding="utf-8", newline="\n") as handle:
            _json.dump(keys, handle)

    for path in (menu_xml, tools_xml):
        if os.path.isfile(path):
            os.remove(path)
    write_state({"format": "FBX"})
    added = sorted(bridge.ensure_launcher())
    check("a deleted menu file is written again", added == ["CoatLink.xml", "CoatLinkTools.xml"], added)
    check("ensure_launcher is idempotent", bridge.ensure_launcher() == [])

    # ---- leftovers of older builds, and of 3D-Coat's run-time insertions ----
    # An id that is in our XML *and* in one of 3D-Coat's own insertion files is
    # listed twice, so those files go - and so do the pre-rename ones, which point
    # at scripts that are no longer there.
    stale = os.path.join(extra, "CoatLink_Old.xml")
    prerename = os.path.join(extra, "CoatBridge.xml")
    theirs = os.path.join(extra, "CoatMenu.xml")
    for path in (stale, prerename, theirs):
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("x")
    bridge.ensure_launcher()
    check("3D-Coat's own insertion file for our id is removed", not os.path.exists(stale))
    check("the pre-rename menu file is removed", not os.path.exists(prerename))
    check("somebody else's menu file is left alone", os.path.exists(theirs))

    # ---- tool buttons: one entry per button per room, the same file route ----
    write_state({"format": "FBX"})
    if os.path.isfile(tools_xml):
        os.remove(tools_xml)        # ensure_launcher() already wrote it
    check("the tool file is written", bridge.register_room_tools() == ["CoatLinkTools.xml"],
          bridge.register_room_tools())
    tools = read(tools_xml)
    check("one entry per button per room",
          tools.count("<ExtraMenuItem>") == len(bridge.TOOL_ROOMS) * len(bridge.TOOL_ACTIONS),
          tools.count("<ExtraMenuItem>"))
    check("the buttons name their room and their script",
          "<inRoom>Paint</inRoom>" in tools
          and "script:%s/CoatLink_Send.py" % where in tools, tools)
    check("tool registration is idempotent", bridge.register_room_tools() == [])

    # Removal takes the files back out: the files are what puts the entries there
    panel.RemoveLauncher()
    check("removal deletes both files",
          not os.path.isfile(menu_xml) and not os.path.isfile(tools_xml))
    check("removal reports back", "removed" in panel.status.lower(), panel.status)

    # and the next open writes them again
    write_state({"format": "FBX"})
    check("the next open writes them again",
          sorted(bridge.ensure_launcher()) == ["CoatLink.xml", "CoatLinkTools.xml"])

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
    check("a log line says which half wrote it",
          any(" | 3dcoat | " in line for line in bridge.log_text().splitlines()),
          bridge.log_text()[-160:])

    # ---- the data folder the scripts live in: agreement with the Blender half ----
    # Both halves, the installer and the after-import helper keep CoatLink.log and
    # CoatLink.json in <Documents>/3DCoat.  Landing in UserPrefs instead split one
    # trip's evidence across two files and left Blender reading a stale axis/units
    # record, so the folder is pinned here.
    deep = os.path.join(tmp, "Documents", "3DCoat", "UserPrefs", "Scripts", "CoatLink")
    check("the data folder is found above UserPrefs",
          bridge.data_folder_of(deep).replace("\\", "/").endswith("/Documents/3DCoat"),
          bridge.data_folder_of(deep))
    old = os.path.join(tmp, "Documents", "3D-CoatV48", "Scripts", "CoatLink")
    check("and above the 4.x Scripts layout",
          bridge.data_folder_of(old).replace("\\", "/").endswith("/3D-CoatV48"),
          bridge.data_folder_of(old))
    check("a script outside 3D-Coat's own folders names nothing",
          bridge.data_folder_of(os.path.join(tmp, "somewhere", "elsewhere")) == "",
          bridge.data_folder_of(os.path.join(tmp, "somewhere", "elsewhere")))

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
          bridge.CoatLinkPanel().ReductionPercent == 40,
          bridge.CoatLinkPanel().ReductionPercent)
    check("the panel carries a native number field for the percentage",
          "ReductionPercent,[0,100]" in panel.ui(), panel.ui())
    check("the panel carries a native choice for textures, off first",
          "Textures,[#textures off|#textures on]" in panel.ui(), panel.ui())
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

    # one state, not three: this bridge carries models, so its own exports keep the
    # texture files out of the exchange folder unless someone asks for them
    bridge.set_export_textures(False)
    cmd.calls = []
    panel.SendToBlender()
    check("textures off is pushed into 3D-Coat's dialog",
          ("bool", field, False) in cmd.calls, [call for call in cmd.calls if isinstance(call, tuple)])
    check("3D-Coat really holds textures off", cmd.bools.get(field) is False, cmd.bools)
    check("the status line mentions textures", "textures off" in panel.status, panel.status)

    panel.Textures = 1
    panel.process()
    check("the second entry is the only way to ask for textures",
          bridge.export_textures() is True, bridge.load_state())
    cmd.calls = []
    panel.SendToBlender()
    check("asked for, textures on is pushed too", ("bool", field, True) in cmd.calls,
          [call for call in cmd.calls if isinstance(call, tuple)])

    panel.Textures = 0
    panel.process()
    check("back to the first entry means off again", bridge.export_textures() is False,
          bridge.load_state())

    # a state file from a build that had the third state still reads as a decision
    bridge.save_state({bridge.TEXTURES_KEY: "auto"})
    check("a stored \"auto\" reads as off, not as undefined",
          bridge.export_textures() is False, bridge.load_state())
    bridge.save_state({bridge.TEXTURES_KEY: "on"})
    check("and a stored \"on\" is kept", bridge.export_textures() is True, bridge.load_state())

    # leave the panel and the state file in step for what follows
    bridge.set_export_textures(False)
    panel.Textures = 0
    panel.process()

    # ---- the Setup button opens 3D-Coat's own panel, never a Qt window ----
    coat.dialog_log = []
    coat.ui.cmd.calls = []
    check("no Qt module is pulled in by the panel", "PySide6" not in sys.modules,
          [name for name in sys.modules if "PySide" in name])
    status = bridge.run_action("CoatLink_Setup")
    steps = [name for name, _args in coat.dialog_log]
    check("Setup opens 3D-Coat's own dialog", "show" in steps and "caption" in steps, coat.dialog_log)
    check("the panel is anchored in 3D-Coat's window", "topRight" in steps, coat.dialog_log)
    check("the panel carries the reduction controls",
          any(str(item).startswith("ReductionPercent,") for item in bridge.CoatLinkPanel().ui()),
          bridge.CoatLinkPanel().ui())
    check("Setup reports back", bool(status), status)

    # ---- the shader map: what each exported node carries ----
    # A sculpt shader is display shading, and 3D-Coat's own export writes no material
    # names at all, so the Blender half can only learn the assignment from a file we
    # leave beside the model.  Reading it means making each volume current in turn -
    # which must not leave someone else's selection behind.
    preset = os.path.join(bridge.user_data_dir(), "UserPrefs", "Shaders", "PbrShaders",
                          "#Metal", "Aluminum")
    os.makedirs(preset, exist_ok=True)
    with open(os.path.join(preset, "ShaderParams.xml"), "w", encoding="utf-8") as handle:
        handle.write(
            "<VoxShaderParams>\n"
            " <ExParams>\n"
            "  <ExShaderParam><Usage></Usage><ID>Color</ID><Type>float4</Type>"
            "<$Default>FFE1AE75</$Default></ExShaderParam>\n"
            "  <ExShaderParam><Usage></Usage><ID>Metalness</ID><Type>slider01</Type>"
            "<$Default>1.000000</$Default></ExShaderParam>\n"
            "  <ExShaderParam><Usage>USE_COLORTEX</Usage><ID>CustomSampler1</ID>"
            "<Type>texture</Type></ExShaderParam>\n"
            " </ExParams>\n"
            "</VoxShaderParams>\n")

    check("the preset's stored parameters are read back",
          bridge.shader_params("#Metal/Aluminum").get("Color") == "FFE1AE75"
          and bridge.shader_params("Aluminum").get("Metalness") == "1.000000",
          bridge.shader_params("#Metal/Aluminum"))
    check("a shader that paints its colour from a texture is flagged",
          bridge.shader_params("Aluminum").get("color_from_texture") is True,
          bridge.shader_params("Aluminum"))
    check("a shader with no preset brings no parameters", bridge.shader_params("Nope") == {},
          bridge.shader_params("Nope"))
    # Measured: 3D-Coat answers with the shader's place in its own library, and the last
    # part of that is the shader *file* inside the preset - so the part before it names the
    # preset, and a folder called after the file is never what is looked for.
    install = bridge.install_root()
    check("the installation's shader folder, when one is found, is a 3D-Coat one",
          install == "" or os.path.isdir(os.path.join(install, "UserPrefs", "Shaders")),
          install)
    # The same preset name can exist twice, and only the path says which one a volume is
    # using (measured: "PbrShaders/Gold2" and "PbrShaders/#Metal/Gold2" are different
    # presets with different stored values), so the path is tried exactly first.
    loose = os.path.join(bridge.user_data_dir(), "UserPrefs", "Shaders", "PbrShaders", "Aluminum")
    os.makedirs(loose, exist_ok=True)
    with open(os.path.join(loose, "ShaderParams.xml"), "w", encoding="utf-8") as handle:
        handle.write("<VoxShaderParams>\n <ExParams>\n"
                     "  <ExShaderParam><Usage></Usage><ID>Color</ID><Type>float4</Type>"
                     "<$Default>FF0000FF</$Default></ExShaderParam>\n"
                     " </ExParams>\n</VoxShaderParams>\n")
    check("a library path picks the preset it names, not another of that name",
          bridge.preset_folder("PbrShaders/Aluminum/mcubes") == loose
          and bridge.shader_params("PbrShaders/Aluminum/mcubes").get("Color") == "FF0000FF",
          (bridge.preset_folder("PbrShaders/Aluminum/mcubes"),
           bridge.shader_params("PbrShaders/Aluminum/mcubes")))
    check("a bare preset name still resolves when the name exists twice",
          bridge.preset_folder("Aluminum") != ""
          and bridge.shader_params("Aluminum").get("Metalness") == "1.000000",
          bridge.preset_folder("Aluminum"))

    cmd.volumes = {"Volume1": "#Metal/Aluminum", "Volume2": "NothingLikeThis"}
    cmd.current_volume = "Volume2"
    nodes = bridge.write_shader_map(own_root, ["Volume1", "Volume2"],
                                    bridge.model_path(own_root, "obj"))
    check("the map names the shader every node carries",
          nodes.get("Volume1", {}).get("shader") == "#Metal/Aluminum"
          and nodes.get("Volume2", {}).get("shader") == "NothingLikeThis", nodes)
    check("a node whose shader is not in the library keeps the name it came with",
          nodes.get("Volume2") == {"shader": "NothingLikeThis", "preset": "NothingLikeThis"},
          nodes.get("Volume2"))
    check("the map names the preset, and keeps two presets of one name apart",
          nodes.get("Volume1", {}).get("preset") == "Metal/Aluminum"
          and nodes.get("Volume2", {}).get("preset") == "NothingLikeThis", nodes)
    check("two presets of the same name get two names, never one shared material",
          bridge.shader_material_name(loose, "PbrShaders/Aluminum/mcubes") == "Aluminum"
          and bridge.shader_material_name(
              bridge.preset_folder("PbrShaders/#Metal/Aluminum/mcubes"),
              "PbrShaders/#Metal/Aluminum/mcubes") == "Metal/Aluminum",
          (bridge.shader_material_name(loose, "PbrShaders/Aluminum/mcubes"),
           bridge.preset_folder("PbrShaders/#Metal/Aluminum/mcubes")))
    check("reading each volume's shader puts the previous selection back",
          cmd.current_volume == "Volume2", cmd.current_volume)
    written = json.load(open(bridge.shader_map_path(own_root), encoding="utf-8"))
    check("the map sits beside the model and says which model it describes",
          written.get("model") == "bridge.obj" and sorted(written["nodes"]) == ["Volume1", "Volume2"],
          written)

    # nothing readable: the old map goes, so it can never describe a newer model
    cmd.volumes = {}
    bridge.write_shader_map(own_root, ["Volume1"], bridge.model_path(own_root, "obj"))
    check("a map that cannot be filled is removed instead of left stale",
          not os.path.isfile(bridge.shader_map_path(own_root)), bridge.shader_map_path(own_root))

    # a whole-scene send has no name list of its own: the exported file says what went out
    def obj_with_groups(path):
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("# exported by 3D-Coat\n"
                         "g Clay\nv 0 0 0\nf 1 1 1\n"
                         "g Metal\nv 1 1 1\nf 2 2 2\n")

    coat.applink_present = False
    coat.direct_export = obj_with_groups
    cmd.volumes = {"Clay": "NothingLikeThis", "Metal": "#Metal/Aluminum"}
    use_scope("scene")
    panel.SendToBlender()
    sent = json.load(open(bridge.shader_map_path(bridge.primary_root()), encoding="utf-8"))["nodes"]
    check("a whole-scene send reads the nodes out of the export itself",
          sorted(sent) == ["Clay", "Metal"], sent)
    check("and that send still reports normally", "Sent to Blender" in panel.status, panel.status)

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
