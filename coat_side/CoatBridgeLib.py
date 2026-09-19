# SPDX-License-Identifier: GPL-3.0-or-later
#
# CoatLink - 3D-Coat side of the model bridge.  Copyright (C) 2026 VictoryLuode
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
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import CoatBridgeReceipts as receipts

try:
    import CoatBridgeScopedExport as scoped_export
except ImportError:  # older install without the helper
    scoped_export = None
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
PANEL_CAPTION = "CoatLink"
VERSION = "1.4.0"
#: the format 3D-Coat hands back.  Its own AppLink export uses FBX anyway, so
#: there is nothing to choose - Blender reads the returned file by extension.
#: The model 3D-Coat hands back.  OBJ both ways on purpose: the axis rule then
#: applies to both directions identically.  (An FBX carries its own up-axis
#: declaration, an OBJ does not, so mixing the two formats meant the two
#: directions could never be made to agree.)
EXPORT_FORMAT = "obj"

#: 3D-Coat's own decimation slider.  This is the id the shipped scripts use -
#: UserPrefs/Scripts/mm_export.as and CoreAPI/Templates/CoreAPI_Export/
#: auto_export.cpp both do SetSliderValue("$DecimationParams::ReductionPercent", n)
#: while the export dialog is up, then press "$DialogButton#1" (OK).
#: The value is the percentage of triangles to KEEP (0 = no reduction).
REDUCTION_SLIDER = "$DecimationParams::ReductionPercent"
REDUCTION_KEY = "reduction"

#: what a Send hands over: the node selected in the sculpt tree (and its
#: children), or 3D-Coat's own export, which does the whole scene
SEND_SCOPE_KEY = "send_scope"
SEND_SCOPES = ("selected", "scene")
SEND_SCOPE_LABELS = "#selected node|#whole scene"

#: the export dialog's "export textures" checkbox (documented as an import.txt
#: option listed in applinks.rst, settable with the CMD module's SetBoolField)
TEXTURES_FIELD = "$ExportOpt::ExportTextures"
TEXTURES_KEY = "textures"

#: the panel's native droplist: index -> stored value
TEXTURES_CHOICES = (None, True, False)
STATE_FILE = "CoatBridge.json"
RUN_MARKER = "run.txt"
MENU_ID = "CoatBridge"
MENU_PATHS = ("Scripts", "Windows")  # launcher lives with the other script/window entries
TOOL_ROOMS = ("Voxels",)             # rooms whose tool panel gets a CoatLink button
REOPEN_HINT = "reopen: Scripts > CoatLink"

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
        if os.path.splitext(name)[1].lower() not in (".obj", ".fbx", ".ply", ".stl"):
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


def log_text(limit=200):
    """The tail of the log: used by the tests, and by me when diagnosing from
    outside 3D-Coat."""
    try:
        with open(log_path(), "r", encoding="utf-8", errors="replace") as handle:
            return "\n".join(handle.read().splitlines()[-limit:])
    except OSError:
        return ""


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


def reduction_percent():
    """The percentage the panel slider holds (0 = no reduction)."""
    try:
        value = int(load_state().get(REDUCTION_KEY, 0))
    except (TypeError, ValueError):
        return 0
    return max(0, min(100, value))


def flatten_imported_group(element):
    """Move an imported file's children up to the sculpt root and drop the wrapper.

    3D-Coat wraps an imported file in a node named after it (bridge.obj ->
    "bridge"); Blender has no such node, so the sculpt tree stops matching the
    outliner.  Only that wrapper is removed - the imported objects are moved, never
    deleted, and nothing else in the tree is touched.  Returns the names moved.
    """
    try:
        root = coat.Scene.sculptRoot()
    except Exception as exc:
        log("could not read the sculpt root: %s" % exc)
        return []
    group = element
    try:
        if group is None or group.childCount() == 0:
            group = element.parent() if element is not None else None
    except Exception:
        group = None
    if group is None or group is root:
        return []
    moved = []
    # always take the first child and append it: that keeps the order Blender has,
    # and the live index cannot skip one (the group shrinks as they leave it)
    while True:
        try:
            if group.childCount() == 0:
                break
            child = group.child(0)
        except Exception:
            break
        if child is None:
            break
        # the index 3D-Coat wants for "append" is not documented: try both and let
        # parent() say whether it worked
        reached = False
        for target_index in (-1, root.childCount()):
            try:
                child.moveTo(root, target_index)
            except Exception:
                continue
            try:
                reached = child.parent() is root
            except Exception:
                reached = True
            if reached:
                break
        if not reached:
            log("could not unparent %s" % (_element_name(child) or "?"))
            break
        moved.append(_element_name(child) or "?")
    try:
        if group.childCount() == 0:
            group.remove()
    except Exception:
        pass
    if moved:
        log("unparented %s from the import group" % ", ".join(moved))
    return moved


def send_scope():
    """Which part of the scene Send hands over - "selected" unless changed."""
    value = str(load_state().get(SEND_SCOPE_KEY, "selected")).lower()
    return value if value in SEND_SCOPES else "selected"


def set_send_scope(value):
    if value not in SEND_SCOPES:
        return False
    return save_state({SEND_SCOPE_KEY: value})


def reduction_note():
    """What to say when a Send carried a reduction request (nothing when it did not).

    The selected-node export applies the percentage itself, so unlike the dialog
    route there is no other place the number can show up.
    """
    percent = reduction_percent()
    return " (reduction requested %d%% (unverified))" % percent if percent > 0 else ""


def set_reduction_percent(value):
    try:
        value = max(0, min(100, int(value)))
    except (TypeError, ValueError):
        return False
    return save_state({REDUCTION_KEY: value})


def export_note():
    """What the status line reports about the export settings ("" when nothing
    is set, so a plain export looks exactly like before)."""
    bits = []
    percent = reduction_percent()
    if percent > 0:
        bits.append("reduction requested %d%% (unverified)" % percent)
    textures = export_textures()
    if textures is not None:
        bits.append("textures %s" % ("on" if textures else "off"))
    return " (%s)" % ", ".join(bits) if bits else ""



def capture_reduction():
    """Read the percentage 3D-Coat's export dialog is showing and remember it.

    Used the first time (and whenever the stored value is cleared): the user sets
    it once in 3D-Coat's own dialog, we keep it and apply it automatically from
    then on - so the dialog never has to be filled in twice.
    """
    if CMD is None:
        return "reduction: no CMD api in this build"
    try:
        raw = float(CMD.GetSliderValue(REDUCTION_SLIDER))
    except Exception as exc:
        return "could not read the reduction slider: %s" % exc
    percent = int(round(raw))
    if percent <= 0 or percent > 100:
        return "reduction read as %s - nothing stored" % raw
    set_reduction_percent(percent)
    return "remembered reduction %d%% from 3D-Coat" % percent


def export_textures():
    """True / False when the panel has decided, None while 3D-Coat decides.

    Stored as "auto" / "on" / "off" so "3D-Coat decides" is a real third state
    (a plain bool cannot express it).
    """
    value = load_state().get(TEXTURES_KEY, "auto")
    if isinstance(value, bool):
        return value
    return {"on": True, "off": False}.get(str(value).lower())


def set_export_textures(value):
    stored = "auto" if value is None else ("on" if value else "off")
    return save_state({TEXTURES_KEY: stored})


def apply_textures():
    """Push the texture switch into 3D-Coat's export dialog.  "" when unset."""
    value = export_textures()
    if value is None:
        return ""
    if CMD is None:
        return "textures: no CMD api in this build"
    try:
        CMD.SetBoolField(TEXTURES_FIELD, bool(value))
    except Exception as exc:
        return "textures %s failed: %s" % (value, exc)
    return "textures %s" % ("on" if value else "off")


def apply_reduction(percent=None):
    """Push the percentage into 3D-Coat's own decimation slider.

    Called while 3D-Coat's export dialog is up (see _export_via_applink), which is
    what the shipped scripts do.  Returns a note for the log; "" when nothing was
    asked for, and an explanation when the API refused, so a silent no-op can
    never look like success.
    """
    try:
        percent = reduction_percent() if percent is None else int(percent)
    except (TypeError, ValueError):
        return "reduction: bad value"
    if percent <= 0:
        return ""
    if CMD is None:
        return "reduction %d%%: no CMD api in this build" % percent
    try:
        CMD.SetSliderValue(REDUCTION_SLIDER, float(percent))
    except Exception as exc:
        return "reduction %d%% failed: %s" % (percent, exc)
    try:
        got = CMD.GetSliderValue(REDUCTION_SLIDER)
    except Exception:
        return "reduction %d%% set" % percent
    return "reduction %d%% set (slider reads %s)" % (percent, got)


# --------------------------------------------------------------------------
# headless actions, for the tool-panel buttons (no UI at all)
# --------------------------------------------------------------------------

#: tool id -> label shown in the room tool panel (and in the hotkey editor)
ACTION_LABELS = {
    "CoatBridge_Send": ("SendToBlender", "Send to Blender"),
    "CoatBridge_Pull": ("PullFromBlender", "Pull from Blender"),
    "CoatBridge_Setup": ("OpenPanel", "CoatLink: panel"),
}


def scene_scale_note():
    """3D-Coat's export scale and unit name.

    Scene.GetSceneScale() is documented as "the length of 1 scene unit when you
    export the scene", which is exactly the factor that makes a model come home at
    a different size - so it goes into the log on every action.
    """
    try:
        return "3D-Coat units=%s scale=%s" % (coat.Scene.GetSceneUnits(), coat.Scene.GetSceneScale())
    except Exception as exc:
        return "3D-Coat scale unknown (%s)" % exc


def current_size():
    """(x, y, z, units) of the element 3D-Coat has current, or None."""
    try:
        box = coat.Scene.current().Volume().calcWorldSpaceAABB()
        return (float(box.GetSizeX()), float(box.GetSizeY()), float(box.GetSizeZ()),
                str(coat.Scene.GetSceneUnits() or ""))
    except Exception as exc:
        log("size: could not measure the current object (%s)" % exc)
        return None


def size_line():
    """The panel's size readout."""
    measured = current_size()
    if not measured:
        return "Size: no object selected"
    x, y, z, units = measured
    return "Size: %.3f x %.3f x %.3f %s" % (x, y, z, units)


def scale_to_size(target, only_if_larger=False):
    """Scale the current element so its longest side measures `target`.

    Everything happens inside 3D-Coat (mat4.ScalingAt about the object's own
    centre, applied with transform_single), so nothing is exported, re-imported
    or otherwise round-tripped to change a size.
    """
    try:
        target = float(target)
    except (TypeError, ValueError):
        return "target size is not a number"
    if target <= 0:
        return "target size must be above zero"
    measured = current_size()
    if not measured:
        return "select something in 3D-Coat first"
    largest = max(measured[:3])
    if largest <= 0:
        return "the current object has no measurable size"
    if only_if_larger and largest >= target:
        return "already %.3f (target %.3f, left alone)" % (largest, target)
    factor = target / largest
    try:
        element = coat.Scene.current()
        box = element.Volume().calcWorldSpaceAABB()
        element.transform_single(coat.mat4.ScalingAt(box.GetCenter(), factor))
    except Exception as exc:
        return "scaling failed: %s" % exc
    log("size: longest side %.4f -> %.4f (x%.4f)" % (largest, target, factor))
    return "Size %.3f -> %.3f (x%.4f)" % (largest, target, factor)


def coat_settings_info():
    """3D-Coat's own size and axis settings, written into the state file so the
    Blender side can match them without anyone typing numbers.

    Scene.GetSceneScale() is documented as "the length of 1 scene unit when you
    export the scene", and 3D-Coat's export option ApplyMeasurementScale applies
    exactly that factor to hand out natural units - so a model coming in from
    Blender looks small by that factor until the sender multiplies by it.
    SwapYZ is 3D-Coat's "swap the Y and Z scene axes" option (for Z-up
    applications such as Rhino or 3ds Max).
    """
    info = {}
    readers = (
        ("scene_scale", lambda: float(coat.Scene.GetSceneScale())),
        ("scene_units", lambda: str(coat.Scene.GetSceneUnits())),
        ("swap_yz", lambda: bool(coat.settings.getBool("SwapYZ"))),
    )
    for key, reader in readers:
        try:
            info[key] = reader()
        except Exception as exc:
            info[key] = None
            log("coat settings: could not read %s (%s)" % (key, exc))
    save_state({"coat": info})
    log("coat settings: scale=%s units=%s swap Y/Z=%s" % (info.get("scene_scale"),
                                                          info.get("scene_units"),
                                                          info.get("swap_yz")))
    return info


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
    coat_settings_info()          # also logs 3D-Coat's scale/units/axis
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
        self.status = "Ready"
        self.detail = ""
        # native controls: "Name,[min,max]" is a number field bound to the
        # attribute, "Name,[#A|#B]" a droplist.  This is the layout syntax
        # 3D-Coat's own Autoexport example panel uses.
        self.ReductionPercent = reduction_percent()
        self.Textures = TEXTURES_CHOICES.index(export_textures())
        self.SendScope = SEND_SCOPES.index(send_scope())
        self.SizeLabel = "Size: -"
        self.Advanced = False
        self._saved_controls = (self.ReductionPercent, self.Textures, self.SendScope)
        self.refresh_detail()

    # ---- layout -----------------------------------------------------------

    def ui(self):
        self.process()  # cached controls only; no scene access
        items = []
        items.append("SendScope,[%s]" % SEND_SCOPE_LABELS)
        items.append("[1]")
        items.append("SendToBlender")
        items.append("PullFromBlender")
        items.append("---")
        items.append("#" + self.SizeLabel)
        items.append("ReductionPercent,[0,100]")
        items.append("RefreshStats")
        items.append("##" + getattr(self, "StatsLabel", "Statistics paused; click RefreshStats"))
        items.append("##Reduction % = removed; estimate only, export not verified")
        items.append("Textures,[#from 3D-Coat|#textures on|#textures off]")
        items.append("---")
        items.append("Advanced")
        if self.Advanced:
            items.append("[1 1]")
            items.append("Detect")
            items.append("OpenFolder")
            items.append("[1 1]")
            items.append("StartBlender")
            items.append("RemoveLauncher")
        items.append("---")
        items.append("#" + self.status)
        if self.Advanced and self.detail:
            items.append("##" + self.detail)
        items.append("##" + REOPEN_HINT)
        return items

    def process(self):
        """No host queries or disk reads per frame. Persist actual edits only."""
        current = (self.ReductionPercent, self.Textures, self.SendScope)
        if current == self._saved_controls:
            return False
        values = {REDUCTION_KEY: max(0, min(100, int(self.ReductionPercent)))}
        scope = int(self.SendScope)
        if 0 <= scope < len(SEND_SCOPES):
            values[SEND_SCOPE_KEY] = SEND_SCOPES[scope]
        choice = int(self.Textures)
        if 0 <= choice < len(TEXTURES_CHOICES):
            value = TEXTURES_CHOICES[choice]
            values[TEXTURES_KEY] = "auto" if value is None else ("on" if value else "off")
        if save_state(values):
            self._saved_controls = current
        return False

    def RefreshStats(self):
        """Explicit user action only: never inspect live mesh during redraw."""
        self.SizeLabel = size_line()
        try:
            count = int(coat.Scene.current().Volume().getPolycount())
            self.StatsLabel = "Snapshot: %d faces (not auto-refreshed)" % count
        except Exception as exc:
            self.StatsLabel = "Statistics unavailable: %s" % exc

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
        coat_settings_info()
        root = primary_root()
        if not root:
            self._report("exchange folder not found - press Detect", "")
            return
        if not ensure_folder(root):
            self._report("could not create the BlenderBridge folder", "")
            return

        path = model_path(root, EXPORT_FORMAT)
        signal = signal_path(root)
        for _attempt in range(2):
            if os.path.isfile(signal):
                try:
                    os.remove(signal)  # never report a stale export as this one
                except OSError:
                    pass

        if send_scope() == "selected":
            self._export_selected(root, path)
            return

        exported = self._export_via_applink(path)
        if exported:
            self._report("Sent to Blender via the AppLink target (whole scene)" + export_note(),
                         "folder: %s" % app_folder(root))
            return
        exported = self._export_direct(path)
        if exported:
            write_signal(root, path)
            self._report("Sent to Blender: %s (whole scene)%s" % (os.path.basename(path), export_note()),
                         "folder: %s" % app_folder(root))
            return
        self._report("Export failed", "use File > Export To > %s, or check the console" % APP_FOLDER)

    def _export_selected(self, root, path):
        """Send the node selected in the sculpt tree, plus its children.

        Scene.current() is documented as "the current sculpt object", and the mesh
        extraction takes with_subtree / all_selected explicitly, so nothing else in
        the scene can leave by accident.  There is deliberately no fallback to the
        whole-scene export: a bridge that quietly sends more than you selected is
        worse than one that tells you to select a node.
        """
        if scoped_export is None:
            self._report("Export helper missing", "reinstall the 3D-Coat scripts")
            return
        try:
            names, faces = scoped_export.export_subtree(coat, path, reduction_percent())
        except Exception as exc:
            self._report("Nothing sent: %s" % exc, "select a node in the Sculpt Tree")
            log("selected-node export refused: %s" % exc)
            return
        write_signal(root, path)
        self._report("Sent %s: %s (selected node + subtree)%s"
                     % (os.path.basename(path), ", ".join(names), reduction_note()),
                     "%d faces | folder: %s" % (faces, app_folder(root)))

    def PullFromBlender(self):
        """Import the model Blender sent to us: the queue file wins, so we take
        exactly what Blender asked for rather than whatever is newest."""
        coat_settings_info()
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
            receipt_version = receipts.fingerprint(model)
            element = coat.Scene.importMesh(model)
        except Exception as exc:
            self._report("Import failed: %s" % exc, os.path.basename(model))
            return
        unparented = flatten_imported_group(element)
        consumed = consume_import(root, model)
        name = _element_name(element) or os.path.basename(model)
        if element is not None:
            receipts.acknowledge(model, "3dcoat", receipt_version, [name])
        note = "%s | %s" % ("queue file consumed" if consumed else "queue file left alone",
                            "unparented %d object(s)" % len(unparented) if unparented
                            else "no import group to unparent")
        self._report("Pulled %s from %s" % (name, os.path.basename(model)), note)

    def OpenPanel(self):
        """Open the panel: 3D-Coat's own dialog, nothing Qt."""
        panel = show_panel(force=True)
        if panel is None:
            self._report("could not open the panel", REOPEN_HINT)
            return
        self._report(panel.status, REOPEN_HINT)

    def ApplySize(self):
        """Scale the current object so its longest side is the target size."""
        self._report(scale_to_size(self.TargetSize), "")

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
                     "run this script again (Scripts > CoatLink) to put it back")

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
        applied = [""]

        def _confirm():
            # 3D-Coat's export dialog is up.  A stored percentage is pushed into
            # 3D-Coat's own decimation slider and OK is pressed without the user
            # ever seeing it - the first time around (nothing stored) we read the
            # value the dialog is showing and remember it instead.
            applied[0] = " | ".join(
                part for part in (apply_reduction() if reduction_percent() > 0 else capture_reduction(),
                                  apply_textures()) if part)
            coat.ui.cmd("$DialogButton#1")

        try:
            if reduction_percent() > 0:
                apply_reduction()  # covers the skip-dialog path too
            apply_textures()
            coat.ui.setFileForFileDialog(path)
            coat.ui.cmd(target, _confirm)
            coat.io.step(4)
        except Exception:
            return False
        if applied[0]:
            log("export settings: %s" % applied[0])
        return os.path.isfile(signal_path(primary_root()))

    def _export_direct(self, path):
        if CMD is None:
            return False
        try:
            notes = [part for part in (apply_reduction(), apply_textures()) if part]
            if notes:
                log("export settings: %s" % " | ".join(notes))
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
    """Put a CoatLink button into the tool panel of the listed rooms.

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
    """The panel closed (button 1 = Close): nothing to keep but the menu record."""
    try:
        save_state({"menus": load_state().get("menus", [])})
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
    coat.dialog() \
        .caption(PANEL_CAPTION) \
        .noModal() \
        .topRight() \
        .width(320) \
        .buttons("Close") \
        .params(panel) \
        .onPress(_on_press) \
        .show()
    _on_press(1)
    return panel


def main():
    register_menu_item()
    register_room_tools()
    show_panel()
