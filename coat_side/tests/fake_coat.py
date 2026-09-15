# SPDX-License-Identifier: GPL-3.0-or-later
"""Fake 3D-Coat API used by the 3D-Coat side tests.

`coat` and `CMD` are replaced with recorders, and the home directory is pointed
at a throwaway tree, so the scripts can be imported and driven exactly the way
3D-Coat would - without 3D-Coat.
"""

import os
import sys
import types


class Recorder(object):
    def __init__(self, name):
        self.name = name
        self.calls = []

    def __call__(self, *args, **kwargs):
        self.calls.append(args)
        if hasattr(self, "return_value"):
            return self.return_value(*args, **kwargs)
        return None


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
        self.ui.insertInToolset = Recorder("ui.insertInToolset")
        self.ui.removeCommandFromMenu = Recorder("ui.removeCommandFromMenu")
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


def make_exchange_tree(tmp):
    """A throwaway pair of exchange roots, like 3D-Coat registers."""
    own_root = os.path.join(tmp, "Documents", "3DCoat", "Exchange")
    job_root = os.path.join(tmp, "Documents", "AppLinks", "3D-Coat", "Exchange")
    os.makedirs(own_root, exist_ok=True)
    os.makedirs(job_root, exist_ok=True)
    return own_root, job_root
