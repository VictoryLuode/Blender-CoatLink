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


class CmdRecorder(Recorder):
    """ui.cmd(command, callback): 3D-Coat runs the callback when the dialog that
    command opened is up, so the fake runs it too - the tests then really
    exercise the code that fills the dialog in."""

    def __call__(self, *args, **kwargs):
        self.calls.append(args)
        for arg in args:
            if callable(arg):
                arg()
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


#: marks "the fake decides" for `current_element`, so a test can set it to None to
#: mean "nothing is selected in the sculpt tree"
UNSET = object()


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

        self.ui.cmd = CmdRecorder("ui.cmd")
        self.ui.setFileForFileDialog = Recorder("ui.setFileForFileDialog")
        self.ui.showInfoMessage = lambda text, ms: self.messages.append(text)
        self.ui.checkIfMenuItemInserted = lambda menu_id: self.menu_inserted
        self.ui.addTranslation = Recorder("ui.addTranslation")
        self.ui.insertInMenu = lambda menu, menu_id, path: self.inserted.append((menu, menu_id, path))
        self.ui.insertInToolset = Recorder("ui.insertInToolset")
        self.ui.removeCommandFromMenu = Recorder("ui.removeCommandFromMenu")
        self.ui.presentInUI = lambda target: self.applink_present

        self.settings = types.SimpleNamespace()
        self.settings_values = {"SwapYZ": True}

        def get_bool(name):
            if name not in self.settings_values:
                raise KeyError(name)
            return self.settings_values[name]

        self.settings.getBool = get_bool
        self.io.step = lambda frames: None
        self.io.listBlenderInstallFolders = lambda: []

        self.root = TreeNode("Root", self)
        self.moves = []
        self.removed = []
        #: name of the wrapper node an import creates ("bridge" for bridge.obj)
        self.import_group_name = None

        def _import_mesh(path):
            """Import like 3D-Coat does: a group named after the file, holding the
            objects, and the first object is what the call returns."""
            self.scene_imports.append(path)
            stem = os.path.splitext(os.path.basename(path))[0]
            group = TreeNode(self.import_group_name or stem, self, self.root)
            child = TreeNode("Volume1", self, group)
            return child

        # coat.Scene.importMesh(...) - an attribute, exactly like the API
        self.current_size = [2.0, 1.0, 0.5]     # what 3D-Coat measures
        self.transforms = []

        class _Box(object):
            def __init__(self, size):
                self.size = size

            def GetSizeX(self):
                return self.size[0]

            def GetSizeY(self):
                return self.size[1]

            def GetSizeZ(self):
                return self.size[2]

            def GetCenter(self):
                return types.SimpleNamespace(x=0.0, y=0.0, z=0.0)

        class _Volume(object):
            def __init__(self, size):
                self.size = size
                self.polycount = 1000

            def calcWorldSpaceAABB(self):
                return _Box(self.size)

            def getPolycount(self):
                return int(self.polycount)

        self.polycount = 1000

        class _Mesh(object):
            """coat.Mesh(): what the selected-node export pulls out of the tree.

            Records how it was asked (subtree / all-selected / reduction) and writes
            a real little OBJ, so the exporter's own validation runs on real lines.
            """

            def __init__(self):
                self.calls = []
                self.names = ["Volume1"]
                self.faces = 12
                self.written = None

            def fromVolume(self, volume, with_subtree=False, all_selected=False):
                self.calls.append(("fromVolume", bool(with_subtree), bool(all_selected)))
                return self

            def fromReducedVolume(self, volume, reduction_percent,
                                  with_subtree=False, all_selected=False):
                self.calls.append(("fromReducedVolume", float(reduction_percent),
                                   bool(with_subtree), bool(all_selected)))
                return self

            def valid(self):
                return self.faces > 0

            def facesCount(self):
                return self.faces

            def getObjectsCount(self):
                return len(self.names)

            def getObjectName(self, index):
                return self.names[index]

            def Write(self, path):
                self.written = path
                body = "".join("g %s\n" % name for name in self.names)
                body += "v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n"
                with open(path, "w", encoding="utf-8", newline="\n") as handle:
                    handle.write(body)
                return True

        self.meshes = []
        #: what the next coat.Mesh() should look like: {"names": [...], "faces": n,
        #: "write": callable}.  Tests set this instead of guessing at an instance.
        self.mesh_template = None

        def _new_mesh():
            mesh = _Mesh()
            template = self.mesh_template or {}
            if "names" in template:
                mesh.names = list(template["names"])
            if "faces" in template:
                mesh.faces = template["faces"]
            if "write" in template:
                mesh.Write = template["write"]
            self.meshes.append(mesh)
            return mesh

        self.Mesh = _new_mesh
        self.current_element = UNSET

        class _Element(object):
            def __init__(self, fake):
                self.fake = fake

            def Volume(self):
                return _Volume(self.fake.current_size)

            def transform_single(self, matrix):
                self.fake.transforms.append(matrix)

        self.Scene = types.SimpleNamespace(importMesh=_import_mesh,
                                           GetSceneUnits=lambda: "m",
                                           GetSceneScale=lambda: 1.0,
                                           sculptRoot=lambda: self.root,
                                           current=lambda: _Element(self)
                                           if self.current_element is UNSET
                                           else self.current_element)

    def dialog(self):
        return FakeDialog(self.dialog_log)


class TreeNode(object):
    """A node of 3D-Coat's sculpt tree, with the parts the bridge uses.

    Real 3D-Coat wraps an imported file in a node named after it; tests build that
    shape here and then check what the bridge does to it.
    """

    def __init__(self, name, fake, parent=None):
        self._name = name
        self.fake = fake
        self.parent_node = parent
        self.children = []
        if parent is not None:
            parent.children.append(self)

    def name(self):
        return self._name

    def childCount(self):
        return len(self.children)

    def child(self, index):
        if 0 <= index < len(self.children):
            return self.children[index]
        return None

    def parent(self):
        return self.parent_node

    def moveTo(self, new_parent, index):
        if new_parent is None:
            raise RuntimeError("no parent")
        if self.parent_node is not None and self in self.parent_node.children:
            self.parent_node.children.remove(self)
        if index is None or index < 0 or index > len(new_parent.children):
            new_parent.children.append(self)
        else:
            new_parent.children.insert(index, self)
        self.parent_node = new_parent
        self.fake.moves.append((self._name, new_parent.name(), index))

    def remove(self):
        if self.parent_node is not None and self in self.parent_node.children:
            self.parent_node.children.remove(self)
        self.fake.removed.append(self._name)

    # a node can also be the "current object" the panel reads
    def Volume(self):
        return _Volume(self.fake.current_size)

    def transform_single(self, matrix):
        self.fake.transforms.append(matrix)


class FakeMat4(object):
    """Records how the bridge asked 3D-Coat to scale something."""

    def ScalingAt(self, origin, factor):
        return ("ScalingAt", origin, factor)


def build_environment(tmp):
    """Redirect ~ to the temp tree and install the fake modules."""
    real_expanduser = os.path.expanduser

    def fake_expanduser(path):
        return tmp if path == "~" else real_expanduser(path)

    os.path.expanduser = fake_expanduser
    # Windows' own answer for Documents cannot be faked - it is a registry call -
    # so the override every door and both halves honour stands in for it.
    os.environ["COATLINK_DOCS"] = os.path.join(tmp, "Documents")

    coat = FakeCoat()
    coat.mat4 = FakeMat4()
    sys.modules["coat"] = coat
    cmd = types.ModuleType("CMD")
    cmd.calls = []

    def export_objects_and_textures(path):
        cmd.calls.append(path)
        if coat.direct_export:
            coat.direct_export(path)

    cmd.ExportObjectsAndTextures = export_objects_and_textures

    # 3D-Coat's dialog slider api: only ids 3D-Coat actually has accept a value,
    # so a wrong id can never look like success in a test.
    cmd.sliders = {}
    cmd.known_sliders = {"$DecimationParams::ReductionPercent"}

    def set_slider_value(name, value):
        cmd.calls.append(("slider", name, value))
        if name not in cmd.known_sliders:
            return False
        cmd.sliders[name] = float(value)
        return True

    cmd.SetSliderValue = set_slider_value
    cmd.GetSliderValue = lambda name: cmd.sliders.get(name, 0.0)

    cmd.bools = {"$ExportOpt::ExportTextures": True}

    def set_bool_field(name, value):
        cmd.calls.append(("bool", name, value))
        if name not in cmd.bools:
            return False
        cmd.bools[name] = bool(value)
        return True

    cmd.SetBoolField = set_bool_field
    cmd.GetBoolField = lambda name: cmd.bools.get(name)

    # 3D-Coat's volume/shader api: only a name that really is a volume accepts being
    # made current, so a wrong name can never look like a successful read in a test
    cmd.volumes = {}
    cmd.current_volume = ""

    def set_cur_volume(name):
        cmd.calls.append(("volume", name))
        if name not in cmd.volumes:
            return False
        cmd.current_volume = name
        return True

    cmd.SetCurVolume = set_cur_volume
    cmd.GetCurVolume = lambda: cmd.current_volume
    cmd.GetCurVolumeShader = lambda: cmd.volumes.get(cmd.current_volume, "")
    sys.modules["CMD"] = cmd
    return coat, cmd


def make_exchange_tree(tmp):
    """A throwaway pair of exchange roots, like 3D-Coat registers."""
    own_root = os.path.join(tmp, "Documents", "3DCoat", "Exchange")
    job_root = os.path.join(tmp, "Documents", "AppLinks", "3D-Coat", "Exchange")
    os.makedirs(own_root, exist_ok=True)
    os.makedirs(job_root, exist_ok=True)
    return own_root, job_root
