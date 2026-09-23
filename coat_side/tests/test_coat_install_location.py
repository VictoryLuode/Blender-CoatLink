# SPDX-License-Identifier: GPL-3.0-or-later
"""The installer must find 3D-Coat wherever it was put.

Not everyone installs 3D-Coat under ``C:\\Program Files`` - a folder of your own
and another drive are both normal - and not everyone keeps Documents at
``%USERPROFILE%\\Documents``: redirect it to OneDrive and 3D-Coat's data folder
(and the Python it ships) moves with it.  These checks pin both down, on this
machine's real registry where that is meaningful and on stubbed answers where it
is not.

  * a Documents folder that really holds ``3DCoat`` wins over the guess
  * a 3D-Coat folder anywhere on the machine is found, and one without a ``data``
    folder is not mistaken for an install
  * the uninstall entries are understood, quoted icon paths and all
  * nothing is returned when there is nothing to find
"""

import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
COAT_SIDE = HERE.parent
sys.path.insert(0, str(COAT_SIDE))

import CoatLinkInstall as install                       # noqa: E402

FAILURES = []


def check(name, ok, detail=None):
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> %r" % (detail,)))
    if not ok:
        FAILURES.append(name)


def make_install(root, has_data=True):
    """A folder that looks like a 3D-Coat install (the icons need ``data``)."""
    root.mkdir(parents=True, exist_ok=True)
    if has_data:
        (root / "data").mkdir(exist_ok=True)
    return root


def no_roots():
    return []


def nothing_registered():
    return []


def stubbed(module, name, value):
    original = getattr(module, name)
    setattr(module, name, value)
    return original


print("---- Documents: the shell's answer, then what really holds 3DCoat ----")
with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    redirected = tmp / "OneDrive" / "Documents"
    (redirected / "3DCoat" / "UserPrefs").mkdir(parents=True)
    original = stubbed(install, "shell_documents", lambda: redirected)
    try:
        check("redirected Documents wins when 3DCoat lives there",
              install.documents_dir() == redirected, install.documents_dir())
        check("user_prefs follows it",
              str(install.user_prefs()).replace("\\", "/").endswith("/3DCoat/UserPrefs"),
              install.user_prefs())
    finally:
        stubbed(install, "shell_documents", original)

    plain = tmp / "plain"
    (plain / "3DCoat" / "UserPrefs").mkdir(parents=True)
    original = stubbed(install, "shell_documents", lambda: plain)
    try:
        check("a Documents folder with 3DCoat is used as it comes",
              install.documents_dir() == plain, install.documents_dir())
    finally:
        stubbed(install, "shell_documents", original)

    # the bridge writes its own log into a bare 3DCoat folder, and taking that for
    # 3D-Coat's data would send the next upgrade to a folder 3D-Coat never reads
    decoy = tmp / "decoy"
    (decoy / "3DCoat").mkdir(parents=True)
    (decoy / "3DCoat" / "CoatLink.log").write_text("", encoding="utf-8")
    check("a bare 3DCoat folder (only our own log) is not 3D-Coat data",
          install.coat_data_dirs(decoy) == [], install.coat_data_dirs(decoy))

    real = tmp / "real"
    (real / "3DCoat2026" / "UserPrefs").mkdir(parents=True)
    check("a versioned data folder is recognised",
          [folder.name for folder in install.coat_data_dirs(real)] == ["3DCoat2026"],
          install.coat_data_dirs(real))

    both = tmp / "both"
    (both / "3DCoat2025" / "UserPrefs").mkdir(parents=True)
    (both / "3DCoat2026" / "UserPrefs").mkdir(parents=True)
    original = stubbed(install, "shell_documents", lambda: both)
    try:
        check("the newest versioned data folder wins",
              install.coat_data_dir().name == "3DCoat2026", install.coat_data_dir())
        check("user_prefs follows the newest one",
              str(install.user_prefs()).replace("\\", "/").endswith("/3DCoat2026/UserPrefs"),
              install.user_prefs())
    finally:
        stubbed(install, "shell_documents", original)

    original = stubbed(install, "shell_documents", lambda: tmp / "nowhere")
    try:
        found = install.documents_dir()
        check("with nothing to go on, a folder that has 3DCoat is still preferred",
              install.coat_data_dirs(found) or not any(
                  install.coat_data_dirs(candidate) for candidate in
                  [tmp / "OneDrive" / "Documents", tmp / "real", tmp / "both",
                   Path(os.path.expanduser("~")) / "Documents"]),
              found)
    finally:
        stubbed(install, "shell_documents", original)

print("---- program_dir: any install location, data folder required ----")
with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    custom = make_install(tmp / "Apps" / "3DCoat-9999")
    saved = (stubbed(install, "registry_program_dirs", nothing_registered),
             stubbed(install, "environment_program_roots", no_roots),
             stubbed(install, "drive_program_roots", no_roots),
             stubbed(install, "user_program_roots", no_roots))
    try:
        check("nothing found means None", install.program_dir() is None, install.program_dir())
    finally:
        for name, value in zip(("registry_program_dirs", "environment_program_roots",
                                "drive_program_roots", "user_program_roots"), saved):
            stubbed(install, name, value)

    saved = (stubbed(install, "registry_program_dirs", lambda: [custom]),
             stubbed(install, "environment_program_roots", no_roots),
             stubbed(install, "drive_program_roots", no_roots),
             stubbed(install, "user_program_roots", no_roots))
    try:
        check("an install outside Program Files is found through the registry",
              install.program_dir() == custom, install.program_dir())
    finally:
        for name, value in zip(("registry_program_dirs", "environment_program_roots",
                                "drive_program_roots", "user_program_roots"), saved):
            stubbed(install, name, value)

    fake = tmp / "ProgramFiles" / "3DCoat-9998"
    fake.mkdir(parents=True)                     # a folder, but not an install
    saved = (stubbed(install, "registry_program_dirs", lambda: [fake]),
             stubbed(install, "environment_program_roots", no_roots),
             stubbed(install, "drive_program_roots", no_roots),
             stubbed(install, "user_program_roots", no_roots))
    try:
        check("a folder without data/ is not mistaken for an install",
              install.program_dir() is None, install.program_dir())
    finally:
        for name, value in zip(("registry_program_dirs", "environment_program_roots",
                                "drive_program_roots", "user_program_roots"), saved):
            stubbed(install, name, value)

print("---- uninstall values, as Windows writes them ----")
folder = install._folder_from_registry_value(r'"C:\Program Files\3DCoat-2025\display.ico"')
check("a quoted display icon gives its folder",
      str(folder) == r"C:\Program Files\3DCoat-2025", folder)
folder = install._folder_from_registry_value(r'"C:\Program Files\3DCoat-2025\display.ico",0')
check("the ,0 suffix does not upset it",
      str(folder) == r"C:\Program Files\3DCoat-2025", folder)
folder = install._folder_from_registry_value(r"C:\Apps\3DCoat-2025")
check("a bare folder stays itself", str(folder) == r"C:\Apps\3DCoat-2025", folder)
folder = install._folder_from_registry_value(r'"C:\Apps\3DCoat 2025\uninstall.exe" /S')
check("a quoted uninstaller gives the folder above it",
      str(folder) == r"C:\Apps\3DCoat 2025", folder)
check("empty values give None", install._folder_from_registry_value("") is None)
check("missing values give None", install._folder_from_registry_value(None) is None)

print("---- real machine, real registry: whatever is found must be usable ----")
found = install.program_dir()
check("program_dir answers with a folder that has data/ (or nothing at all)",
      found is None or (Path(found) / "data").is_dir(), found)
check("registry_program_dirs returns a list", isinstance(install.registry_program_dirs(), list))
check("drive_program_roots returns a list", isinstance(install.drive_program_roots(), list))
check("user_program_roots returns a list", isinstance(install.user_program_roots(), list))
check("shell_documents returns a path or None",
      install.shell_documents() is None or isinstance(install.shell_documents(), Path),
      install.shell_documents())

# every registry folder that claims to be an install must actually look like one
for candidate in install.registry_program_dirs():
    path = Path(candidate)
    check("registry entry is a real folder: %s" % path.name, path.is_dir(), candidate)

print()
if FAILURES:
    print("FAILED %d check(s): %s" % (len(FAILURES), ", ".join(FAILURES)))
    sys.exit(1)
print("all install-location checks passed")
