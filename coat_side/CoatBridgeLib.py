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
import time

import coat

try:
    import CMD
except ImportError:  # the command module is optional at import time
    CMD = None

APP_FOLDER = "BlenderBridge"
MODEL_NAME = "bridge"
PANEL_CAPTION = "Coat Bridge"
VERSION = "1.4.0"
FORMAT_ITEMS = ("FBX", "OBJ")
STATE_FILE = "CoatBridge.json"
RUN_MARKER = "run.txt"
MENU_ID = "CoatBridge"
MENU_PATHS = ("Scripts", "Windows")  # launcher lives with the other script/window entries
TOOL_ROOMS = ("Voxels",)             # rooms whose tool panel gets a Coat Bridge button
REOPEN_HINT = "reopen: Scripts > Coat Bridge"

#: timestamp of the last time the panel was opened, so a double click cannot
#: stack two panels (and a stale value never blocks a later reopen)
_LAST_OPEN = [0.0]


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

def log_path():
    """A small append-only log next to the 3D-Coat user data, so a silent
    failure inside 3D-Coat can be diagnosed from outside."""
    return os.path.join(documents_bases()[0], "3DCoat", "CoatBridge.log")


def log(message):
    try:
        LINES = 400
        path = log_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                lines = handle.read().splitlines()
            if len(lines) > LINES:
                with open(path, "w", encoding="utf-8", newline="\n") as handle:
                    handle.write("\n".join(lines[-LINES // 2:]) + "\n")
        with open(path, "a", encoding="utf-8", newline="\n") as handle:
            handle.write("%s | %s\n" % (time.strftime("%H:%M:%S"), message))
        return True
    except Exception:
        return False


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
    """Merge into the state file: the panel, the close handler and the menu
    registration all write different keys and must not wipe each other."""
    try:
        import json

        merged = load_state()
        merged.update(data)
        os.makedirs(os.path.dirname(state_path()), exist_ok=True)
        with open(state_path(), "w", encoding="utf-8", newline="\n") as handle:
            json.dump(merged, handle, indent=2)
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------
# headless actions, for the tool-panel buttons (no UI at all)
# --------------------------------------------------------------------------

#: tool id -> label shown in the room tool panel (and in the hotkey editor)
ACTION_LABELS = {
    "CoatBridge_Send": ("SendToBlender", "Send to Blender"),
    "CoatBridge_Pull": ("PullFromBlender", "Pull from Blender"),
    "CoatBridge_Setup": ("Detect", "Coat Bridge: setup"),
}


def add_translations():
    """Give the tool buttons readable labels.  3D-Coat shows the raw id until a
    translation exists, so every action calls this when it runs."""
    for tool_id, (_method, label) in ACTION_LABELS.items():
        try:
            coat.ui.addTranslation(tool_id, label)
        except Exception:
            pass


def run_action(tool_id):
    """Run one bridge action headless and report the outcome with 3D-Coat's own
    floating message - no window, no dialog."""
    method, label = ACTION_LABELS.get(tool_id, ("", tool_id))
    add_translations()
    panel = CoatBridgePanel()
    action = getattr(panel, method, None)
    if action is None:
        return "unknown action: %s" % tool_id
    log("tool %s -> %s" % (tool_id, label))
    try:
        action()
    except Exception as exc:
        panel.status = "%s failed: %s" % (label, exc)
        log(panel.status)
    try:
        coat.ui.showInfoMessage(panel.status, 3000)
    except Exception:
        pass
    return panel.status


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
        items.append("[1 1]")
        items.append("Detect")
        items.append("OpenFolder")
        items.append("[1 1]")
        items.append("StartBlender")
        items.append("RemoveLauncher")
        items.append("---")
        items.append("#" + self.status)
        if self.detail:
            items.append("##" + self.detail)
        items.append("##" + REOPEN_HINT)
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

    def RemoveLauncher(self):
        """Take the injected menu entries and tool buttons back out again."""
        try:
            coat.ui.removeCommandFromMenu(MENU_ID)
        except Exception as exc:
            self._report("Could not remove the launcher: %s" % exc, "")
            return
        state = load_state()
        state["menus"] = []
        state["tools"] = []
        save_state(state)
        self._report("Launcher removed",
                     "run this script again (Scripts > Coat Bridge) to put it back")

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
        log(status + (" | " + detail if detail else ""))
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
    """Make sure the launcher exists, and report which menus were added to.

    Scripts is usually already covered by the shipped XML; Windows is added
    here so the panel also sits with the other window entries.  The list of
    menus already handled is kept in the state file, because
    checkIfMenuItemInserted() cannot tell one menu from another.
    """
    state = load_state()
    done = list(state.get("menus", []))
    added = []
    try:
        coat.ui.addTranslation(MENU_ID, PANEL_CAPTION)
    except Exception:
        pass
    for path in MENU_PATHS:
        if path in done:
            continue
        if path == "Scripts" and _menu_present(MENU_ID):
            done.append(path)  # the shipped XML already provides it
            continue
        try:
            coat.ui.insertInMenu(path, MENU_ID, "")
            done.append(path)
            added.append(path)
        except Exception:
            pass
    if done != state.get("menus", []):
        state["menus"] = sorted(set(done))
        save_state(state)
    return added


def register_room_tools():
    """Put a Coat Bridge button into the tool panel of the listed rooms.

    The tool appears at the end of the room's tool list; the id doubles as the
    icon name (data/Textures/icons64/<id>.png) and gets its label from the
    translation added in register_menu_item().
    """
    state = load_state()
    done = list(state.get("tools", []))
    added = []
    for room in TOOL_ROOMS:
        if room in done:
            continue
        try:
            coat.ui.insertInToolset(room, "", MENU_ID)
            done.append(room)
            added.append(room)
        except Exception:
            pass
    if done != state.get("tools", []):
        state["tools"] = sorted(set(done))
        save_state(state)
    return added


def _menu_present(menu_id):
    try:
        return bool(coat.ui.checkIfMenuItemInserted(menu_id))
    except Exception:
        return False


def _on_press(button):
    """The panel closed (button 1 = Close): remember the format for next time."""
    try:
        save_state({"format": _LAST_FORMAT[0], "menus": load_state().get("menus", [])})
    except Exception:
        pass


def show_panel(force=False):
    """Open the panel.  A second click within a couple of seconds is ignored so
    a double click cannot stack two panels; a stale marker never blocks."""
    import time

    now = time.time()
    if not force and now - _LAST_OPEN[0] < 3.0:
        return None
    _LAST_OPEN[0] = now

    panel = CoatBridgePanel()
    _LAST_FORMAT[0] = panel.format
    coat.dialog() \
        .caption(PANEL_CAPTION) \
        .noModal() \
        .topRight() \
        .width(320) \
        .buttons("Close") \
        .params(panel) \
        .process(panel.process) \
        .onPress(_on_press) \
        .show()
    _on_press(1)
    return panel


#: the format the panel is currently showing, so the close handler can save it
_LAST_FORMAT = ["FBX"]


def main():
    register_menu_item()
    register_room_tools()
    show_panel()
