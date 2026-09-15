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

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "CoatBridge.py")

RESULTS = []


def check(name, condition, detail=""):
    RESULTS.append((name, bool(condition), detail))
    print("%-4s %s%s" % ("PASS" if condition else "FAIL", name, "" if condition else "   <- %s" % detail))


class Recorder(object):
    def __init__(self, name):
        self.name = name
        self.calls = []

    def __call__(self, *args, **kwargs):
        self.calls.append(args)
        return self.return_value(*args, **kwargs) if hasattr(self, "return_value") else None


class FakeDialog(object):
    """Chainable recorder for coat.dialog().caption(...).topRight()...show()."""

    def __init__(self, log):
        self.log = log

    def _step(self, name, *args):
        self.log.append((name, args))
        return self

    def caption(self, text):
        return self._step("caption", text)

    def noModal(self):
        return self._step("noModal")

    def topRight(self):
        return self._step("topRight")

    def width(self, value):
        return self._step("width", value)

    def buttons(self, text):
        return self._step("buttons", text)

    def params(self, value):
        return self._step("params", value)

    def process(self, callback):
        return self._step("process", callback)

    def onPress(self, callback):
        return self._step("onPress", callback)

    def show(self):
        return self._step("show")


class FakeCoat(object):
    def __init__(self):
        self.dialog_log = []
        self.ui = types.SimpleNamespace()
        self.io = types.SimpleNamespace()
        self.scene_imports = []
        self.state_file = ""
        self.applink_present = False
        self.applink_export = None       # callable(root) simulating 3D-Coat's own export
        self.direct_export = None        # callable(path) simulating CMD export
        self.messages = []
        self.menu_inserted = False
        self.inserted = []

        self.ui.cmd = Recorder("ui.cmd")
        self.ui.setFileForFileDialog = Recorder("ui.setFileForFileDialog")
        self.ui.showInfoMessage = lambda text, ms: self.messages.append(text)
        self.ui.checkIfMenuItemInserted = lambda menu_id: self.menu_inserted
        self.ui.addTranslation = Recorder("ui.addTranslation")
        self.ui.insertInMenu = lambda menu, menu_id, path: self.inserted.append((menu, menu_id, path))
        self.ui.presentInUI = lambda target: self.applink_present

        self.io.step = lambda frames: None
        self.io.listBlenderInstallFolders = lambda: []

        def _import_mesh(path):
            self.scene_imports.append(path)
            return types.SimpleNamespace(name=lambda: os.path.splitext(os.path.basename(path))[0])

        # coat.Scene.importMesh(...) - an attribute, exactly like the API
        self.Scene = types.SimpleNamespace(importMesh=_import_mesh)

    def dialog(self):
        return FakeDialog(self.dialog_log)


def build_environment(tmp):
    """Redirect ~ to the temp tree and install the fake modules."""
    real_expanduser = os.path.expanduser

    def fake_expanduser(path):
        return tmp if path == "~" else real_expanduser(path)

    os.path.expanduser = fake_expanduser

    coat = FakeCoat()
    sys.modules["coat"] = coat
    cmd = types.ModuleType("CMD")
    cmd.calls = []

    def export_objects_and_textures(path):
        cmd.calls.append(path)
        if coat.direct_export:
            coat.direct_export(path)

    cmd.ExportObjectsAndTextures = export_objects_and_textures
    sys.modules["CMD"] = cmd
    return coat, cmd


def import_script():
    spec = importlib.util.spec_from_file_location("coat_bridge_3dcoat", SCRIPT)
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

    # ---- the script ran on import like 3D-Coat would run it ----
    steps = [name for name, _args in coat.dialog_log]
    check("panel is shown on import", steps[-1] == "show", steps)
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
    panel.format = "FBX"
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
    panel.format = "OBJ"
    panel.SendToBlender()
    check("send falls back to the direct export", cmd.calls and cmd.calls[-1].endswith("bridge.obj"), cmd.calls[-1:])
    check("send writes the signal Blender watches", os.path.isfile(bridge.signal_path(own_root)))
    check("send reports the file", "Sent to Blender" in panel.status and "bridge.obj" in panel.status, panel.status)

    # ---- format persistence ----
    panel.format = "FBX"
    panel.process()
    check("the format setting is stored", bridge.load_state().get("format") == "FBX", bridge.load_state())

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
    check("layout exposes the format droplist", "format,[FBX|OBJ]" in items, items)
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
