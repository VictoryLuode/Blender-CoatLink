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
#     <root>/CoatLinkBridge/bridge.<ext>  the model Blender sent
#     <root>/CoatLinkBridge/export.txt    what we write to hand a model back
#
# 3D-Coat registers more than one exchange root, so both are handled.

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import CoatLinkReceipts as receipts

try:
    import CoatLinkScopedExport as scoped_export
except ImportError:  # older install without the helper
    scoped_export = None
import json
import re
import subprocess
import sys
import time
import textwrap

import coat

try:
    import CMD
except ImportError:  # the command module is optional at import time
    CMD = None

APP_FOLDER = "CoatLinkBridge"
#: what the export target was called before the rename.  3D-Coat lists a target
#: from the run.txt marker inside its folder, so the old name only leaves
#: File > Export To once that marker is gone - see retire_legacy_app_folders().
LEGACY_APP_FOLDERS = ("CoatLink",)
MODEL_NAME = "bridge"
PANEL_CAPTION = "CoatLink"
#: the format 3D-Coat hands back.  Its own AppLink export uses FBX anyway, so
#: there is nothing to choose - Blender reads the returned file by extension.
#: The model 3D-Coat hands back.  OBJ both ways on purpose: the axis rule then
#: applies to both directions identically.  (An FBX carries its own up-axis
#: declaration, an OBJ does not, so mixing the two formats meant the two
#: directions could never be made to agree.)
EXPORT_FORMAT = "obj"

#: What the Blender half reads to give every arriving object the material of the
#: shader it was sent with.  A sculpt shader is 3D-Coat's *display* shading and its
#: exporters write no material names at all (measured: "usemtl " with nothing after
#: it, "newmtl " likewise), so the assignment can only travel beside the model.
#: 3D-Coat writes its own side files as .txt/.xml, so the name is ours.  The Blender
#: half carries the same constant.
SHADER_MAP_NAME = "shaders.json"
#: Where the PBR shader presets live, under the user data folder.  A preset that
#: cannot be found costs the parameters, never the assignment.
SHADER_PRESET_PARTS = ("UserPrefs", "Shaders", "PbrShaders")

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
SEND_SCOPE_LABELS = "#Selected|#Whole scene"
#: what each scope actually hands over - the two are not the same thing, and 3D-Coat
#: decides for itself what its own export covers, so the panel says so
SEND_SCOPE_HINTS = ("the node selected in the Sculpt Tree, plus its children",
                    "3D-Coat's own export (all volumes, its own rules)")

#: the export dialog's "export textures" checkbox (documented as an import.txt
#: option listed in applinks.rst, settable with the CMD module's SetBoolField)
TEXTURES_FIELD = "$ExportOpt::ExportTextures"
TEXTURES_KEY = "textures"

#: the panel's native droplist: index -> stored value.  Off comes first because that is
#: what this bridge is for - models - so the texture files 3D-Coat's own exporter would
#: write stay out of the exchange folder.  Turning them on is a decision, not a default.
TEXTURES_CHOICES = (False, True)
TEXTURES_LABELS = "#textures off|#textures on"

#: The S/V badge in a sculpt-tree row.  Its own tooltip reads "Press this button to
#: transform surface to voxel representation", so pressing it is 3D-Coat doing the
#: conversion itself - the same thing the user does by hand, and the one they report
#: as more accurate than the Volume.toVoxels() API.  The id carries the object name.
VOXEL_TOGGLE_ID = "$VoxTreeBranch.VoxSurf.%s"

#: how many times to look at the object after pressing the badge before concluding
#: the press did nothing (3D-Coat carries the conversion out over a few frames)
VOXEL_TOGGLE_POLLS = 3
STATE_FILE = "CoatLink.json"
RUN_MARKER = "run.txt"
MENU_ID = "CoatLink"
MENU_PATHS = ("Scripts",)  # one entry point, as everywhere else in this project
TOOL_ROOMS = ("Voxels", "Paint")      # rooms whose tool panel gets the CoatLink buttons
#: one tool button per room per action, in this order; the file names double as the
#: button ids and as the scripts the XML points at
TOOL_ACTIONS = ("CoatLink_Send", "CoatLink_Pull", "CoatLink_Setup")
REOPEN_HINT = "reopen: Scripts > CoatLink"

#: timestamp of the last time the panel was opened, so a double click cannot
#: stack two panels (and a stale value never blocks a later reopen)
_LAST_OPEN = [0.0]


# --------------------------------------------------------------------------
# exchange folders (same discovery rules as the Blender add-on)
# --------------------------------------------------------------------------

def data_folder_of(start):
    """The 3D-Coat data folder that holds ``start``, or "".

    ``…/Documents/3DCoat/UserPrefs/Scripts/CoatLink`` -> ``…/Documents/3DCoat``,
    and the 4.x layout (``…/3D-CoatV48/Scripts/…``) lands on ``…/3D-CoatV48`` the same
    way: the folder is the one carrying 3D-Coat's own name.
    """
    folder = os.path.abspath(start)
    for _ in range(8):
        name = os.path.basename(folder).lower()
        if name.startswith("3dcoat") or name.startswith("3d-coat"):
            return folder
        parent = os.path.dirname(folder)
        if parent == folder:     # reached the drive root
            break
        folder = parent
    return ""


def script_user_data():
    """The 3D-Coat data folder this script itself lives in, or "".

    The installer puts these scripts in ``<user data>/UserPrefs/Scripts/CoatLink``,
    so the folder is *known* rather than guessed: walking up from ``__file__`` finds
    ``UserPrefs`` (2021 and later) or ``Scripts`` (the 4.x layout).  The folder it
    returns is 3D-Coat's *data* folder - ``…/Documents/3DCoat``, one level above
    ``UserPrefs`` - because that is where the Blender half, the installer and the
    after-import helper all put ``CoatLink.log`` and ``CoatLink.json``.  Returning
    ``UserPrefs`` instead split one trip's evidence into two files: the panel could never see
    the other half's lines, and the Blender side read a stale ``CoatLink.json`` for
    its axis and units.  That matters
    because ``~/Documents`` and 3D-Coat's own folders are not the same place once
    Documents is redirected (OneDrive) or ``COAT_FILES_PATH`` is set - and guessing
    wrong there is what makes the panel say "no exchange folder found" on a machine
    where everything is installed correctly.  The folder name also carries the
    version on some builds (``3DCoat2025``), which a hard-coded ``3DCoat`` misses.
    """
    folder = os.path.dirname(os.path.abspath(__file__))
    return data_folder_of(folder)


def windows_documents():
    """Windows' own answer for the Documents folder, or "" (non-Windows, failure).

    The same call the Blender half makes, so both halves agree on a redirected
    machine instead of one asking Windows and the other assuming ``~/Documents``.
    ``COATLINK_DOCS`` names the folder outright - the same override the installer's
    doors honour, and what the test suite uses to stand in for another machine.
    """
    override = os.environ.get("COATLINK_DOCS")
    if override:
        return override
    if os.name != "nt":
        return ""
    try:
        import ctypes

        buffer = ctypes.create_unicode_buffer(1024)
        # CSIDL_PERSONAL = 5
        if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buffer) == 0:
            return buffer.value
    except Exception:
        return ""
    return ""


def documents_bases():
    """Candidate Documents folders, the one this script lives in first."""
    bases = []
    data = script_user_data()
    if data:
        bases.append(os.path.dirname(data))
    shell = windows_documents()
    if shell:
        bases.append(shell)
    bases.append(os.path.join(os.path.expanduser("~"), "Documents"))
    seen = set()
    unique = []
    for base in bases:
        base = os.path.normpath(base)
        key = os.path.normcase(base)
        if base and key not in seen:
            seen.add(key)
            unique.append(base)
    return unique


def user_data_dir():
    """3D-Coat's user data folder (``…/Documents/3DCoat`` and friends).

    What the script found by looking at itself comes first; ``~/Documents/3DCoat``
    is only the guess to fall back on when that failed (the script was started from
    somewhere else, or copied out of its folder).
    """
    data = script_user_data()
    if data:
        return data
    for base in documents_bases():
        for name in os.listdir(base) if os.path.isdir(base) else []:
            if name.lower() in ("3dcoat", "3d-coatv48", "3d-coatv49"):
                return os.path.join(base, name)
    return os.path.join(documents_bases()[0], "3DCoat")


def candidate_roots():
    roots = []
    for base in documents_bases():
        # the shared root: 3D-Coat's engine polls its job file here, so both
        # sides read and write here and a return lands on the file the send
        # wrote.  Measured live: the engine never picks a job up from the
        # other root, so this one has to lead.
        roots.append(os.path.join(base, "AppLinks", "3D-Coat", "Exchange"))
    # 3D-Coat's own root: watched for anything an older session left behind
    roots.append(os.path.join(user_data_dir(), "Exchange"))
    return [os.path.normpath(root) for root in roots]


def exchange_roots():
    """Existing roots, the shared one first."""
    return [root for root in candidate_roots() if os.path.isdir(root)]


def primary_root():
    roots = exchange_roots()
    return roots[0] if roots else ""


def app_folder(root):
    return os.path.join(root, APP_FOLDER)


def app_folder_names():
    """Every folder name of ours, the current one first."""
    return (APP_FOLDER,) + LEGACY_APP_FOLDERS


def retire_legacy_app_folders(root):
    """Take the old target name off 3D-Coat's File > Export To menu.

    The entry comes from the run.txt marker inside the folder, so deleting the
    marker is what retires a name; the folder and its files stay put, where the
    export.txt naming a returned model still points.
    """
    done = []
    for name in LEGACY_APP_FOLDERS:
        folder = os.path.join(root, name)
        marker = os.path.join(folder, RUN_MARKER)
        if not os.path.isfile(marker):
            continue
        try:
            os.remove(marker)
        except OSError as exc:
            log("could not retire the old export target %s (%s)" % (folder, exc))
            continue
        done.append(folder)
        log("retired the old export target %s: its %s marker is gone" % (folder, RUN_MARKER))
    return done


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
    retire_legacy_app_folders(root)   # publishing the new name retires the old one
    return folder


def is_our_model(root, path):
    """Does this model sit inside one of our folders under ``root``?

    The job file is the one file both AppLinks share, so a job has to be claimed by
    what it points at rather than by the file it arrived in.  The pre-rename folder
    counts as ours: a job queued before the rename is still ours to import.
    """
    folder = os.path.normcase(os.path.normpath(os.path.dirname(os.path.abspath(path))))
    for name in app_folder_names():
        if folder == os.path.normcase(os.path.normpath(os.path.join(root, name))):
            return True
    return False


def read_import_model(root):
    """The model Blender queued in <root>/import.txt, if it is ours and still there.

    Only a job naming a model inside our own ``CoatLink`` folder counts.  The
    official Blender AppLink writes its jobs into the very same ``import.txt``
    (measured in its own source: first line the model, third line ``[3B]``), so a
    path that is not ours belongs to that add-on - importing it here, and deleting
    the file afterwards the way ``consume_import`` does, would steal its job.
    """
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
    model = os.path.normpath(first)
    if not is_our_model(root, model):
        log("import.txt names a model outside our own folder - left for its own AppLink: %s" % model)
        return ""
    return model


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
# the shader map: which shader each exported node carries
# --------------------------------------------------------------------------

def shader_map_path(root):
    return os.path.join(app_folder(root), SHADER_MAP_NAME)


def model_nodes(path):
    """The object groups an OBJ holds, in file order; [] when it is not an OBJ.

    The scoped export knows the names it wrote; this is for 3D-Coat's own whole-scene
    export, where the only record of what went out is the file itself.
    """
    if not path or not path.lower().endswith(".obj") or not os.path.isfile(path):
        return []
    names = []
    try:
        with open(path, encoding="utf-8", errors="replace") as stream:
            for line in stream:
                if line.startswith(("o ", "g ")):
                    label = line[2:].strip()
                    if label and label not in names:
                        names.append(label)
    except OSError as exc:
        log("could not read the exported model's node names: %s" % exc)
    return names


def volume_shaders(names):
    """{node name: shader name}, read from 3D-Coat itself.

    CMD.GetCurVolumeShader reads the *current* volume, so each name is made current
    in turn and the previous selection is put back afterwards: a send must not leave
    a different node selected than it found.  Nothing here raises - a build without
    these commands, or a name that is no longer a volume, costs that node's shader
    and nothing else.
    """
    found = {}
    if CMD is None or not names:
        return found
    try:
        previous = CMD.GetCurVolume()
    except Exception:
        previous = ""
    try:
        for name in names:
            try:
                if not CMD.SetCurVolume(name):
                    log("shader map: no volume named %s" % name)
                    continue
                shader = (CMD.GetCurVolumeShader() or "").strip()
            except Exception as exc:
                log("shader map: shader of %s unreadable: %s" % (name, exc))
                continue
            if shader:
                found[name] = shader
    finally:
        if previous:
            try:
                CMD.SetCurVolume(previous)
            except Exception:
                pass
    return found


def shader_preset_root():
    """Where the PBR shader presets are: 3D-Coat's own user data folder.

    These scripts only ever run inside a 3D-Coat that has already created that folder,
    so this is the copy the running 3D-Coat reads its shaders from.  A preset that is
    not found costs the parameters, never the assignment.
    """
    return os.path.join(user_data_dir(), *SHADER_PRESET_PARTS)


def preset_folder(shader):
    """The preset folder a shader name points at, or "".

    What GetCurVolumeShader returns is undocumented, so one tolerant match covers a
    bare name ("Aluminum"), a category-qualified one ("#Metal/Aluminum" or
    "Metal/Aluminum") and a full folder path.
    """
    wanted = (shader or "").replace("\\", "/").strip("/")
    root = shader_preset_root()
    if not wanted or not os.path.isdir(root):
        return ""
    tail = wanted.rsplit("/", 1)[-1]
    for category in sorted(os.listdir(root)):
        folder = os.path.join(root, category)
        if not os.path.isdir(folder):
            continue
        for preset in sorted(os.listdir(folder)):
            path = os.path.join(folder, preset)
            if not os.path.isdir(path):
                continue
            if preset == tail or any("%s/%s" % (name, preset) in (wanted, tail)
                                     for name in (category, category.lstrip("#"))):
                return path
    return ""


def shader_params(shader):
    """The stored parameters of a preset: {ID: value}; {} when it is not found.

    These are the values the preset *ships* with: 3D-Coat's per-volume sliders are not
    readable from outside (CMD offers SetShaderProperty and no getter), so a value
    dragged in 3D-Coat cannot be read back.  Colour is stored as 8 hex digits, alpha
    first (A R G B), and a preset whose colour comes from a texture is flagged - there
    the stored colour is an unused fallback, which the Blender half has to know before
    it puts it on a material.
    """
    folder = preset_folder(shader)
    path = os.path.join(folder, "ShaderParams.xml") if folder else ""
    if not path or not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            text = handle.read()
    except OSError as exc:
        log("shader preset unreadable (%s): %s" % (shader, exc))
        return {}
    params = {}
    textured_colour = False
    for block in re.findall(r"<ExShaderParam>(.*?)</ExShaderParam>", text, re.S):
        fields = dict(re.findall(r"<(ID|Type|Usage|\$Default)>(.*?)</\1>", block, re.S))
        ident = fields.get("ID", "").strip()
        kind = fields.get("Type", "").strip()
        if not ident:
            continue
        if kind in ("texture", "method"):
            if ident == "CustomSampler1" and "USE_COLORTEX" in fields.get("Usage", ""):
                textured_colour = True
            continue
        value = fields.get("$Default", "").strip()
        if value:
            params[ident] = value
    if textured_colour:
        params["color_from_texture"] = True
    return params


def remove_shader_map(root):
    """Drop the map: no export is waiting for it any more."""
    path = shader_map_path(root)
    try:
        if os.path.isfile(path):
            os.remove(path)
            return True
    except OSError as exc:
        log("shader map not removable: %s" % exc)
    return False


def write_shader_map(root, names=None, model=""):
    """Record which shader each exported node carries, beside the model.

    Written after every export and *removed* when nothing could be read, so a stale
    map can never describe a newer model.  Never raises: refusing to send a model
    because a shader could not be read would be worse than having no map at all.
    """
    if names is None:
        names = model_nodes(model)
    names = [name for name in (names or []) if name]
    found = volume_shaders(names)
    if not found:
        remove_shader_map(root)
        log("shader map: nothing recorded (%d node(s) checked)" % len(names))
        return {}
    nodes = {}
    for name in names:
        shader = found.get(name)
        if not shader:
            continue
        entry = {"shader": shader}
        entry.update(shader_params(shader))
        nodes[name] = entry
    data = {"generated": time.strftime("%Y-%m-%d %H:%M:%S"),
            "model": os.path.basename(model or model_path(root, EXPORT_FORMAT)),
            "nodes": nodes}
    path = shader_map_path(root)
    temporary = path + ".tmp"
    try:
        ensure_folder(root)
        with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, indent=1, sort_keys=True)
        os.replace(temporary, path)
    except OSError as exc:
        log("shader map not written: %s" % exc)
        if os.path.exists(temporary):
            try:
                os.remove(temporary)
            except OSError:
                pass
        return {}
    log("shader map: %d of %d node(s): %s"
        % (len(nodes), len(names),
           ", ".join("%s=%s" % (name, nodes[name]["shader"]) for name in sorted(nodes)[:6])))
    return nodes


# --------------------------------------------------------------------------
# settings (plain json next to the 3D-Coat user data, no coat API needed)
# --------------------------------------------------------------------------

def log_path():
    """A small append-only log next to the 3D-Coat user data, so a silent
    failure inside 3D-Coat can be diagnosed from outside."""
    return os.path.join(user_data_dir(), "CoatLink.log")


def log_text(limit=200):
    """The tail of the log: used by the tests, and by me when diagnosing from
    outside 3D-Coat."""
    try:
        with open(log_path(), "r", encoding="utf-8", errors="replace") as handle:
            return "\n".join(handle.read().splitlines()[-limit:])
    except OSError:
        return ""


def log(message, exc=False):
    if exc:
        try:
            import traceback
            traceback.print_exc()
        except Exception:
            pass
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
            # the same three-field shape the Blender half and the after-import helper
            # write, so one file can be read by all three and a line can be told apart
            # by who wrote it
            handle.write("%s | 3dcoat | %s\n" % (time.strftime("%H:%M:%S"), message))
        return True
    except Exception:
        return False


def state_path():
    return os.path.join(user_data_dir(), STATE_FILE)


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
    """True / False as the panel decided.  Off unless someone turned it on.

    There used to be a third state - "auto", leaving it to 3D-Coat's own export
    dialog.  A stored "auto" reads as off now: that is what it meant for anyone who
    left the setting alone, and this bridge carries models, so textures have to be
    asked for rather than quietly appearing in the exchange folder.
    """
    value = load_state().get(TEXTURES_KEY, "off")
    if isinstance(value, bool):
        return value
    if str(value).lower() == "auto":
        return False
    return {"on": True, "off": False}.get(str(value).lower(), False)


def set_export_textures(value):
    return save_state({TEXTURES_KEY: "on" if value else "off"})


def apply_textures():
    """Push the texture switch into 3D-Coat's export dialog."""
    value = export_textures()
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
#: what the panel's buttons say (the tool-strip buttons use ACTION_LABELS instead)
PANEL_ACTION_LABELS = {"SendToBlender": "Send", "PullFromBlender": "Pull"}

#: 3D-Coat labels a panel control by its own name unless that name is translated, so
#: without this the panel reads "SendScope", "ReductionPercent", "RefreshStats" - the
#: words the code uses, not words a person uses.  The wording matches the Blender menu
#: wherever the two mean the same thing.
PANEL_LABELS = {
    "SendScope": "Scope",
    "ReductionPercent": "Reduction percent",
    "Textures": "Textures",
    "RefreshStats": "Refresh info",
    "CopyDetails": "Copy details",
    "Detect": "Detect",
    "OpenFolder": "Open folder",
    "StartBlender": "Start Blender",
    "RemoveLauncher": "Remove tool buttons",
    "VoxelizeVisible": "To voxels",
}

ACTION_LABELS = {
    "CoatLink_Send": ("SendToBlender", "Send to Blender"),
    "CoatLink_Pull": ("PullFromBlender", "Pull from Blender"),
    "CoatLink_Setup": ("OpenPanel", "CoatLink: panel"),
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
    for name, label in PANEL_LABELS.items():
        try:
            coat.ui.addTranslation(name, label)
        except Exception:
            pass  # a missing translation is cosmetic; never break registration
    for tool_id, (_method, label) in ACTION_LABELS.items():
        try:
            coat.ui.addTranslation(tool_id, label)
        except Exception:
            pass
        # the panel's own buttons are methods, and 3D-Coat labels them by name
        # unless they are translated: "Send" / "Pull", the same words the Blender
        # menu uses.  The tool-strip buttons keep the longer labels above, because
        # there they stand on their own.
        try:
            coat.ui.addTranslation(_method, PANEL_ACTION_LABELS.get(_method, label))
        except Exception:
            pass


def ensure_launcher():
    """Make sure the menu entry and the tool buttons are in place.

    ``CoatLinkMenu`` writes both files and clears out what older builds left
    behind (its docstring has the reasoning).  This is what the extension calls in
    ``onStartup``, and calling it again when the panel opens is what repairs a
    machine where the XML files went missing.
    """
    try:
        import CoatLinkMenu
        info = CoatLinkMenu.ensure()
    except Exception as exc:
        log("could not register the launcher: %s" % exc)
        return []
    return info.get("written", [])


def run_action(tool_id):
    """Run one bridge action headless and report the outcome with 3D-Coat's own
    floating message - no window, no dialog."""
    method, label = ACTION_LABELS.get(tool_id, ("", tool_id))
    add_translations()
    panel = CoatLinkPanel()
    action = getattr(panel, method, None)
    if action is None:
        return "unknown action: %s" % tool_id
    log("tool %s -> %s" % (tool_id, label))
    if tool_id == "CoatLink_Setup":
        ensure_launcher()         # the panel's own entry, XML or no XML
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

def voxelize_via_tree(element, name):
    """Press the tree row's own S/V badge.  True when the object turned voxel.

    Verified by reading the volume back instead of trusting the press: for an object
    3D-Coat does not offer the badge on, nothing happens and the caller falls back to
    the Volume API.  Never raises - this runs from a button, in a live scene.

    The badge raises a small dialog (its OK is `$DialogButton#1`), and 3D-Coat calls
    the callback we hand to `ui.cmd` on every frame that dialog is up - so the dialog
    is accepted here instead of waiting for a click per object.
    """
    if not name:
        return False

    def accept():
        try:
            coat.ui.cmd("$DialogButton#1")
        except Exception:
            pass

    try:
        coat.ui.cmd(VOXEL_TOGGLE_ID % name, accept)
    except TypeError:                     # a build whose ui.cmd takes one argument
        try:
            coat.ui.cmd(VOXEL_TOGGLE_ID % name)
        except Exception:
            return False
    except Exception:
        return False
    for _ in range(VOXEL_TOGGLE_POLLS):
        try:
            coat.io.step(2)          # let 3D-Coat carry the conversion out
            if element.Volume().isVoxelized():
                return True
        except Exception:
            return False
    return False


def panel_text_rows(text, count):
    """Bound native label width/height without querying the host or the disk."""
    lines = textwrap.wrap(str(text), width=44) or [""]
    if len(lines) > count:
        lines = lines[:count]
        lines[-1] = lines[-1][:41] + "..."
    return ["##" + (line or " ") for line in lines + [""] * (count - len(lines))]


class CoatLinkPanel(object):
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
        #: queue state, recomputed only by explicit actions (disk I/O)
        self.QueueLabel = ""
        #: how much of the tree is still surface, recomputed by RefreshStats only
        self.ModeLabel = ""
        self._saved_controls = (self.ReductionPercent, self.Textures, self.SendScope)
        self.refresh_detail()

    # ---- layout -----------------------------------------------------------

    def ui(self):
        self.process()  # cached controls only; no scene access
        items = []
        # the two actions side by side, first, exactly like the Blender menu draws them
        items.append("[1 1]")
        items.append("SendToBlender")
        items.append("PullFromBlender")
        items.append("[1]")
        items.append("VoxelizeVisible")
        items.append("##makes every visible object in the Sculpt Tree a voxel volume")
        items.append("---")
        items.append("#Send options")
        items.append("SendScope,[%s]" % SEND_SCOPE_LABELS)
        try:
            items.append("##" + SEND_SCOPE_HINTS[int(self.SendScope)])
        except (IndexError, TypeError, ValueError):
            pass
        items.append("#" + self.SizeLabel)
        items.append("ReductionPercent,[0,100]")
        items.append("RefreshStats")
        items.extend(panel_text_rows(
            getattr(self, "StatsLabel", "Statistics paused; click Refresh info"), 2))
        items.extend(panel_text_rows(self.ModeLabel, 1))
        items.append("##Reduction % = removed; estimate only, export not verified")
        items.append("Textures,[%s]" % TEXTURES_LABELS)
        items.append("---")
        items.append("#Setup")
        items.append("[1 1]")
        items.append("Detect")
        items.append("OpenFolder")
        items.append("[1 1]")
        items.append("StartBlender")
        items.append("RemoveLauncher")
        items.append("[1]")
        items.append("---")
        items.append("#Status")
        items.extend(panel_text_rows(self.status, 4))
        items.extend(panel_text_rows(self.detail, 2))
        items.append("CopyDetails")
        items.append("##copies full details, including local paths")
        items.extend(panel_text_rows(self.QueueLabel, 1))
        items.append("##" + REOPEN_HINT)
        return items

    def CopyDetails(self):
        """Explicit local clipboard action; never called by redraw."""
        report = "\n".join((PANEL_CAPTION, self.status, self.detail, self.SizeLabel,
                            getattr(self, "StatsLabel", "Statistics not refreshed")))
        try:
            if sys.platform != "win32":
                raise RuntimeError("clipboard copying is currently available on Windows only")
            subprocess.run(["clip.exe"], input=report.encode("utf-16"),
                           check=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
        except Exception as exc:
            self._report("Could not copy details: %s" % exc, "Use the CoatLink log instead")
            return
        # Preserve the diagnostic readout being copied, rather than replacing it.
        try:
            coat.ui.showInfoMessage("Details copied (includes local paths)", 2500)
        except Exception:
            pass

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
            values[TEXTURES_KEY] = "on" if TEXTURES_CHOICES[choice] else "off"
        if save_state(values):
            self._saved_controls = current
        return False

    def _visible_voxel_targets(self):
        """Every object the Sculpt Tree is showing right now.

        Leaves only: a node with children is packaging (the group 3D-Coat wraps an
        import in), and converting it would leave a stray extra volume behind.
        Hidden or unreadable branches are skipped before visiting children.
        Returns (targets, skipped branch count), never raises, bounded.
        """
        try:
            root = coat.Scene.sculptRoot()
        except Exception:
            return [], 0
        targets = []
        hidden = [0]

        def walk(element, depth=0):
            if element is None or depth > 8:
                return
            try:
                visible = element.visible()
            except Exception:
                visible = False
            if not visible:
                hidden[0] += 1
                return
            try:
                count = element.childCount()
            except Exception:
                hidden[0] += 1
                return
            if count:
                for index in range(count):
                    try:
                        walk(element.child(index), depth + 1)
                    except Exception:
                        continue
                return
            targets.append(element)

        # the sculpt root is the container, never an object: walking from it would
        # treat an empty tree as one node whose volume cannot be read
        try:
            count = root.childCount()
        except Exception:
            count = 0
        for index in range(count):
            try:
                walk(root.child(index))
            except Exception:
                continue
        return targets, hidden[0]

    def VoxelizeVisible(self):
        """Turn every visible object in the Sculpt Tree into voxel volumes.

        The import mode is not ours to force - 3D-Coat decides that from import.txt -
        and it has been handing models over in surface mode whatever the mode line
        says.  This is the one click that puts the whole scene where the sculpting
        tools want it.  Objects that are already voxelized are counted and left alone,
        hidden ones are reported but not touched, and a failure is a sentence in the
        status line rather than an exception.
        """
        targets, hidden = self._visible_voxel_targets()
        if not targets and not hidden:
            self.status = "Nothing in the Sculpt Tree to convert"
            return
        converted = already = failed = 0
        via_tree = 0
        for element in targets:
            try:
                volume = element.Volume()
                if volume.isVoxelized():
                    already += 1
                    continue
                # 3D-Coat's own badge first: it is the conversion the user trusts
                if voxelize_via_tree(element, _element_name(element)):
                    converted += 1
                    via_tree += 1
                    continue
                volume.toVoxels()
                converted += 1
            except Exception:
                failed += 1
        parts = []
        if converted:
            parts.append("%d to voxels" % converted)
        if via_tree:
            parts.append("%d via 3D-Coat's tree button" % via_tree)
        if already:
            parts.append("%d already voxel" % already)
        if hidden:
            parts.append("%d hidden/unreadable branches, left alone" % hidden)
        if failed:
            parts.append("%d could not be converted" % failed)
        self.status = "To voxels: " + (", ".join(parts) if parts else "nothing to do")
        log(self.status)
        try:
            self.RefreshStats()
        except Exception:
            pass

    @staticmethod
    def volume_mode(volume):
        """` · voxel volume` / ` · surface mode`, or "" when it cannot be told.

        The Sculpt Tree shows the same thing as one letter (V / S), and it is the first
        question after an import, so it belongs in the readout where it can be read
        without hunting for the object in the tree.
        """
        for name, text in (("isVoxelized", " · voxel volume"),
                           ("isSurface", " · surface mode")):
            try:
                if getattr(volume, name)():
                    return text
            except Exception:
                continue
        return ""

    def RefreshStats(self):
        """Explicit user action only: never inspect live mesh during redraw."""
        self.SizeLabel = size_line()
        self.ModeLabel = self.mode_summary()
        try:
            volume = coat.Scene.current().Volume()
            count = int(volume.getPolycount())
            self.StatsLabel = "Snapshot: %d faces%s (not auto-refreshed)" % (
                count, self.volume_mode(volume))
        except Exception as exc:
            self.StatsLabel = "Statistics unavailable: %s" % exc

    def mode_summary(self):
        """How many of the visible tree objects are still surfaces.

        The number the user asked for: after an import it is not obvious how much of
        the scene is in surface mode, and that is exactly what decides whether `To
        voxels` still has work to do.  Explicit action only - it walks the tree, which
        must never happen during a redraw.
        """
        try:
            targets, _hidden = self._visible_voxel_targets()
        except Exception:
            return ""
        surface = 0
        counted = 0
        for element in targets:
            try:
                voxel = bool(element.Volume().isVoxelized())
            except Exception:
                continue
            counted += 1
            if not voxel:
                surface += 1
        if not counted:
            return ""
        text = "%d of %d visible objects in surface mode" % (surface, counted)
        return text + " - press To voxels" if surface else text

    def refresh_detail(self):
        root = primary_root()
        if not root:
            self.detail = "exchange folder not found - press Detect"
            self.QueueLabel = ""
            return
        queued = read_import_model(root)
        parts = ["Folder: " + os.path.basename(root)]
        parts.append("waiting: " + os.path.basename(queued) if queued else "waiting: nothing")
        self.detail = " | ".join(parts)
        self.QueueLabel = ("Queue: %s waiting - press Pull" % os.path.basename(queued)
                           if queued else "Queue: nothing waiting from Blender")
    # ---- actions ----------------------------------------------------------

    def SendToBlender(self):
        """Export the current model into our folder and hand Blender the path."""
        coat_settings_info()
        root = primary_root()
        if not root:
            self._report("exchange folder not found - press Detect", "")
            return
        if not ensure_folder(root):
            self._report("could not create our exchange folder", "")
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
            write_shader_map(root, model=path)
            self._report("Sent to Blender via the AppLink target (whole scene)" + export_note(),
                         "folder: %s" % app_folder(root))
            return
        exported = self._export_direct(path)
        if exported:
            write_signal(root, path)
            write_shader_map(root, model=path)
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
        write_shader_map(root, names, path)
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
        """Take the menu entry and the tool buttons back out again.

        The two files are what put them there, so that is what goes: deleting
        3D-Coat's own insertion files for the id (written when an older build
        inserted it at run time) keeps a restart from bringing the entry back.
        """
        removed = []
        import CoatLinkMenu  # imported here: CoatLinkMenu imports this module
        for name in (CoatLinkMenu.MENU_FILE, CoatLinkMenu.TOOLS_FILE):
            path = os.path.join(CoatLinkMenu.extra_menu_dir(), name)
            try:
                if os.path.isfile(path):
                    os.remove(path)
                    removed.append(name)
            except OSError as exc:
                self._report("Could not remove %s" % name, str(exc))
                return
        for name in os.listdir(CoatLinkMenu.extra_menu_dir() or "."):
            if name.startswith(MENU_ID + "_") and name.endswith(".xml"):
                try:
                    os.remove(os.path.join(CoatLinkMenu.extra_menu_dir(), name))
                    removed.append(name)
                except OSError:
                    pass
        self._report("Launcher removed", "removed %s - run this script again "
                     "(Scripts > CoatLink) to put it back" % ", ".join(removed or ["nothing"]))

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
            # the queue readout is disk I/O, so only an explicit action refreshes it
            root = primary_root()
            queued = read_import_model(root) if root else ""
            self.QueueLabel = ("Queue: %s waiting - press Pull" % os.path.basename(queued)
                               if queued else "Queue: nothing waiting from Blender")
        except Exception:
            pass
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
    """Write the menu file 3D-Coat reads at startup, for every menu path.

    This used to insert the entry at run time instead.  The XML is the way that
    survives a restart, and an id that is both in the XML and in 3D-Coat's own
    insertion file is listed twice - so the file is the only route now, and
    ``CoatLinkMenu.clean_old_installs()`` removes the older insertion files.
    """
    try:
        coat.ui.addTranslation(MENU_ID, PANEL_CAPTION)
    except Exception:
        pass
    try:
        import CoatLinkMenu
        return CoatLinkMenu.write_menu_xml()
    except Exception as exc:
        log("could not write the menu entry: %s" % exc)
        return []


def register_room_tools():
    """Write the tool buttons of the rooms listed in TOOL_ROOMS.

    Same reasoning as register_menu_item(): one XML file, read at every start, one
    entry per button per room.  A run-time insert gives every room a single generic
    button instead, and lists it twice when the XML also carries the id.  The labels
    come from the translation table filled in by register_menu_item().
    """
    try:
        import CoatLinkMenu
        return CoatLinkMenu.write_tools_xml()
    except Exception as exc:
        log("could not write the tool buttons: %s" % exc)
        return []


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

    panel = CoatLinkPanel()
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
