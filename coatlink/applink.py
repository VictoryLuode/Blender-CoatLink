# SPDX-License-Identifier: GPL-3.0-or-later
#
# CoatLink - a small, predictable Blender <-> 3D-Coat model bridge.
# Copyright (C) 2026  VictoryLuode
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.

"""3D-Coat AppLink protocol - the two files that matter.

    <root>/import.txt                    job file: what to load, nothing else
    <root>/CoatLinkBridge/              our folder: the model goes here
    <root>/CoatLinkBridge/export.txt    3D-Coat writes it when it sends a model back

3D-Coat registers more than one root (it logs both on startup):

    Documents/AppLinks/3D-Coat/Exchange   the shared one: jobs in, returns out
    Documents/3DCoat/Exchange             its own root, watched but not written to

Measured on 3D-Coat 2025/2026: the job file is only polled in the ROOT (a copy
inside the app folder is ignored), and an export made with File > Export To >
<App> lands in <app folder> of 3D-Coat's own root.  So: write the job to the
primary root, look for the return in every root's app folder.

Measured again, live: 3D-Coat's engine picks the job file up from the AppLinks
root only - a job written into Documents/3DCoat/Exchange sat there untouched for
two minutes.  The AppLinks root is therefore the primary for the whole bridge:
this add-on writes its job there and the 3D-Coat script
(coat_side/CoatLinkLib.py) writes its returns there too, so a return lands on
the very file the send wrote and there is one file to look at.

Reference: "3D-Coat AppLinks specifications" (applinks.rst), shipped with
3D-Coat in UserPrefs/PythonAPI/docs/source/.
"""

import ctypes
import glob
import json
import os
import platform
import subprocess
import time

from . import after_import

# Folder name that shows up in 3D-Coat's File > Export To menu.  Kept separate
# from the official AppLink folder ("Blender") so both add-ons can coexist, and
# deliberately not the add-on's own name: "CoatLink" in the export list and
# "CoatLink" in 3D-Coat's Scripts menu read as one thing and are not.
APP_FOLDER = "CoatLinkBridge"

#: what the export target was called before the rename, oldest first.  The name
#: 3D-Coat lists comes from the run.txt marker inside the folder, so the old entry
#: leaves the menu only once that marker is gone - see retire_legacy_app_folders().
LEGACY_APP_FOLDERS = ("CoatLink",)

#: What the 3D-Coat half writes beside the model: which shader each exported node
#: carries.  A sculpt shader is 3D-Coat's *display* shading, its exporters write no
#: material names at all ("usemtl " with nothing after it), so this file is the only
#: place the shader-to-object assignment survives the trip.  The 3D-Coat half
#: (coat_side/CoatLinkLib.py) carries the same constant.
SHADER_MAP_NAME = "shaders.json"
#: what the 3D-Coat half writes beside a *paint* export: the painting room's own object
#: and material names and its texture sets - none of which the exported model carries
PAINT_MAP_NAME = "paint.json"

_MODEL_NAME = "bridge"
_COAT_EXE = "3DCoatGL64.exe"

#: 3D-Coat names its user data folder after the version on recent builds
#: (3DCoat2025, 3DCoat2026) and carried a hyphen in the 4.x line (3D-CoatV48),
#: so the name is matched rather than assumed.
_COAT_DATA_PREFIXES = ("3dcoat", "3d-coat")


def _windows_documents():
    """The real Documents folder, which may be relocated (spec, Application 3).

    ``COATLINK_DOCS`` names it outright - the override the installer's doors and
    the 3D-Coat half honour too, and how the test suite stands in for another
    machine.
    """
    override = os.environ.get("COATLINK_DOCS")
    if override:
        return override
    try:
        import ctypes.wintypes as wintypes

        buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
        # CSIDL_PERSONAL = 5
        if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0:
            return buf.value or None
    except Exception:
        pass
    return None


def _documents_bases():
    """Every place a 3D-Coat folder may live, most likely first."""
    home = os.path.expanduser("~")
    bases = []
    if platform.system() == "Windows":
        docs = _windows_documents()
        if docs:
            bases.append(docs)
    bases.append(os.path.join(home, "Documents"))
    if platform.system() not in ("Windows", "Darwin"):
        bases = [home]
    return [os.path.normpath(base) for base in dict.fromkeys(bases)]


def _looks_like_coat_data(path):
    """A 3D-Coat user data folder, not merely a folder carrying the name.

    The real folders hold ``UserPrefs`` (2021+) or ``Exchange``/``data``; a folder
    we have written our own state file into counts too, because that is the one a
    running 3D-Coat handed the settings to.
    """
    for name in ("UserPrefs", "Exchange", "data"):
        if os.path.isdir(os.path.join(path, name)):
            return True
    return os.path.isfile(os.path.join(path, "CoatLink.json"))


def coat_data_dirs():
    """3D-Coat's user data folders, the one in use first.

    A folder 3D-Coat has already written to (it holds ``CoatLink.json``) is the
    one in use; after that the newest name wins, because a machine can hold
    3DCoat2025 and 3DCoat2026 side by side.
    """
    found = []
    for base in _documents_bases():
        try:
            names = os.listdir(base)
        except OSError:
            continue
        for name in names:
            if not name.lower().startswith(_COAT_DATA_PREFIXES):
                continue
            path = os.path.join(base, name)
            if os.path.isdir(path) and _looks_like_coat_data(path):
                found.append(path)
    found.sort(key=lambda path: (os.path.isfile(os.path.join(path, "CoatLink.json")),
                                 os.path.basename(path).lower()),
               reverse=True)
    return found


def _candidate_exchange_folders():
    """Exchange roots in preference order (the one jobs are read from first).

    AppLinks/3D-Coat/Exchange leads because that is the only root 3D-Coat's
    engine polls for the job file - measured live, a job left in
    3DCoat/Exchange was never picked up.  The 3D-Coat script side leads with it
    too, so a return lands on the very bridge.obj the send wrote.  Every user
    data folder 3D-Coat actually has follows, so a renamed one (``3DCoat2025`` /
    ``3DCoat2026``) is not missed.
    """
    roots = []
    for base in _documents_bases():
        roots.append(os.path.join(base, "AppLinks", "3D-Coat", "Exchange"))
    for folder in coat_data_dirs():
        roots.append(os.path.join(folder, "Exchange"))
    roots.append(os.path.join(_documents_bases()[0], "3DCoat", "Exchange"))
    return [os.path.normpath(root) for root in dict.fromkeys(roots)]


def _existing(paths):
    return [path for path in paths if os.path.isdir(path)]


def resolve_exchange(configured=""):
    """The root the job file goes to.

    An explicitly configured folder is always honoured - even when it is wrong -
    so a typo surfaces as an error instead of silently writing somewhere else.
    """
    if configured:
        return os.path.normpath(configured)
    existing = _existing(_candidate_exchange_folders())
    return existing[0] if existing else _candidate_exchange_folders()[0]


def detect_exchange(configured=""):
    """Best guess for "where is 3D-Coat's exchange folder right now"."""
    if configured and os.path.isdir(configured):
        return os.path.normpath(configured)
    existing = _existing(_candidate_exchange_folders())
    if existing:
        return existing[0]
    return os.path.normpath(configured) if configured else _candidate_exchange_folders()[0]


def exchange_roots(configured=""):
    """Every exchange root worth watching, the primary one first."""
    primary = resolve_exchange(configured)
    roots = [primary]
    for path in _existing(_candidate_exchange_folders()):
        if os.path.normcase(path) not in [os.path.normcase(root) for root in roots]:
            roots.append(path)
    return roots


def app_folder(root):
    return os.path.join(root, APP_FOLDER)


def app_folder_names():
    """Every folder name of ours, the current one first."""
    return (APP_FOLDER,) + LEGACY_APP_FOLDERS


def is_our_folder(path, roots):
    """Is ``path`` a file inside one of our folders under one of ``roots``?

    A pre-rename folder counts.  A model 3D-Coat handed back before the rename is
    still this bridge's model, and refusing it would strand the transfer.
    """
    folder = os.path.normcase(os.path.normpath(os.path.dirname(path)))
    for root in roots:
        for name in app_folder_names():
            if folder == os.path.normcase(os.path.normpath(os.path.join(root, name))):
                return True
    return False


def retire_legacy_app_folders(root):
    """Take the old target name off 3D-Coat's File > Export To menu.

    The menu entry comes from the run.txt marker inside the folder, not from the
    folder itself (measured: a folder renamed to ``*.removed`` while keeping its
    marker is still listed), so deleting the marker is what retires a name.  The
    folder and everything in it stay: a returned model still sits where the
    export.txt naming it points, which is also where is_our_folder() looks.
    """
    notes = []
    for name in LEGACY_APP_FOLDERS:
        folder = os.path.join(root, name)
        marker = os.path.join(folder, "run.txt")
        if not os.path.isfile(marker):
            continue
        try:
            os.remove(marker)
        except OSError as exc:
            notes.append("could not retire the old export target %s (%s)" % (folder, exc))
            continue
        notes.append("retired the old export target %s: its run.txt marker is gone" % folder)
    return notes


def carry_legacy_file(root, name, folder=None):
    """Bring a file of ours over from a pre-rename folder, and answer with its path.

    The pull record is the reason this exists: its keys are absolute model paths,
    so it survives the folder change, while leaving it behind would let an old
    signal import the same model a second time.  A file already in the new folder
    wins - it is the newer one by definition of having been written there.
    """
    folder = folder or app_folder(root)
    target = os.path.join(folder, name)
    if os.path.isfile(target):
        return target
    for legacy in LEGACY_APP_FOLDERS:
        source = os.path.join(root, legacy, name)
        if os.path.isfile(source):
            try:
                os.replace(source, target)
            except OSError:
                pass
            break
    return target


def _log_shared(message):
    """One line into the log both halves write; logging never breaks a transfer."""
    try:
        path = shared_log_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8", newline="\n") as handle:
            handle.write("%s | blender | %s\n" % (time.strftime("%H:%M:%S"), message))
    except Exception:
        pass


def model_path(root, extension=None, name=_MODEL_NAME):
    """Single, fixed name inside the app folder - no per-send file names."""
    stem = name if not extension else "%s.%s" % (name, extension.lstrip("."))
    return os.path.join(app_folder(root), stem)


def shader_map_path(model):
    """The shader map beside a model file, "" when the model has no folder yet."""
    folder = os.path.dirname(model or "")
    if not folder:
        return ""
    return os.path.join(folder, SHADER_MAP_NAME)


def paint_map_path(model):
    """The paint-room record beside a model file, "" when it has no folder yet."""
    folder = os.path.dirname(model or "")
    if not folder:
        return ""
    return os.path.join(folder, PAINT_MAP_NAME)


def ensure_app_folder(root):
    """Create <root>/CoatLinkBridge/ with the one file AppLink requires.

    run.txt only has to exist (it may be empty) for 3D-Coat to list the target
    in File > Export To.  No extension.txt: measured on 3D-Coat 2026, it ignores
    it and hands back FBX.  Publishing the new name also retires the old one, so
    the export list never offers both.
    """
    folder = app_folder(root)
    os.makedirs(folder, exist_ok=True)
    marker = os.path.join(folder, "run.txt")
    if not os.path.isfile(marker):
        _write(marker, "")
    for note in retire_legacy_app_folders(root):
        _log_shared(note)
    return folder


def import_txt(root):
    """The job file.  It is polled in the root only, never in the app folder."""
    return os.path.join(root, "import.txt")


def foreign_job(root):
    """The model named by a job file in ``root`` that is *not* ours, or "".

    The official Blender AppLink queues its jobs in this very same ``import.txt``
    (its own source writes the model path first).  Writing ours on top of one is
    unavoidable - only one job file exists - but doing it quietly would look like
    a job that simply vanished, so the caller says so in the log.
    """
    try:
        with open(import_txt(root), "r", encoding="utf-8", errors="replace") as handle:
            first = handle.readline().strip().strip('"')
    except OSError:
        return ""
    if not first or first.startswith("["):
        return ""
    path = os.path.normpath(first)
    folder = os.path.normcase(os.path.normpath(os.path.dirname(path)))
    if folder == os.path.normcase(os.path.normpath(app_folder(root))):
        return ""
    return path


def shared_log_path():
    """The log both sides of the bridge write to (the 3D-Coat user folder), so a
    scale mismatch or a silent failure can be diagnosed in one place.

    The same folder the 3D-Coat half picks for itself, so the two never end up
    writing one log each on a machine whose Documents folder moved.
    """
    folders = coat_data_dirs()
    if folders:
        return os.path.join(folders[0], "CoatLink.log")
    return os.path.join(_documents_bases()[0], "3DCoat", "CoatLink.log")


def signal_files(roots):
    """Where a returned model is announced, in every root.

    The app folder signal is ours by definition; the root one is an
    announcement that has to point into an app folder to be accepted.  A
    pre-rename folder is watched as well: a return 3D-Coat announced before the
    rename still counts, and the model it names is still on disk.
    """
    files = []
    for root in roots:
        for name in app_folder_names():
            files.append(os.path.join(root, name, "export.txt"))
        files.append(os.path.join(root, "export.txt"))
    return files


#: 3D-Coat parks an imported file under a parent node named after it (bridge.obj
#: -> "bridge"), which Blender has no equivalent of.  import.txt can run a python
#: file after the import (documented for 3D-Coat 2025.12+ as "[pythonfile ...]"),
#: so the job carries this script along: it moves the imported objects up to the
#: sculpt root and drops the empty parent, and the tree ends up like Blender's.
#: Kept as a real file next to this module so it can be read, compiled and tested.
AFTER_IMPORT_NAME = "CoatLink_AfterImport.py"
AFTER_IMPORT_SOURCE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "after_import.py")


def after_import_path(root):
    """Where the after-import script goes: next to the job file, in the root."""
    return os.path.join(root, AFTER_IMPORT_NAME)


def after_import_marker(root):
    """Where the helper says it started: beside itself, in the exchange root.

    The helper writes this before it touches anything, so it works even when the
    shared log cannot be reached from inside 3D-Coat - and its *absence* is not proof
    the step never ran, only a dated one from this trip is proof that it did.  See
    after_import_markers() for every note a trip can leave.
    """
    return after_import_path(root) + ".ran"


def import_shim_path(root):
    """The job's own import.py: the file 3D-Coat runs when it finds it there."""
    return os.path.join(root, after_import.IMPORT_SHIM_NAME)


def import_shim_marker(root):
    """Where that file says it started: beside itself, like the helper's own note."""
    return import_shim_path(root) + ".ran"


def after_import_markers(root):
    """Every note that says the after-import step started, in one list.

    Two files can leave one: the helper itself, and the job's ``import.py`` - which is
    the file 3D-Coat actually runs, and on some builds the only one that gets a chance
    to.  A note proves the step started, never that it worked.
    """
    return [after_import_marker(root), import_shim_marker(root)]


def write_after_import(root, voxelize=False):
    """Copy the helper into the exchange root; returns its path (or "" on failure).

    `voxelize` is baked into the copy rather than passed as an argument: import.txt
    can only name a python file, and the helper has to know whether this job asked for
    a voxel import.  The file in the add-on stays neutral, so tests can load it either
    way.
    """
    try:
        with open(AFTER_IMPORT_SOURCE, "r", encoding="utf-8") as handle:
            script = handle.read()
    except OSError:
        return ""
    if voxelize:
        marker = "VOXELIZE = False"
        if marker in script:
            script = script.replace(marker, "VOXELIZE = True", 1)
    target = after_import_path(root)
    tmp = target + ".tmp"
    _write(tmp, script)
    os.replace(tmp, target)
    return target


def write_import_shim(root):
    """Drop the import.py 3D-Coat runs itself; returns its path (or "" on failure).

    This is the working half of the after-import step.  The job file still names the
    helper with `[pythonfile ...]`, but that line is read without being executed on
    2025.17, so the unparenting rides on this file instead - the mechanism the shipped
    AppLinks spec describes, and the one 3D-Coat's own log shows it running.

    Written before import.txt: that file's appearance is what starts the import.
    """
    helper = after_import_path(root)
    if not os.path.isfile(helper):
        return ""
    script = after_import.import_shim_source(helper, import_shim_marker(root))
    target = import_shim_path(root)
    tmp = target + ".tmp"
    _write(tmp, script)
    os.replace(tmp, target)
    return target


def write_import_txt(root, load_path, return_path, mode, skip_dialogs=True):
    """Write the job file.  Must be the LAST file created: its appearance is
    what makes 3D-Coat start the import.

    [SkipImport]/[SkipExport] let 3D-Coat load and send back the model with its
    current settings instead of stopping at a dialog every time.  The last line hands
    3D-Coat the script that unparents the imported objects (see AFTER_IMPORT_SOURCE):
    it names the file for the engine's own directive, and the same script is dropped in
    beside the job as import.py, which is the file 3D-Coat runs by itself - the
    directive on its own does not run anything on 2025.17.

    """
    lines = [_slash(load_path), _slash(return_path), "[%s]" % mode]
    if skip_dialogs:
        lines.append("[SkipImport]")
        lines.append("[SkipExport]")
    helper = write_after_import(root, voxelize=(mode == "vox"))
    if helper:
        lines.append("[pythonfile %s]" % _slash(helper))
        write_import_shim(root)
    target = import_txt(root)
    tmp = target + ".tmp"
    _write(tmp, "\n".join(lines) + "\n")
    os.replace(tmp, target)  # atomic: 3D-Coat never sees a half written file
    return target


def read_export_paths(path):
    """Model paths listed in an export.txt (one per line and/or ';' separated)."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            raw = handle.read()
    except OSError:
        return []
    out = []
    for chunk in raw.replace("\r", "\n").replace(";", "\n").split("\n"):
        chunk = chunk.strip().strip('"')
        if not chunk or chunk.startswith("["):
            continue
        out.append(os.path.normpath(chunk))
    return out


def coat_state():
    """What the 3D-Coat side last wrote about itself (scene scale, units, the
    swap-Y/Z option) - it keeps this in its own state file, which we only read.

    Both applications run on the same machine, so this is how the Blender side
    learns 3D-Coat's settings without asking the user: the 3D-Coat side refreshes
    it on every action.
    """
    for folder in coat_data_dirs():
        path = os.path.join(folder, "CoatLink.json")
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            continue
        state = data.get("coat") if isinstance(data, dict) else None
        if isinstance(state, dict):
            return state
    return {}


def find_coat_executable():
    """Where 3D-Coat's executable is, on any machine.

    The uninstall entries come first because they know about an install that is
    not under Program Files at all (a folder of your own, another drive), then
    the Program Files folders this system spells, then every drive.
    """
    roots = list(registered_install_dirs())
    for name in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)"):
        value = os.environ.get(name)
        if value:
            roots.append(value)
    for letter in "abcdefghijklmnopqrstuvwxyz":
        for folder in ("Program Files", "Program Files (x86)"):
            roots.append("%s:\\%s" % (letter, folder))
    local = os.environ.get("LOCALAPPDATA")
    if local:
        roots.append(os.path.join(local, "Programs"))
        roots.append(local)
    found = []
    for root in dict.fromkeys(roots):
        if not root or not os.path.isdir(root):
            continue
        found += glob.glob(os.path.join(root, "3DCoat*", _COAT_EXE))
        found += glob.glob(os.path.join(root, "3D-Coat*", _COAT_EXE))
    return sorted(found)[-1] if found else ""


def registered_install_dirs():
    """3D-Coat folders Windows records, wherever they were installed."""
    if platform.system() != "Windows":
        return []
    try:
        import winreg
    except ImportError:
        return []
    keys = ((winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"))
    found = []
    for hive, subkey in keys:
        try:
            with winreg.OpenKey(hive, subkey) as key:
                names = [winreg.EnumKey(key, index) for index in range(winreg.QueryInfoKey(key)[0])]
        except OSError:
            continue
        for name in names:
            entry = os.path.join(subkey, name)
            values = {}
            for value_name in ("DisplayName", "InstallLocation", "DisplayIcon", "UninstallString"):
                try:
                    with winreg.OpenKey(hive, entry) as key:
                        values[value_name] = str(winreg.QueryValueEx(key, value_name)[0])
                except OSError:
                    continue
            label = ("%s %s" % (name, values.get("DisplayName", ""))).lower()
            if "3d-coat" not in label and "3dcoat" not in label:
                continue
            for value_name in ("InstallLocation", "DisplayIcon", "UninstallString"):
                text = values.get(value_name, "").strip()
                if not text:
                    continue
                if text.startswith('"'):
                    text = text[1:].split('"')[0]
                else:
                    text = text.split(",")[0].strip()
                text = os.path.expandvars(text)
                folder = text if os.path.isdir(text) else os.path.dirname(text)
                if folder:
                    found.append(folder)
    return found


def is_coat_running():
    """True/False on Windows, None when it cannot be determined.

    The output of tasklist is matched as bytes: on a non-English Windows it is
    encoded with the local code page, so decoding it would raise.
    """
    if platform.system() != "Windows":
        return None
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq %s" % _COAT_EXE],
            capture_output=True, timeout=10, creationflags=flags,
        ).stdout or b""
    except Exception:
        return None
    return _COAT_EXE.lower().encode("ascii") in out.lower()


def _slash(path):
    # The spec asks for '/' separators; 3D-Coat accepts them on every platform.
    return os.path.abspath(path).replace("\\", "/")


def _write(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
