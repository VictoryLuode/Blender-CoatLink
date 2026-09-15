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
from fake_coat import FakeCoat, build_environment  # shared fake 3D-Coat API

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, "..", "CoatBridgeLib.py")
DIALOG_ENTRY = os.path.join(HERE, "..", "CoatBridgeDialog.py")

RESULTS = []


def check(name, condition, detail=""):
    RESULTS.append((name, bool(condition), detail))
    print("%-4s %s%s" % ("PASS" if condition else "FAIL", name, "" if condition else "   <- %s" % detail))


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

    runpy.run_path(DIALOG_ENTRY)
    steps = [name for name, _args in coat.dialog_log]
    check("panel is shown when run as a script", bool(steps) and steps[-1] == "show", steps)
    check("panel caption matches the Blender side",
          any(name == "caption" and args[0] == "Coat Bridge" for name, args in coat.dialog_log))
    check("panel is pinned to the top-right", "topRight" in steps and "noModal" in steps)
    check("panel width is set", any(name == "width" for name, _ in coat.dialog_log))
    check("panel has a close button",
          any(name == "buttons" and args[0] == "Close" for name, args in coat.dialog_log))
    check("panel drives its state each frame",
          any(name == "process" and callable(args[0]) for name, args in coat.dialog_log))

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

    # ---- send, AppLink route (3D-Coat exports and announces it itself) ----
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
          and "bridge.fbx" in open(bridge.signal_path(own_root)).read())
    check("send tells 3D-Coat which file to use",
          any(args and "bridge.fbx" in str(args[0]) for args in coat.ui.setFileForFileDialog.calls),
          coat.ui.setFileForFileDialog.calls)

    # ---- send, direct export fallback ----
    os.remove(bridge.signal_path(own_root))
    coat.applink_present = False

    def direct_export(path):
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("# exported directly\n")

    coat.direct_export = direct_export
    panel.SendToBlender()
    check("send falls back to the direct export", bool(cmd.calls) and cmd.calls[-1].endswith("bridge.fbx"), cmd.calls[-1:])
    check("send writes the signal Blender watches", os.path.isfile(bridge.signal_path(own_root)))
    check("send reports the file", "Sent to Blender" in panel.status and "bridge.fbx" in panel.status, panel.status)

    # ---- there is exactly one export format ----
    check("the panel keeps no format state", not hasattr(panel, "format"))
    check("3D-Coat hands back FBX", bridge.EXPORT_FORMAT == "fbx")

    # ---- panel layout mirrors the Blender menu ----
    items = panel.ui()
    plain = [item for item in items if not item.startswith(("[", "#", "---"))]
    for name in plain:
        if "," in name:
            name = name.split(",", 1)[0]
        check("layout item '%s' exists on the panel" % name, hasattr(panel, name))
    check("layout starts with a full-width button row", items[0] == "[1]")
    check("layout offers the same actions as Blender",
          {"SendToBlender", "PullFromBlender", "Detect", "OpenFolder", "StartBlender"} <=
          {item.split(",", 1)[0] for item in plain}, plain)
    check("the layout has no format control",
          not any(item.startswith("format,") for item in items), items)
    check("layout shows the status line", any(item.startswith("#") for item in items))
    check("layout tells the user how to reopen the panel",
          any(bridge.REOPEN_HINT in item for item in items), items)

    # ---- menu registration (main() already ran it on import) ----
    check("first run registers Scripts and Windows",
          coat.inserted[:2] == [("Scripts", "CoatBridge", ""), ("Windows", "CoatBridge", "")], coat.inserted)
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
