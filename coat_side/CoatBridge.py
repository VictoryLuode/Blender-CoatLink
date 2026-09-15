# SPDX-License-Identifier: GPL-3.0-or-later
#
# Coat Bridge - 3D-Coat side of the model bridge.  Copyright (C) 2026 VictoryLuode
#
# A non-modal panel pinned to the top-right of the 3D-Coat viewport, with the
# same layout and wording as the Blender add-on's menu:
#
#     Send to Blender      export this model into Blender's folder
#     Pull from Blender    import the model Blender sent
#     Format               what we hand to Blender (FBX / OBJ)
#     Detect               find the exchange folder and prepare the target
#     Folder               open the exchange folder
#     Start Blender        launch the newest Blender found on this machine
#     status box           last action, folder, queue state
#
# The exchange layout is the one the Blender add-on uses:
#
#     <root>/import.txt                  Blender's job file (we consume it)
#     <root>/BlenderBridge/bridge.<ext>  the model Blender sent
#     <root>/BlenderBridge/export.txt    what we write to hand a model back
#
# 3D-Coat registers more than one exchange root, so both are handled.

import os
import subprocess
import sys

import coat

try:
    import CMD
except ImportError:  # the command module is optional at import time
    CMD = None

APP_FOLDER = "BlenderBridge"
MODEL_NAME = "bridge"
PANEL_CAPTION = "Coat Bridge"
VERSION = "1.3.0"
FORMAT_ITEMS = ("FBX", "OBJ")
STATE_FILE = "CoatBridge.json"
RUN_MARKER = "run.txt"


# --------------------------------------------------------------------------
# exchange folders (same discovery rules as the Blender add-on)
# --------------------------------------------------------------------------

def documents_bases():
    home = os.path.expanduser("~")
    bases = [os.path.join(home, "Documents")]
    return [os.path.normpath(base) for base in bases]


def candidate_roots():
    roots = []
    for base in documents_bases():
        # 3D-Coat's own root: it writes its AppLink exports here
        roots.append(os.path.join(base, "3DCoat", "Exchange"))
        # the documented AppLink root: Blender writes its job file here
        roots.append(os.path.join(base, "AppLinks", "3D-Coat", "Exchange"))
    return [os.path.normpath(root) for root in roots]


def exchange_roots():
    """Existing roots, 3D-Coat's own first."""
    return [root for root in candidate_roots() if os.path.isdir(root)]


def primary_root():
    roots = exchange_roots()
    return roots[0] if roots else ""


def app_folder(root):
    return os.path.join(root, APP_FOLDER)


def import_txt(root):
    return os.path.join(root, "import.txt")


def signal_path(root):
    return os.path.join(app_folder(root), "export.txt")


def model_path(root, extension):
    return os.path.join(app_folder(root), "%s.%s" % (MODEL_NAME, extension.lower().lstrip(".")))


def ensure_folder(root):
    folder = app_folder(root)
    os.makedirs(folder, exist_ok=True)
    marker = os.path.join(folder, RUN_MARKER)
    if not os.path.isfile(marker):
        with open(marker, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("")  # empty on purpose: only makes the folder an AppLink target
    return folder


def read_import_model(root):
    """The model Blender queued in <root>/import.txt, if it is still there."""
    path = import_txt(root)
    if not os.path.isfile(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            first = handle.readline().strip().strip('"')
    except OSError:
        return ""
    if not first or first.startswith("["):
        return ""
    return os.path.normpath(first)


def consume_import(root, model):
    """Drop Blender's job file once we imported it ourselves, so 3D-Coat's own
    AppLink poller does not import the same model a second time."""
    path = import_txt(root)
    if not os.path.isfile(path) or os.path.normcase(read_import_model(root)) != os.path.normcase(model):
        return False
    try:
        os.remove(path)
    except OSError:
        return False
    return True


def write_signal(root, model):
    folder = ensure_folder(root)
    with open(signal_path(root), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(os.path.abspath(model) + "\n")
    return signal_path(root)


def sent_models(root):
    """Models sitting in our folder, newest first."""
    folder = app_folder(root)
    if not os.path.isdir(folder):
        return []
    found = []
    for name in os.listdir(folder):
        if not name.lower().startswith(MODEL_NAME.lower() + "."):
            continue
        path = os.path.join(folder, name)
        found.append((os.path.getmtime(path), path))
    return [path for _mtime, path in sorted(found, reverse=True)]


# --------------------------------------------------------------------------
# settings (plain json next to the 3D-Coat user data, no coat API needed)
# --------------------------------------------------------------------------

def state_path():
    base = documents_bases()[0]
    return os.path.join(base, "3DCoat", STATE_FILE)


def load_state():
    try:
        import json

        with open(state_path(), "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_state(data):
    try:
        import json

        os.makedirs(os.path.dirname(state_path()), exist_ok=True)
        with open(state_path(), "w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, indent=2)
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------
# the panel
# --------------------------------------------------------------------------

class CoatBridgePanel(object):
    """State object for the dialog: attributes become controls, the ui() list
    is the layout, methods whose names appear in that list become buttons."""

    def __init__(self):
        state = load_state()
        self.format = state.get("format", "FBX")
        if self.format not in FORMAT_ITEMS:
            self.format = "FBX"
        self.status = "Ready"
        self.detail = ""
        self.refresh_detail()
        self._previous_format = self.format

    # ---- layout -----------------------------------------------------------

    def ui(self):
        items = []
        items.append("[1]")
        items.append("SendToBlender")
        items.append("PullFromBlender")
        items.append("---")
        items.append("format,[%s]" % "|".join(FORMAT_ITEMS))
        items.append("---")
        items.append("[1 1 1]")
        items.append("Detect")
        items.append("OpenFolder")
        items.append("StartBlender")
        items.append("---")
        items.append("#" + self.status)
        if self.detail:
            items.append("##" + self.detail)
        return items

    def process(self):
        """Called every frame while the panel is open."""
        if self.format != self._previous_format:
            save_state({"format": self.format})
            self._previous_format = self.format
            self.refresh_detail()
        return False

    def refresh_detail(self):
        root = primary_root()
        if not root:
            self.detail = "exchange folder not found - press Detect"
            return
        queued = read_import_model(root)
        parts = ["Folder: " + os.path.basename(root)]
        parts.append("waiting: " + os.path.basename(queued) if queued else "waiting: nothing")
        self.detail = " | ".join(parts)

    # ---- actions ----------------------------------------------------------

    def SendToBlender(self):
        """Export the current model into our folder and hand Blender the path."""
        root = primary_root()
        if not root:
            self._report("exchange folder not found - press Detect", "")
            return
        if not ensure_folder(root):
            self._report("could not create the BlenderBridge folder", "")
            return

        path = model_path(root, self.format.lower())
        signal = signal_path(root)
        for _attempt in range(2):
            if os.path.isfile(signal):
                try:
                    os.remove(signal)  # never report a stale export as this one
                except OSError:
                    pass

        exported = self._export_via_applink(path)
        if exported:
            self._report("Sent to Blender via the AppLink target", "folder: %s" % app_folder(root))
            return
        exported = self._export_direct(path)
        if exported:
            write_signal(root, path)
            self._report("Sent to Blender: %s" % os.path.basename(path), "folder: %s" % app_folder(root))
            return
        self._report("Export failed", "use File > Export To > %s, or check the console" % APP_FOLDER)

    def PullFromBlender(self):
        """Import the model Blender sent to us: the queue file wins, so we take
        exactly what Blender asked for rather than whatever is newest."""
        roots = exchange_roots()
        queued = [(root, read_import_model(root)) for root in roots]
        queued = [(root, model) for root, model in queued if model and os.path.isfile(model)]

        candidates = queued
        if not candidates:
            newest = []
            for root in roots:
                for path in sent_models(root):
                    newest.append((root, path))
            candidates = sorted(newest, key=lambda item: os.path.getmtime(item[1]), reverse=True)[:1]

        if not candidates:
            self._report("Nothing to pull", "send a model from Blender first")
            return

        root, model = candidates[0]
        try:
            element = coat.Scene.importMesh(model)
        except Exception as exc:
            self._report("Import failed: %s" % exc, os.path.basename(model))
            return
        consumed = consume_import(root, model)
        name = _element_name(element) or os.path.basename(model)
        self._report("Pulled %s from %s" % (name, os.path.basename(model)),
                     "queue file consumed" if consumed else "queue file left alone")

    def Detect(self):
        root = primary_root()
        if not root:
            self._report("no exchange folder found", "start 3D-Coat once so it creates it")
            return
        folder = ensure_folder(root)
        self._report("Target ready: %s" % APP_FOLDER, folder)
        self.refresh_detail()

    def OpenFolder(self):
        root = primary_root()
        if not root:
            self._report("no exchange folder found", "")
            return
        folder = app_folder(root)
        os.makedirs(folder, exist_ok=True)
        try:
            if hasattr(os, "startfile"):
                os.startfile(folder)
            else:
                subprocess.Popen(["xdg-open", folder] if sys.platform != "darwin" else ["open", folder])
            self._report("Opened the exchange folder", folder)
        except Exception as exc:
            self._report("Could not open the folder: %s" % exc, folder)

    def StartBlender(self):
        exe = find_blender_executable()
        if not exe:
            self._report("Blender not found", "install Blender or start it manually")
            return
        try:
            subprocess.Popen([exe], cwd=os.path.dirname(exe))
            self._report("Started Blender", exe)
        except Exception as exc:
            self._report("Could not start Blender: %s" % exc, exe)

    # ---- internals --------------------------------------------------------

    def _export_via_applink(self, path):
        """Let 3D-Coat's own AppLink target do the export: it writes the model
        and its own export.txt, which is exactly what Blender waits for."""
        target = "$" + APP_FOLDER
        try:
            if not coat.ui.presentInUI(target):
                return False
        except Exception:
            return False
        try:
            coat.ui.setFileForFileDialog(path)
            coat.ui.cmd(target, lambda: coat.ui.cmd("$DialogButton#1"))
            coat.io.step(4)
        except Exception:
            return False
        return os.path.isfile(signal_path(primary_root()))

    def _export_direct(self, path):
        if CMD is None:
            return False
        try:
            CMD.ExportObjectsAndTextures(path)
            coat.io.step(4)
        except Exception:
            return False
        return os.path.isfile(path)

    def _report(self, status, detail):
        self.status = status
        self.detail = detail
        try:
            coat.ui.showInfoMessage(status, 2500)
        except Exception:
            pass


def _element_name(element):
    for attribute in ("name",):
        method = getattr(element, attribute, None)
        if callable(method):
            try:
                return str(method())
            except Exception:
                return ""
    return ""


def find_blender_executable():
    """Newest stable Blender on this machine, using 3D-Coat's own index when it
    has one."""
    folders = []
    try:
        folders = list(coat.io.listBlenderInstallFolders())
    except Exception:
        folders = []
    candidates = []
    for folder in folders:
        if os.path.isfile(folder) and folder.lower().endswith(".exe"):
            candidates.append(folder)
            continue
        for name in ("blender.exe", "blender"):
            path = os.path.join(folder, name)
            if os.path.isfile(path):
                candidates.append(path)
    return sorted(candidates)[-1] if candidates else ""


# --------------------------------------------------------------------------
# entry point: register in the Scripts menu once, then show the panel
# --------------------------------------------------------------------------

def register_menu_item():
    """Idempotent: the menu entry points back at this script.

    The label comes from the translation table, so the item shows up as
    "Coat Bridge" whether it was added here or by the shipped XML.
    """
    try:
        coat.ui.addTranslation("CoatBridge", PANEL_CAPTION)
        if coat.ui.checkIfMenuItemInserted("CoatBridge"):
            return False
        coat.ui.insertInMenu("Scripts", "CoatBridge", "")
        return True
    except Exception:
        return False


def show_panel():
    panel = CoatBridgePanel()
    coat.dialog() \
        .caption(PANEL_CAPTION) \
        .noModal() \
        .topRight() \
        .width(320) \
        .buttons("Close") \
        .params(panel) \
        .process(panel.process) \
        .show()
    save_state({"format": panel.format})


def main():
    register_menu_item()
    show_panel()


main()
