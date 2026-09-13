# SPDX-License-Identifier: GPL-3.0-or-later
#
# Coat Bridge - a small, predictable Blender <-> 3D-Coat model bridge.
# Copyright (C) 2026  VictoryLuode
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.

"""3D-Coat AppLink protocol.

The protocol is file based.  Everything happens inside one exchange folder:

    <exchange>/import.txt          we write it  -> tells 3D-Coat what to load
    <exchange>/export.txt          3D-Coat writes it -> path of the returned model
    <exchange>/<App>/run.txt       marks <App> as a target of File > Export To
    <exchange>/<App>/export.txt    3D-Coat writes it when <App> was the target

Reference: "3D-Coat AppLinks specifications" (applinks.rst), shipped with
3D-Coat in UserPrefs/PythonAPI/docs/source/.
"""

import ctypes
import glob
import os
import platform
import subprocess

# Folder name that shows up in 3D-Coat's File > Export To menu.  It is kept
# separate from the official AppLink folder ("Blender") on purpose, so both
# add-ons can live side by side without fighting over the same files.
APP_FOLDER = "BlenderBridge"

# All files this bridge creates are prefixed, which makes "is this file ours?"
# a cheap and reliable question.
PREFIX = "coat_bridge"

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


def _candidate_exchange_folders():
    home = os.path.expanduser("~")
    system = platform.system()
    bases = []
    if system == "Windows":
        docs = _windows_documents()
        if docs:
            bases.append(os.path.join(docs, "AppLinks"))
        bases.append(os.path.join(home, "Documents", "AppLinks"))
    elif system == "Darwin":
        bases.append(os.path.join(home, "Documents", "AppLinks"))
    else:
        bases.append(os.path.join(home, "AppLinks"))
    return [os.path.normpath(os.path.join(b, "3D-Coat", "Exchange")) for b in bases]


def resolve_exchange(configured=""):
    """Effective exchange folder.

    An explicitly configured folder is always honoured - even when it is wrong -
    so a typo surfaces as an error instead of silently writing somewhere else.
    With no configuration the usual locations are probed.
    """
    if configured:
        return os.path.normpath(configured)
    existing = _first_existing()
    return existing or _candidate_exchange_folders()[0]


def detect_exchange(configured=""):
    """Best guess for "where is 3D-Coat's exchange folder right now"."""
    if configured and os.path.isdir(configured):
        return os.path.normpath(configured)
    existing = _first_existing()
    if existing:
        return existing
    return os.path.normpath(configured) if configured else _candidate_exchange_folders()[0]


def _first_existing():
    for path in _candidate_exchange_folders():
        if os.path.isdir(path):
            return path
    return ""


def app_folder(exchange):
    return os.path.join(exchange, APP_FOLDER)


def ensure_folders(exchange, extension="obj"):
    """Create <exchange>/<App>/ with the three files AppLink expects.

    run.txt must exist (it may be empty) for 3D-Coat to list the target in
    File > Export To; extension.txt tells 3D-Coat which format to hand back.
    """
    os.makedirs(exchange, exist_ok=True)
    folder = app_folder(exchange)
    os.makedirs(folder, exist_ok=True)
    _write(os.path.join(folder, "run.txt"), "")  # empty on purpose: never launches anything
    _write(os.path.join(folder, "extension.txt"), extension.lstrip("."))
    return folder


def import_txt(exchange):
    return os.path.join(exchange, "import.txt")


def export_txt_candidates(exchange):
    """Files 3D-Coat uses to signal "the model came back".

    Root export.txt is the documented return channel; the app folder one is
    written when 3D-Coat exported through File > Export To > <App>.
    """
    return [os.path.join(exchange, "export.txt"), os.path.join(app_folder(exchange), "export.txt")]


def write_import_txt(exchange, load_path, return_path, mode, skip_dialogs=True):
    """Write the job file.  Must be the LAST file created: its appearance is
    what makes 3D-Coat start the import.

    [SkipImport]/[SkipExport] let 3D-Coat load and send back the model with its
    current settings instead of stopping at a dialog every time.
    """
    lines = [_slash(load_path), _slash(return_path), "[%s]" % mode]
    if skip_dialogs:
        lines.append("[SkipImport]")
        lines.append("[SkipExport]")
    target = import_txt(exchange)
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


def find_coat_executable():
    roots = [
        os.environ.get("ProgramFiles"),
        os.environ.get("ProgramW6432"),
        r"C:\Program Files",
        r"D:\Program Files",
        r"C:\Program Files (x86)",
        r"D:\Program Files (x86)",
    ]
    found = []
    for root in dict.fromkeys(filter(None, roots)):
        found += glob.glob(os.path.join(root, "3DCoat*", _COAT_EXE))
    return sorted(found)[-1] if found else ""


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
