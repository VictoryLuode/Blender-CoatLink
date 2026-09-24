# SPDX-License-Identifier: GPL-3.0-or-later
#
# CoatLink - 3D-Coat side of the model bridge.  Copyright (C) 2026 VictoryLuode
#
# A non-modal panel pinned to the top-right of the 3D-Coat viewport, with the
# same sections, in the same order and the same words, as the Blender add-on's
# menu:
#
#     Export / Import      hand this model to Blender, take what Blender sent
#     Export options       Export type, Export range, Reduction percent
#     Import options       Selected To Voxel - convert what is selected
#     Setup                Detect, Open folder, Start Blender, Remove launcher
#     Status               the object readouts, the last action, Copy details
#
# No descriptions under the controls: the labels say what they do, and a panel
# that explains itself in fine print stops reading like the Blender menu.  The
# words and the order of the sections are what make the two halves one product.
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
#: Where the shaders live under a 3D-Coat folder.  A preset that cannot be found costs
#: the parameters, never the assignment.
SHADER_ROOT_PARTS = ("UserPrefs", "Shaders")
#: The family 3D-Coat's own PBR presets are filed under - what a shader path usually
#: starts with.  Other families sit beside it (measured: "NGPreview", "CurrentMcubes"),
#: so the whole shader folder is searched, not this one family.
SHADER_DEFAULT_FAMILY = "PbrShaders"
#: The copy that matters is the installation's: measured, GetCurVolumeShader answers
#: "PbrShaders/Gold2/mcubes", and Gold2 is one of the presets 3D-Coat ships, which live
#: in the program folder ("<install>/UserPrefs/Shaders/PbrShaders/#Metal/Gold2"), not in
#: the user data folder.  The user's own copy is searched first all the same - that is
#: where downloaded shaders land.  The install folder carries a year and can sit on any
#: drive, so it is looked for rather than assumed.
_DRIVE_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_INSTALL_DRIVES = []
_DRIVES_LOOKED_UP = []
_INSTALL_ROOT = []
_PRESET_FOLDERS = {}
_PRESET_NAMES = []

#: 3D-Coat's own decimation slider.  This is the id the shipped scripts use -
#: UserPrefs/Scripts/mm_export.as and CoreAPI/Templates/CoreAPI_Export/
#: auto_export.cpp both do SetSliderValue("$DecimationParams::ReductionPercent", n)
#: while the export dialog is up, then press "$DialogButton#1" (OK).
#: The value is the percentage of triangles to KEEP (0 = no reduction).
REDUCTION_SLIDER = "$DecimationParams::ReductionPercent"
REDUCTION_KEY = "reduction"

#: what a Send hands over: the nodes selected in the sculpt tree (and their children,
#: one node or several), or 3D-Coat's own export.  The two are not the same thing -
#: 3D-Coat decides for itself what its own export covers - but the panel states that
#: in words, not in a caption under the droplist (docs/menus.md, "Export range").
SEND_SCOPE_KEY = "send_scope"
SEND_SCOPES = ("selected", "scene")
SEND_SCOPE_LABELS = "#Selected objects|#Visible objects"

#: What an export carries.  Two exports behind one panel row: "sculpt" hands over the
#: volumes in the Sculpt Tree, "paint" the painting room's mesh with its textures.
#: Blender receives both through the same door - it is the same model format, and the
#: same pull imports it - but only the paint route has textures to put on anything, so
#: only that route writes a material map.
KIND_KEY = "export_type"
KINDS = ("sculpt", "paint")
KIND_LABELS = "#sculpt object|#paint object"

#: the export dialog's texture folder, and the record written beside a paint export
TEXTURES_PATH_FIELD = "$ExportOpt::PathForTextures"
PAINT_MAP_FILE = "paint.json"

#: the export dialog's "export textures" checkbox (documented as an import.txt
#: option listed in applinks.rst, settable with the CMD module's SetBoolField)
TEXTURES_FIELD = "$ExportOpt::ExportTextures"

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


def xml_escape(text):
    """Escape text that is about to be written inside an XML element.

    The menu files carry absolute paths, and a single unescaped ``&`` makes the whole
    file unreadable to 3D-Coat - which then shows no menu at all, with nothing in the log
    to say why.  ``&`` is a legal character in a Windows user or folder name
    (``C:\\Users\\Tom & Jerry\\...``), so every path that goes into the XML goes through
    here first.
    """
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


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

    What the script found by looking at itself comes first; the folder under Documents
    is only the guess to fall back on when that failed (the script was started from
    somewhere else, or copied out of its folder).  Recent builds name that folder after
    the version (``3DCoat2025``, ``3DCoat2026``) and the 4.x line carried a hyphen
    (``3D-CoatV48``), so the name is matched, never assumed - and only folders that
    really hold 3D-Coat's data count.
    """
    data = script_user_data()
    if data:
        return data
    for base in documents_bases():
        for name in os.listdir(base) if os.path.isdir(base) else []:
            lowered = name.lower()
            if not (lowered.startswith("3dcoat") or lowered.startswith("3d-coat")):
                continue
            folder = os.path.join(base, name)
            if os.path.isdir(os.path.join(folder, "UserPrefs")) \
                    or os.path.isdir(os.path.join(folder, "Scripts")):
                return folder
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


def file_stamp(path):
    """(size, mtime in ns) - how a freshly written file is told from the last one.

    The exchange files have fixed names, so "the file is there" never means "it was just
    written": the stamp is what does.
    """
    try:
        info = os.stat(path)
    except OSError:
        return None
    return (info.st_size, getattr(info, "st_mtime_ns", int(info.st_mtime * 1000000000)))


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
                if CMD.SetCurVolume(name) is False:      # some builds answer None on success
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


def drive_is_worth_asking(root):
    """Whether Windows should be asked about a drive at all.

    Only two answers matter: a fixed or removable drive that is really there.  Asking a
    disconnected network mapping whether a path exists blocks for tens of seconds, and the
    drive type is answered without touching the drive - so this check must never be the
    thing that hangs.  Off Windows there is nothing to ask, and the answer is yes.
    """
    try:
        import ctypes

        kinds = {0: "unknown", 1: "none", 2: "removable", 3: "fixed",
                 4: "remote", 5: "cdrom", 6: "ram"}
        kind = kinds.get(ctypes.windll.kernel32.GetDriveTypeW(str(root)), "unknown")
    except Exception:
        kind = "unknown"
    if kind in ("none", "remote", "cdrom"):
        return False
    try:
        return os.path.exists(root)
    except OSError:
        return False


def install_drives():
    """The drive letters to look for a 3D-Coat install on, looked up once per session."""
    if _DRIVES_LOOKED_UP:
        return _INSTALL_DRIVES
    for letter in _DRIVE_LETTERS:
        if drive_is_worth_asking("%s:/" % letter):
            _INSTALL_DRIVES.append(letter)
    _DRIVES_LOOKED_UP.append(True)          # the answer does not change mid-session
    return _INSTALL_DRIVES


def install_roots_with_shaders():
    """Every program folder that really carries a shader library, newest name last."""
    tops = []
    for drive in install_drives():
        tops += ["%s:/Program Files" % drive, "%s:/Program Files (x86)" % drive]
    local = os.environ.get("LOCALAPPDATA")
    if local:
        tops.append(os.path.join(local, "Programs"))   # a per-user install lands here
    found = []
    for top in tops:
        try:
            entries = sorted(os.listdir(top))
        except OSError:
            continue
        for entry in entries:
            lowered = entry.lower()
            # measured: the folder is "3DCoat-2025" on some installs, "3DCoat2025" on
            # others, so both spellings count - and only one that has the library
            if not (lowered.startswith("3dcoat") or lowered.startswith("3d-coat")):
                continue
            folder = os.path.join(top, entry)
            if os.path.isdir(os.path.join(folder, "UserPrefs", "Shaders")):
                found.append(folder)
    return sorted(found, key=lambda path: os.path.basename(path).lower())


def install_root():
    """3D-Coat's program folder, or "" when none is found.

    The folder carries a year in its name and can sit on any drive, so it is looked for
    instead of assumed - the same reason tests/check_coat_api.py looks for it.  With two
    installs side by side the newest name wins, so a preset is read from the build the
    artist is most likely running.  Read once per session (memoised), because the search
    walks the program-folder listing of every drive.
    """
    if _INSTALL_ROOT:
        return _INSTALL_ROOT[0]
    found = install_roots_with_shaders()
    _INSTALL_ROOT.append(found[-1] if found else "")
    return _INSTALL_ROOT[0]


def shader_preset_roots():
    """Where the shaders are kept: the user's copy first, then the installation's."""
    roots = [os.path.join(user_data_dir(), *SHADER_ROOT_PARTS)]
    install = install_root()
    if install:
        roots.append(os.path.join(install, *SHADER_ROOT_PARTS))
    return [root for root in roots if os.path.isdir(root)]


def presets_under(root, depth=4):
    """Folders under ``root`` that hold a ShaderParams.xml - a preset, by its own mark.

    They are filed in families and categories (#Metal/Gold2) and can also sit straight
    under a family, so the walk goes a few levels down and stops at any folder that
    identifies itself as a preset.
    """
    found = []
    pending = [(root, 0)]
    while pending:
        current, level = pending.pop()
        try:
            entries = sorted(os.listdir(current))
        except OSError:
            continue
        for entry in entries:
            path = os.path.join(current, entry)
            if not os.path.isdir(path):
                continue
            if os.path.isfile(os.path.join(path, "ShaderParams.xml")):
                found.append(path)
            elif level + 1 < depth:
                pending.append((path, level + 1))
    return found


def preset_folder(shader):
    """The preset folder a shader name points at, or "".

    Measured: GetCurVolumeShader answers with the shader's place in 3D-Coat's library -
    "PbrShaders/Gold2/mcubes" - where the last part names the shader *file* inside the
    preset folder (measured across the whole library: every preset carries
    "mcubes.glsl"), so the part before it is the preset.  That path is tried **exactly
    first**, under the shader folder and then under the default family, because the same
    preset name exists twice in the shipped library (a loose "PbrShaders/Gold2" and a
    categorised "PbrShaders/#Metal/Gold2" are different presets with different stored
    values) and only the path says which one a volume is using.  Name matching stays as
    the fallback for the forms that are not paths - a bare name ("Aluminum") and a
    category-qualified one ("#Metal/Aluminum") name the same preset - where any folder
    holding a ShaderParams.xml wins.  Cached per shader string: a send asks once per
    volume.
    """
    wanted = (shader or "").replace("\\", "/").strip("/")
    if not wanted:
        return ""
    if wanted in _PRESET_FOLDERS:
        return _PRESET_FOLDERS[wanted]
    parts = [part for part in wanted.split("/") if part]
    names = []
    for name in ((parts[-2] if len(parts) > 1 else ""), parts[-1] if parts else ""):
        if name and name not in names:
            names.append(name.lower())
    # Two forms come back from 3D-Coat: a path inside the library, whose last part is the
    # shader file ("PbrShaders/Gold2/mcubes"), and a name relative to the library, which is
    # a folder outright ("#Metal/Aluminum").  Both are tried with and without the default
    # family in front of them, and only a folder that carries a ShaderParams.xml counts.
    relatives = []
    for candidate in (parts, parts[:-1]):
        if not candidate:
            continue
        relatives.append(os.path.join(*candidate))
        if candidate[0].lower() != SHADER_DEFAULT_FAMILY.lower():
            relatives.append(os.path.join(SHADER_DEFAULT_FAMILY, *candidate))
    relatives = [relative for index, relative in enumerate(relatives)
                 if relative and relative not in relatives[:index]]
    found = ""
    for root in shader_preset_roots():
        for relative in relatives:
            exact = os.path.join(root, relative)
            if os.path.isfile(os.path.join(exact, "ShaderParams.xml")):
                found = exact
                break
        if found:
            break
        for folder in presets_under(root):
            if os.path.basename(folder).lower() in names:
                found = folder
                break
        if found:
            break
    _PRESET_FOLDERS[wanted] = found
    return found


def preset_names():
    """{preset folder name, lower case: how many folders carry it} over both copies.

    Measured on the shipped library: four names are used twice - "Gold2", "Copper",
    "Skin" (a loose preset and a categorised one) and "Default" (PbrShaders and
    NGPreview) - and those are different presets, so a material named after the bare
    name alone would quietly mix two shaders.
    """
    if not _PRESET_NAMES:
        counts = {}
        for root in shader_preset_roots():
            for folder in presets_under(root):
                name = os.path.basename(folder).lower()
                counts[name] = counts.get(name, 0) + 1
        _PRESET_NAMES.append(counts)
    return _PRESET_NAMES[0]


def relative_preset_path(folder):
    """A preset's path inside the library: "#" dropped, the default family dropped.

    ".../Shaders/PbrShaders/#Metal/Gold2" -> "Metal/Gold2"; one sitting straight under the
    default family keeps just its own name, and another family keeps its family name
    ("NGPreview/Default").
    """
    for root in shader_preset_roots():
        prefix = root.rstrip("/\\") + os.sep
        if folder.lower().startswith(prefix.lower()):
            parts = [part for part in folder[len(prefix):].replace("\\", "/").split("/") if part]
            if parts and parts[0] == SHADER_DEFAULT_FAMILY:
                parts = parts[1:]
            return "/".join(part.lstrip("#") for part in parts)
    return ""


def shader_material_name(folder, shader=""):
    """The name to give a material for this shader: "Gold2", or "Metal/Gold2" if needed.

    The preset's own name is the name, unless the library holds another preset with that
    name - then the folder's place in the library says which is which.  When no folder
    could be worked out, the shader string itself is read instead: measured as
    "PbrShaders/Gold2/mcubes", dropping the leading family and the trailing shader file
    leaves the preset's name.
    """
    if folder:
        base = os.path.basename(folder)
        if preset_names().get(base.lower(), 0) <= 1:
            return base
        return relative_preset_path(folder) or base
    parts = [part for part in str(shader or "").replace("\\", "/").split("/") if part]
    if len(parts) > 1 and parts[0].lower() == SHADER_DEFAULT_FAMILY.lower():
        parts = parts[1:]
    if len(parts) > 1:
        parts = parts[:-1]          # the shader file every preset of this family carries
    return parts[-1] if parts else ""


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
    try:
        return _write_shader_map(root, names=names, model=model)
    except Exception as exc:
        log("shader map: not written (%s: %s)" % (type(exc).__name__, exc))
        return {}


def _write_shader_map(root, names=None, model=""):
    if names is None:
        names = model_nodes(model)
    names = [name for name in (names or []) if name]
    # The library can change between sends (a shader installed, a preset moved), and what
    # the map says about names and parameters must not be a stale picture of it.
    _PRESET_FOLDERS.clear()
    del _PRESET_NAMES[:]
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
        # The name a material for this shader should carry: the preset's own name, or its
        # place in the library when two presets share that name.  The Blender half has no
        # way to work this out - it never sees the library - so it is decided here.
        preset_name = shader_material_name(preset_folder(shader), shader)
        if preset_name:
            entry["preset"] = preset_name
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
    registration all write different keys and must not wipe each other.

    Written through a temporary file and renamed, because a half-written state file costs
    every setting in it - and the units and axis the Blender half reads live in there too.
    """
    try:
        import json

        merged = load_state()
        merged.update(data)
        os.makedirs(os.path.dirname(state_path()), exist_ok=True)
        temporary = state_path() + ".tmp"
        with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(merged, handle, indent=2)
        os.replace(temporary, state_path())
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


def export_kind():
    """What an export hands over - "sculpt" unless the panel says paint."""
    value = str(load_state().get(KIND_KEY, "sculpt")).lower()
    return value if value in KINDS else "sculpt"


def set_export_kind(value):
    if value not in KINDS:
        return False
    return save_state({KIND_KEY: value})


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


#: the export preset this bridge installs into 3D-Coat's own list: the answer to every
#: question its "Export Objects & Textures" dialog asks a paint export
EXPORT_PRESET_NAME = "CoatLink"


def export_preset_dir():
    """``…/UserPrefs/ExportPresets`` in the user's 3D-Coat data folder, "" when unknown."""
    try:
        data = user_data_dir()
    except Exception:
        return ""
    return os.path.join(data, "UserPrefs", "ExportPresets") if data else ""


def _preset_base():
    """3D-Coat's own Blender App-Link preset, or a minimal one when it is not there.

    Reusing theirs is not laziness: its texture slots (``diffuse``, ``normalmap``,
    ``metalness``…) are exactly the PBR set the Blender half knows how to wire up, and
    a future build's slots should come along without this file being edited.
    """
    try:
        root = install_root()
    except Exception:
        root = ""
    if root:
        base = os.path.join(root, "UserPrefs", "ExportPresets", "BlenderAppLink.xml")
        try:
            if os.path.isfile(base):
                with open(base, "r", encoding="utf-8", errors="replace") as handle:
                    return handle.read()
        except OSError:
            pass
    return ("<ExportOpt>\n"
            " <ExportGeometry>true</ExportGeometry>\n"
            " <ExportTextures>true</ExportTextures>\n"
            " <TexApproach>RoughnessMetallness</TexApproach>\n"
            " <ExportResolution>MID-POLY</ExportResolution>\n"
            " <SwapYZ>false</SwapYZ>\n"
            " <PathForTextures>%(folder)s</PathForTextures>\n"
            " <!ExportPreset>%(name)s</!ExportPreset>\n"
            " <PmsMixer>\n"
            "  <UseObjectNameAsPreffix>true</UseObjectNameAsPreffix>\n"
            "  <ExportUvSetsToDifferentFolders>false</ExportUvSetsToDifferentFolders>\n"
            "  <SkipUVSetNameIfSingle>true</SkipUVSetNameIfSingle>\n"
            "  <Textures>\n"
            "   <OneExportTexture><TextureSuffix>diffuse</TextureSuffix><RGB>TEX_COLOR</RGB></OneExportTexture>\n"
            "   <OneExportTexture><TextureSuffix>normalmap</TextureSuffix><RGB>TEX_TANGENTNORMALMAP</RGB></OneExportTexture>\n"
            "   <OneExportTexture><TextureSuffix>roughness</TextureSuffix><RGB>TEX_ROUGHNESS</RGB></OneExportTexture>\n"
            "   <OneExportTexture><TextureSuffix>metalness</TextureSuffix><RGB>TEX_METALL</RGB></OneExportTexture>\n"
            "  </Textures>\n"
            " </PmsMixer>\n"
            "</ExportOpt>\n")


def write_export_preset(root=None):
    """Write this bridge's own export preset into 3D-Coat's preset list.

    The paint route hands the user 3D-Coat's "Export Objects & Textures" dialog, and
    every question that dialog asks about a paint export - geometry yes, textures yes,
    textures next to the model, names starting with the object's - is a *preset* in
    3D-Coat.  A preset the user has to assemble by hand is one more thing to get wrong,
    so it is generated here, per machine, because it carries our folder as an absolute
    path.  Presets are read when that dialog opens and are never rewritten by 3D-Coat,
    so writing this while the application runs is safe.
    """
    folder = export_preset_dir()
    if not folder:
        return ""
    try:
        os.makedirs(folder, exist_ok=True)
        text = _preset_base()
        text = re.sub(r"<!ExportPreset>.*?</!ExportPreset>",
                      "<!ExportPreset>%s</!ExportPreset>" % EXPORT_PRESET_NAME, text, flags=re.S)
        # the shared exchange root - the one a send writes to, so the one the textures
        # have to land in.  primary_root() only knows roots that already exist, hence
        # the fallback: the folder is created by the first send, not by this.
        try:
            root = primary_root() or (candidate_roots() or [""])[0]
        except Exception:
            root = ""
        target = app_folder(root) if root else ""
        wanted = "<PathForTextures>%s</PathForTextures>" % str(target).replace("\\", "/")
        if "<PathForTextures>" in text:
            text = re.sub(r"<PathForTextures>.*?</PathForTextures>", wanted, text, flags=re.S)
        else:
            marker = "<D></D>"
            text = (text.replace(marker, marker + "\n " + wanted, 1) if marker in text
                    else text.replace("</ExportOpt>", " " + wanted + "\n</ExportOpt>", 1))
        path = os.path.join(folder, EXPORT_PRESET_NAME + ".xml")
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        log("export preset %s: textures -> %s" % (EXPORT_PRESET_NAME, target))
        return path
    except Exception as exc:
        log("export preset not written (%s: %s)" % (type(exc).__name__, exc))
        return ""


def apply_textures(on=False):
    """Set 3D-Coat's own texture export: off for a sculpt send, on for a paint one.

    There is no texture control on the panel, because the two kinds want opposite
    answers and neither is a matter of taste.  A sculpt export has no UVs for a
    texture to land on and nothing on the Blender side read the files, so off is the
    answer - and answering it explicitly matters: leaving the checkbox alone would hand
    the result over to whatever state 3D-Coat's dialog was left in, and the same click
    would then produce different folders on different days.  A paint export is the
    other case: its textures are the whole point, so it asks for them.
    """
    if CMD is None:
        return "textures: no CMD api in this build"
    try:
        CMD.SetBoolField(TEXTURES_FIELD, bool(on))
    except Exception as exc:
        return "textures %s failed: %s" % ("on" if on else "off", exc)
    return "textures %s" % ("on" if on else "off")


def apply_texture_folder(folder):
    """Point the export dialog's texture folder at ours (paint exports only).

    3D-Coat writes the texture files itself - no API hands them over - so this is the
    one place their folder is decided.  The setter lives on ``coat.ui`` (the CMD module
    has SetBoolField only); 3D-Coat's own Autoexport template sets the same field the
    same way before pressing the dialog's Export.
    """
    setter = getattr(getattr(coat, "ui", None), "setEditBoxValue", None)
    if setter is None:
        return "textures folder: no ui api in this build"
    try:
        if not setter(TEXTURES_PATH_FIELD, folder):
            return "textures folder not accepted by 3D-Coat"
    except Exception as exc:
        return "textures folder failed: %s" % exc
    return "textures folder %s" % folder


def paint_objects():
    """What the painting room holds: object names, materials and texture sets.

    Read straight from 3D-Coat (``Scene.PaintObjectName`` and its neighbours).  This is
    the only place the Blender side can learn which material to build: the .mtl a
    3D-Coat export writes carries empty material names, so nothing in the model itself
    says it.  Never raises - a name that cannot be read must not stop an export.
    """
    scene = getattr(coat, "Scene", None)
    try:
        count = int(scene.PaintObjectsCount())
    except Exception:
        return None
    names = []
    for index in range(count):
        try:
            names.append(str(scene.PaintObjectName(index)))
        except Exception:
            continue
    materials = []
    try:
        material_count = int(scene.PaintMaterialCount())
    except Exception:
        material_count = 0
    for index in range(material_count):
        try:
            materials.append(str(scene.PaintMaterialName(index)))
        except Exception:
            continue
    uv_sets = []
    try:
        uv_count = int(scene.PaintUVSetsCount())
    except Exception:
        uv_count = 0
    for index in range(uv_count):
        try:
            uv_sets.append(str(scene.PaintUVSetName(index)))
        except Exception:
            continue
    return {"objects": names, "materials": materials, "uv_sets": uv_sets}


def paint_map_path(root):
    return os.path.join(root, PAINT_MAP_FILE)


def remove_paint_map(root):
    try:
        os.remove(paint_map_path(root))
    except OSError:
        pass


def write_paint_map(root, model=""):
    """Record the painting room's objects, materials and texture sets beside the model.

    Written after a paint export and *removed* when nothing could be read, for the same
    reason the shader map is: a stale record describing a newer model is worse than no
    record at all, and the Blender side would build materials out of it in good faith.
    """
    try:
        found = paint_objects()
        if not found or not (found["objects"] or found["materials"]):
            remove_paint_map(root)
            log("paint map: nothing recorded")
            return {}
        payload = {
            "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
            "model": os.path.basename(model or model_path(root, EXPORT_FORMAT)),
            "objects": found["objects"],
            "materials": found["materials"],
            "uv_sets": found["uv_sets"],
        }
        with open(paint_map_path(root), "w") as handle:
            handle.write(json.dumps(payload, indent=1, sort_keys=True))
        log("paint map: %d object(s), %d material(s), %d uv set(s)"
            % (len(payload["objects"]), len(payload["materials"]), len(payload["uv_sets"])))
        return payload
    except Exception as exc:
        log("paint map: not written (%s: %s)" % (type(exc).__name__, exc))
        return {}


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
PANEL_ACTION_LABELS = {"SendToBlender": "Export", "PullFromBlender": "Import"}

#: 3D-Coat labels a panel control by its own name unless that name is translated, so
#: without this the panel reads "SendScope", "ReductionPercent", "RefreshStats" - the
#: words the code uses, not words a person uses.  The wording matches the Blender menu
#: wherever the two mean the same thing.
PANEL_LABELS = {
    "ExportType": "Export type",
    "SendScope": "Export range",
    "ReductionPercent": "Reduction percent",
    "CopyDetails": "Copy details",
    "Detect": "Detect",
    "OpenFolder": "Open folder",
    "StartBlender": "Start Blender",
    "RemoveLauncher": "Remove tool buttons",
    "SelectedToVoxel": "Selected To Voxel",
}

ACTION_LABELS = {
    "CoatLink_Send": ("SendToBlender", "Export to Blender"),
    "CoatLink_Pull": ("PullFromBlender", "Import from Blender"),
    "CoatLink_Setup": ("OpenPanel", "CoatLink"),
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
        info = {}
    # the entry itself is inserted rather than declared: see register_menu_item()
    return list(info.get("written", [])) + register_menu_item()


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
        self.ExportType = KINDS.index(export_kind())
        self.SendScope = SEND_SCOPES.index(send_scope())
        self.SizeLabel = "Size: -"
        #: queue state, recomputed only by explicit actions (disk I/O)
        self.QueueLabel = ""
        #: how much of the tree is still surface, recomputed by RefreshStats only
        self.ModeLabel = ""
        self._saved_controls = (self.ReductionPercent, self.ExportType, self.SendScope)
        self.refresh_detail()
        self.refresh_stats()

    # ---- layout -----------------------------------------------------------

    def ui(self):
        self.process()  # cached controls only; no scene access
        items = []
        # the two actions side by side, first, exactly like the Blender menu draws them
        items.append("[1 1]")
        items.append("SendToBlender")
        items.append("PullFromBlender")
        items.append("---")
        # Same sections, same order, same words as the Blender menu: what goes out,
        # what to do with what came back, the setup, the readout.  No descriptions
        # under the controls - the labels say what they do.
        items.append("#Export options")
        # What goes out comes first: the kind decides what everything under it means.  A
        # paint export has no range to offer - 3D-Coat's own dialog decides which paint
        # objects it writes, and the panel cannot narrow that - so that row is not drawn
        # there.  A control that cannot do anything is worse than one that is not there.
        # The kind comes from the cached control, never from a state-file read: nothing
        # inside ui() may touch the disk, because 3D-Coat redraws this panel whenever it
        # pleases (the suite has a test that fails on any state read from a redraw).
        items.append("ExportType,[%s]" % KIND_LABELS)
        painting = (0 <= int(self.ExportType) < len(KINDS)
                    and KINDS[int(self.ExportType)] == "paint")
        if not painting:
            items.append("SendScope,[%s]" % SEND_SCOPE_LABELS)
        items.append("ReductionPercent,[0,100]")
        items.append("---")
        items.append("#Import options")
        items.append("[1]")
        items.append("SelectedToVoxel")
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
        # Everything about the objects themselves lives here, in Status, beside the
        # last action: the size, the face-count snapshot, how much of the tree is
        # still surface.  The queue row appears only while something is waiting.
        items.append("#Status")
        items.append("#" + self.SizeLabel)
        items.extend(panel_text_rows(
            getattr(self, "StatsLabel", "Snapshot unavailable"), 2))
        if self.ModeLabel:
            items.extend(panel_text_rows(self.ModeLabel, 1))
        items.extend(panel_text_rows(self.status, 2))
        items.append("CopyDetails")
        items.append("##copies full details, including local paths")
        if self.QueueLabel:
            items.extend(panel_text_rows(self.QueueLabel, 1))
        items.append("##" + REOPEN_HINT)
        return items

    def CopyDetails(self):
        """Explicit local clipboard action; never called by redraw."""
        report = "\n".join((PANEL_CAPTION, self.status, self.detail, self.SizeLabel,
                            getattr(self, "StatsLabel", "Statistics not refreshed"),
                            self.ModeLabel))
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
        current = (self.ReductionPercent, self.ExportType, self.SendScope)
        if current == self._saved_controls:
            return False
        values = {REDUCTION_KEY: max(0, min(100, int(self.ReductionPercent)))}
        kind = int(self.ExportType)
        if 0 <= kind < len(KINDS):
            values[KIND_KEY] = KINDS[kind]
        scope = int(self.SendScope)
        if 0 <= scope < len(SEND_SCOPES):
            values[SEND_SCOPE_KEY] = SEND_SCOPES[scope]
        if save_state(values):
            self._saved_controls = current
        return False

    def _voxel_targets_under(self, roots):
        """The leaf volumes under these nodes, hidden or unreadable ones skipped.

        Leaves only: a node with children is packaging (the group 3D-Coat wraps an
        import in), and converting it would leave a stray extra volume behind.
        Returns (targets, skipped branch count); never raises, bounded.
        """
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

        for element in roots:
            try:
                walk(element)
            except Exception:
                continue
        return targets, hidden[0]

    def _visible_voxel_targets(self):
        """Every object the Sculpt Tree is showing right now - what the readout counts."""
        try:
            root = coat.Scene.sculptRoot()
        except Exception:
            return [], 0
        # the sculpt root is the container, never an object: walking from it would
        # treat an empty tree as one node whose volume cannot be read
        try:
            count = root.childCount()
        except Exception:
            count = 0
        roots = []
        for index in range(count):
            try:
                roots.append(root.child(index))
            except Exception:
                continue
        return self._voxel_targets_under(roots)

    def _selected_voxel_targets(self):
        """The volumes under the Sculpt Tree's selection, children included.

        When the build cannot report a selection the current node stands in for it -
        the same fallback a send makes - and the status line says which happened.
        Returns (targets, skipped branch count, "selection" or "current").
        """
        roots = []
        how = "selection"
        if scoped_export is not None:
            try:
                roots = [element for element in scoped_export.selected_nodes(coat)
                         if element is not None]
            except Exception:
                roots = []
        if not roots:
            how = "current"
            try:
                current = coat.Scene.current()
            except Exception:
                current = None
            if current is not None:
                roots = [current]
        targets, hidden = self._voxel_targets_under(roots)
        return targets, hidden, how

    def refresh_stats(self):
        """The object readouts, gathered at explicit moments and never during a redraw."""
        try:
            self.RefreshStats()
        except Exception:
            pass

    def SelectedToVoxel(self):
        """Turn the selected Sculpt Tree volumes into voxel volumes.

        The import mode is not ours to force - 3D-Coat decides that from import.txt -
        and it has been handing models over in surface mode whatever the mode line
        says.  This is the one click that puts what you selected where the sculpting
        tools want it: the selected nodes and their children, leaves only.  Objects
        that are already voxelized are counted and left alone, a failure is a sentence
        in the status line rather than an exception.
        """
        targets, hidden, how = self._selected_voxel_targets()
        if not targets and not hidden:
            self.status = ("Nothing selected to convert" if how == "selection"
                           else "Nothing in the Sculpt Tree to convert")
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
        if how == "current":
            parts.append("no selection to read, used the current node")
        self.status = "Selected To Voxel: " + (", ".join(parts) if parts else "nothing to do")
        log(self.status)
        self.refresh_stats()

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
            self.StatsLabel = "Snapshot: %d faces%s" % (count, self.volume_mode(volume))
        except Exception as exc:
            self.StatsLabel = "Statistics unavailable: %s" % exc

    def mode_summary(self):
        """How many of the visible tree objects are still surfaces.

        The number the user asked for: after an import it is not obvious how much of
        the scene is in surface mode, and that is what decides whether `Selected To
        Voxel` still has work to do.  Explicit action only - it walks the tree, which
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
        return "%d of %d visible objects in surface mode" % (surface, counted)

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
        # Empty while nothing waits: the panel draws a queue row only when there is a
        # queue, so an idle panel says nothing rather than saying "nothing".
        self.QueueLabel = ("Queue: %s waiting - press Import" % os.path.basename(queued)
                           if queued else "")
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

        if export_kind() == "paint":
            self._export_paint(root, path)
            return

        if send_scope() == "selected":
            self._export_selected(root, path)
            return

        exported = self._export_via_applink(path)
        if exported:
            write_shader_map(root, model=path)
            remove_paint_map(root)      # a paint record must not outlive the paint export
            self._report("Exported to Blender via the AppLink target (visible objects)" + export_note(),
                         "folder: %s" % app_folder(root))
            return
        exported = self._export_direct(path)
        if exported:
            write_shader_map(root, model=path)
            remove_paint_map(root)      # a paint record must not outlive the paint export   # before the signal: see _export_selected
            write_signal(root, path)
            self._report("Exported to Blender: %s (visible objects)%s" % (os.path.basename(path), export_note()),
                         "folder: %s" % app_folder(root))
            return
        self._report("Export failed", "use File > Export To > %s, or check the console" % APP_FOLDER)

    def _export_selected(self, root, path):
        """Send the nodes selected in the sculpt tree, plus their children.

        One node or several: 3D-Coat's own tree selection is what says which, and the
        mesh extraction takes all_selected explicitly, so nothing else in the scene can
        leave by accident.  There is deliberately no fallback to the whole-scene export:
        a bridge that quietly sends more than you selected is worse than one that tells
        you to select a node.
        """
        if scoped_export is None:
            self._report("Export helper missing", "reinstall the 3D-Coat scripts")
            return
        try:
            names, faces, chosen = scoped_export.export_subtree(coat, path, reduction_percent(),
                                                                MODEL_NAME)
        except Exception as exc:
            self._report("Nothing sent: %s" % exc, "select a node in the Sculpt Tree")
            log("selected-node export refused: %s" % exc)
            return
        # the map goes down before the signal: Blender polls the signal every couple of
        # seconds, and a signal that arrives before the map would arrive with no materials
        write_shader_map(root, names, path)
        remove_paint_map(root)          # ditto: this trip is not a paint export
        write_signal(root, path)
        what = "selected node + subtree" if chosen <= 1 else "%d selected nodes + subtrees" % chosen
        self._report("Exported %s: %s (%s)%s"
                     % (os.path.basename(path), ", ".join(names), what, reduction_note()),
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
        self._report("Imported %s from %s" % (name, os.path.basename(model)), note)

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

    def _export_paint(self, root, path):
        """Send the painting room's mesh, with its textures, through 3D-Coat's dialog.

        A different export, not a variant of the sculpt one: a painted model carries UVs
        and textures, the volumes in the Sculpt Tree carry neither.  This is the route
        3D-Coat's own template uses for the job (PythonAPI/Templates/py_Export/
        Autoexport.py): ask the dialog for geometry and textures, point its texture
        folder at the folder the model goes to, then press Export.  It is the only route
        that carries texture files out at all.

        What the dialog cannot say is which paint object a material belongs to - the .mtl
        it writes has empty material names - so the names are read from the PaintRoom API
        and written beside the model for the Blender side to build from.

        The stamped file is what says whether *this* call wrote anything: reporting a
        previous export as the one just sent is the worst thing this bridge could do.
        """
        if CMD is None:
            self._report("Export failed", "no CMD api in this build")
            return False
        before = file_stamp(path)
        try:
            notes = [part for part in (apply_reduction(), apply_textures(True),
                                       apply_texture_folder(app_folder(root))) if part]
            if notes:
                log("paint export settings: %s" % " | ".join(notes))
            CMD.ExportObjectsAndTextures(path)
            coat.io.step(4)
        except Exception as exc:
            log("paint export: %s: %s" % (type(exc).__name__, exc))
            self._report("Export failed", "3D-Coat's paint export raised - see the log")
            return False
        after = file_stamp(path)
        if after is None or after == before:
            log("paint export: 3D-Coat wrote nothing to %s" % os.path.basename(path))
            self._report("Export failed", "no paint model was written - see the log")
            return False
        # a shader map describes a sculpt export; this trip is a paint one, so a stale
        # map must go or the returning model would be given a display shader as well
        remove_shader_map(root)
        recorded = write_paint_map(root, model=path)   # before the signal: see _export_selected
        write_signal(root, path)
        self._report("Exported paint objects to Blender: %s%s"
                     % (os.path.basename(path), export_note()),
                     "folder: %s | %d material(s) recorded"
                     % (app_folder(root), len((recorded or {}).get("materials", []))))
        return True

    def _export_direct(self, path):
        """3D-Coat's own exporter, for the whole scene.

        The file name is fixed, so the previous send left a file of the same name behind:
        its stamp is what says whether *this* call wrote anything.  Reporting an old model
        as the one just sent is the worst thing this bridge could do - the artist would get
        back what they sent minutes ago, and nothing about it would look wrong.
        """
        if CMD is None:
            return False
        before = file_stamp(path)
        try:
            notes = [part for part in (apply_reduction(), apply_textures()) if part]
            if notes:
                log("export settings: %s" % " | ".join(notes))
            CMD.ExportObjectsAndTextures(path)
            coat.io.step(4)
        except Exception:
            return False
        after = file_stamp(path)
        if after is None:
            log("export: no %s was written" % os.path.basename(path))
            return False
        if after == before:
            log("export: %s is unchanged - the exporter wrote nothing"
                % os.path.basename(path))
            return False
        return True

    def _report(self, status, detail):
        log(status + (" | " + detail if detail else ""))
        self.status = status
        self.detail = detail
        try:
            # the queue readout is disk I/O, so only an explicit action refreshes it
            root = primary_root()
            queued = read_import_model(root) if root else ""
            self.QueueLabel = ("Queue: %s waiting - press Import" % os.path.basename(queued)
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
    """Put the Scripts entry into 3D-Coat's own menu list.

    This used to be an ``ExtraMenuItems`` XML and nothing else.  On the machine this is
    developed against that file is written, and read at every start, and the entry still
    never appears - while a run-time ``coat.ui.insertInMenu`` shows up straight away and
    survives, because 3D-Coat records the insertion itself.  So the insertion is the
    route now and the XML is retired; the guard matters because an id that is both
    declared in the XML and inserted at run time is listed *twice*, and because every
    start would otherwise add another copy.
    """
    try:
        coat.ui.addTranslation(MENU_ID, PANEL_CAPTION)
    except Exception:
        pass
    try:
        import CoatLinkMenu
        CoatLinkMenu.retire_menu_xml()
    except Exception as exc:
        log("could not retire the menu file: %s" % exc)
    if _menu_present(MENU_ID):
        log("menu entry already in place: %s" % MENU_ID)
        return []
    # 3D-Coat wants forward slashes here, exactly as in the XML it used to read
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "CoatLink_Setup.py").replace("\\", "/")
    try:
        coat.ui.insertInMenu(MENU_PATHS[0], MENU_ID, script)
    except Exception as exc:
        log("could not insert the menu entry: %s" % exc)
        return []
    log("inserted the menu entry: %s > %s" % (MENU_PATHS[0], MENU_ID))
    return ["menu"]


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
