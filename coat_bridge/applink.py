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

    <root>/import.txt                 job file: what to load, nothing else
    <root>/BlenderBridge/             our folder: the model goes here
    <root>/BlenderBridge/export.txt   3D-Coat writes it when it sends a model back

3D-Coat registers more than one root (it logs both on startup):

    Documents/AppLinks/3D-Coat/Exchange   reads job files here
    Documents/3DCoat/Exchange             writes its exports here

Measured on 3D-Coat 2026: the job file is only polled in the ROOT (a copy inside
the app folder is ignored), and an export made with File > Export To > <App>
lands in <app folder> of 3D-Coat's own root.  So: write the job to the primary
root, look for the return in every root's app folder.

Reference: "3D-Coat AppLinks specifications" (applinks.rst), shipped with
3D-Coat in UserPrefs/PythonAPI/docs/source/.
"""

import ctypes
import glob
import json
import os
import platform
import subprocess

# Folder name that shows up in 3D-Coat's File > Export To menu.  Kept separate
# from the official AppLink folder ("Blender") so both add-ons can coexist.
APP_FOLDER = "BlenderBridge"

_MODEL_NAME = "bridge"
_COAT_EXE = "3DCoatGL64.exe"


def _windows_documents():
    """The real Documents folder, which may be relocated (spec, Application 3)."""
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


def _candidate_exchange_folders():
    """Exchange roots in preference order (the one jobs are read from first)."""
    roots = []
    for base in _documents_bases():
        roots.append(os.path.join(base, "AppLinks", "3D-Coat", "Exchange"))
        roots.append(os.path.join(base, "3DCoat", "Exchange"))
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


def model_path(root, extension=None, name=_MODEL_NAME):
    """Single, fixed name inside the app folder - no per-send file names."""
    stem = name if not extension else "%s.%s" % (name, extension.lstrip("."))
    return os.path.join(app_folder(root), stem)


def ensure_app_folder(root):
    """Create <root>/BlenderBridge/ with the one file AppLink requires.

    run.txt only has to exist (it may be empty) for 3D-Coat to list the target
    in File > Export To.  No extension.txt: measured on 3D-Coat 2026, it ignores
    it and hands back FBX.
    """
    folder = app_folder(root)
    os.makedirs(folder, exist_ok=True)
    marker = os.path.join(folder, "run.txt")
    if not os.path.isfile(marker):
        _write(marker, "")
    return folder


def import_txt(root):
    """The job file.  It is polled in the root only, never in the app folder."""
    return os.path.join(root, "import.txt")


def shared_log_path():
    """The log both sides of the bridge write to (the 3D-Coat user folder), so a
    scale mismatch or a silent failure can be diagnosed in one place."""
    return os.path.join(_documents_bases()[0], "3DCoat", "CoatBridge.log")


def signal_files(roots):
    """Where a returned model is announced, in every root.

    The app folder signal is ours by definition; the root one is an
    announcement that has to point into an app folder to be accepted.
    """
    files = []
    for root in roots:
        files.append(os.path.join(app_folder(root), "export.txt"))
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


def write_import_txt(root, load_path, return_path, mode, skip_dialogs=True):
    """Write the job file.  Must be the LAST file created: its appearance is
    what makes 3D-Coat start the import.

    [SkipImport]/[SkipExport] let 3D-Coat load and send back the model with its
    current settings instead of stopping at a dialog every time.  The last line
    hands 3D-Coat the script that unparents the imported objects (see
    AFTER_IMPORT_SOURCE): it runs after the import, which is exactly when the
    parent node exists.

    """
    lines = [_slash(load_path), _slash(return_path), "[%s]" % mode]
    if skip_dialogs:
        lines.append("[SkipImport]")
        lines.append("[SkipExport]")
    helper = write_after_import(root, voxelize=(mode == "vox"))
    if helper:
        lines.append("[pythonfile %s]" % _slash(helper))
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
    for base in _documents_bases():
        path = os.path.join(base, "3DCoat", "CoatBridge.json")
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
