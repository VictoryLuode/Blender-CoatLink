# SPDX-License-Identifier: GPL-3.0-or-later
#
# CoatLink - a small, predictable Blender <-> 3D-Coat model bridge.

"""Install (or remove) the 3D-Coat half of CoatLink.

It installs it the way a ``.3dcpack`` does: as an extension, into
``<scripts>/cExtensions/CoatLink``, with the name added to
``<scripts>/cExtensions/startup.txt``.  The two ``ExtraMenuItems`` XML files are
*not* installed - they carry absolute ``script:`` paths, so a package cannot hold
them - and are written by the extension itself the first time 3D-Coat starts it
(``coat_side/CoatLinkMenu.py``), which also moves an install of an older build out
of the way.

Three ways in, one implementation:

* from an unzipped release or a checkout, by double-clicking ``install.cmd``
  (Windows) or running ``./install.sh`` / ``./install.ps1``
* straight from this file on 3D-Coat's own Python
* from inside 3D-Coat, if you prefer its console::

      exec(open(r"...\\CoatLinkInstall.py", encoding="utf-8").read())

Both folders are worked out on the spot - no path is baked into anything - and
nothing outside 3D-Coat's user folder is written: the tool buttons take 3D-Coat's
default icon rather than installing one into the program folder.
"""

import argparse
import json
import os
import string
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

#: the folder our scripts live in, under 3D-Coat's Scripts folder
APP_DIRNAME = "CoatLink"

#: what we install - the whole 3D-Coat half, entry point included, because a
#: .3dcpack would carry exactly these files into Scripts/cExtensions/CoatLink
SCRIPT_FILES = (
    "CoatLink.py",
    "CoatLinkLib.py",
    "CoatLinkMenu.py",
    "CoatLinkReceipts.py",
    "CoatLinkScopedExport.py",
    "CoatLink_Send.py",
    "CoatLink_Pull.py",
    "CoatLink_Setup.py",
)

ICON_FILES = (
    "CoatLink.png",
    "CoatLink_Send.png",
    "CoatLink_Pull.png",
    "CoatLink_Setup.png",
)

MENU_FILES = ("CoatLink.xml", "CoatLinkTools.xml")

#: layouts this project used before; removed on sight so an upgrade cannot leave
#: a second copy of the bridge behind
STALE_FILES = (
    "CoatLink.py",
    "CoatLinkQt.py",
    "CoatLinkDialog.py",
)

#: what a release from before the rename installed (`CoatBridge`): a whole second copy of
#: the scripts, the two XML files that make its buttons, and its icons.  The scripts folder
#: is moved aside (never deleted); the XML and the icons go, because they would keep drawing
#: buttons that point at scripts which are no longer there.
LEGACY_APP_DIRNAME = "CoatBridge"
LEGACY_MENU_FILES = ("CoatBridge.xml", "CoatBridgeTools.xml")
LEGACY_ICON_FILES = (
    "CoatBridge.png",
    "CoatBridge_Send.png",
    "CoatBridge_Pull.png",
    "CoatBridge_Setup.png",
)

TOOLS_TEMPLATE = "tools/CoatLinkTools.xml.in"
PLACEHOLDER = "__SCRIPT_DIR__"

MENU_XML = """<ClassArray.ExtraMenuItem>
\t<ExtraMenuItem>
\t\t<MenuPath>Scripts</MenuPath>
\t\t<MenuItem>CoatLink</MenuItem>
\t\t<inRoom></inRoom>
\t\t<inSection></inSection>
\t\t<Command>script:{script_dir}/CoatLink_Setup.py</Command>
\t</ExtraMenuItem>
</ClassArray.ExtraMenuItem>
"""


def windows_path(path):
    """3D-Coat's XML wants forward slashes, whatever the shell gave us."""
    return str(path).replace("\\", "/")


def user_prefs():
    """3D-Coat's user folder (``<Documents>/3DCoat/UserPrefs``).

    ``COATLINK_PREFS`` overrides it, which is how the tests point somewhere safe.
    The folder under Documents is the one 3D-Coat is really using - it is named
    after the version on recent builds (``3DCoat2025``, ``3DCoat2026``) - so it is
    looked up rather than assumed.
    """
    override = os.environ.get("COATLINK_PREFS")
    if override:
        return Path(override)
    data = coat_data_dir()
    if data is not None:
        return data / "UserPrefs"
    return documents_dir() / "3DCoat" / "UserPrefs"


def coat_data_dirs(base):
    """3D-Coat's user data folders directly below one Documents folder.

    The folder is named after the version on recent builds (``3DCoat2025``,
    ``3DCoat2026``) and carried a hyphen in the 4.x line (``3D-CoatV48``), so the
    name is matched, never assumed.  Only folders that really hold 3D-Coat's data
    count - see ``documents_dir``.
    """
    found = []
    try:
        names = os.listdir(base)
    except OSError:
        return found
    for name in names:
        lower = name.lower()
        if not (lower.startswith("3dcoat") or lower.startswith("3d-coat")):
            continue
        folder = Path(base) / name
        if (folder / "UserPrefs").is_dir() or (folder / "Scripts").is_dir():
            found.append(folder)
    return found


def coat_data_dir():
    """The 3D-Coat user data folder, or None when there is none yet."""
    folders = coat_data_dirs(documents_dir())
    if not folders:
        return None
    return sorted(folders, key=lambda path: path.name.lower())[-1]


def _registry_value(hive, subkey, name):
    """One registry value, or None - on any Windows, in any locale."""
    if os.name != "nt":
        return None
    try:
        import winreg
    except ImportError:
        return None
    try:
        with winreg.OpenKey(hive, subkey) as key:
            value = winreg.QueryValueEx(key, name)[0]
    except OSError:
        return None
    return None if value is None else str(value)


def _registry_subkeys(hive, subkey):
    """The names of the entries under one registry key, or []."""
    if os.name != "nt":
        return []
    try:
        import winreg
    except ImportError:
        return []
    try:
        with winreg.OpenKey(hive, subkey) as key:
            return [winreg.EnumKey(key, index) for index in range(winreg.QueryInfoKey(key)[0])]
    except OSError:
        return []


def shell_documents():
    """Windows' own idea of Documents, or None.

    Worth asking, because ``~/Documents`` is only a guess: redirect Documents to
    OneDrive and 3D-Coat keeps its data - and its bundled Python - somewhere else
    entirely.
    """
    if os.name != "nt":
        return None
    try:
        import winreg
    except ImportError:
        return None
    for subkey in (r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
                   r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders"):
        raw = _registry_value(winreg.HKEY_CURRENT_USER, subkey, "Personal")
        if raw:
            return Path(os.path.expandvars(raw))
    return None


def documents_dir():
    """Where 3D-Coat keeps its data.

    What Windows says first, then ``~/Documents``, then the OneDrive spellings of
    both - but a candidate that really holds 3D-Coat's user data wins over that
    order, so a redirected machine is followed rather than missed.

    Only a folder that looks like 3D-Coat's own counts (it has ``UserPrefs`` or
    ``Scripts`` inside).  A bare ``3DCoat`` folder is something else: the bridge
    writes its own log into one, and letting that hoist a candidate to the front
    would send the next upgrade to a folder 3D-Coat never reads.
    """
    home = Path(os.path.expanduser("~"))
    candidates = []
    shell = shell_documents()
    if shell:
        candidates.append(shell)
    candidates.append(home / "Documents")
    for var in ("OneDrive", "OneDriveCommercial", "OneDriveConsumer"):
        base = os.environ.get(var)
        if base:
            candidates += [Path(base) / "Documents", Path(base)]
    for candidate in candidates:
        if coat_data_dirs(candidate):
            return candidate
    return candidates[0]


def _folder_from_registry_value(value):
    """The folder a registry path value points at, or None.

    ``InstallLocation`` is already a folder; ``DisplayIcon`` is usually
    ``"C:\\Program Files\\3DCoat-2025\\display.ico"`` (sometimes with ``,0``) and
    ``UninstallString`` is the uninstaller - the parent folder is what the icons
    need, and the caller drops anything that does not turn out to be an install.
    """
    if not value:
        return None
    text = str(value).strip()
    if text.startswith('"'):
        text = text[1:].split('"')[0]
    else:
        text = text.split(",")[0].strip()
    path = Path(os.path.expandvars(text))
    return path.parent if path.suffix else path


def registry_program_dirs():
    """3D-Coat folders Windows knows about, wherever they were installed.

    A folder 3D-Coat's installer creates is often not under ``Program Files`` at
    all, and the uninstall entries are the only place that says where it went.
    """
    if os.name != "nt":
        return []
    try:
        import winreg
    except ImportError:
        return []
    hives = (winreg.HKEY_LOCAL_MACHINE,
             winreg.HKEY_LOCAL_MACHINE,
             winreg.HKEY_CURRENT_USER)
    subkeys = (r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
               r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
               r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall")
    found = []
    for hive, subkey in zip(hives, subkeys):
        for entry in _registry_subkeys(hive, subkey):
            lowered = entry.lower()
            if "3dcoat" not in lowered and "3d-coat" not in lowered:
                continue
            for name in ("InstallLocation", "DisplayIcon", "UninstallString"):
                folder = _folder_from_registry_value(
                    _registry_value(hive, "%s\\%s" % (subkey, entry), name))
                if folder is not None:
                    found.append(folder)
    return found


def environment_program_roots():
    """The Program Files folders as this system spells them.

    Reading the environment covers installs on a drive or in a folder that
    ``C:\\Program Files`` does not describe.
    """
    roots = []
    for var in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)"):
        value = os.environ.get(var)
        if value:
            roots.append(Path(value))
    return roots


def drive_program_roots():
    """``3DCoat*`` under Program Files on every drive, in both path spellings.

    Both on purpose: this installer normally runs on 3D-Coat's own Python (a
    Windows program, where ``/d/...`` is not a path) but an MSYS Python sees only
    the POSIX form.  A drive letter that does not exist costs one failed
    ``is_dir``.
    """
    roots = []
    for prefix in ("%s:/", "/%s/"):
        for letter in string.ascii_lowercase:
            root = Path(prefix % letter)
            try:
                if not root.is_dir():
                    continue
                for folder in ("Program Files", "Program Files (x86)"):
                    roots += sorted(root.glob("%s/3DCoat*" % folder))
                    roots += sorted(root.glob("%s/3D-Coat*" % folder))
            except OSError:
                # A drive Windows lists but will not answer for - a cloud drive, a card
                # reader with no card in it - raises out of the stat() behind glob():
                # measured on a machine with BaiduCloud's P: mapped, WinError 50 (the
                # request is not supported) out of Path.glob.  Skipping it is right:
                # a folder that cannot be read cannot hold the program folder either.
                continue
    return roots


def user_program_roots():
    """Per-user 3D-Coat installs - a per-user install lands in AppData."""
    home = Path(os.path.expanduser("~"))
    roots = []
    for pattern in ("AppData/Local/Programs/3DCoat*",
                    "AppData/Local/Programs/3D-Coat*",
                    "AppData/Local/3DCoat*"):
        roots += sorted(home.glob(pattern))
    return roots


def program_dir():
    """3D-Coat's program folder, for the button icons - best effort.

    Inside 3D-Coat the ``coat`` module is loaded from
    ``<install>/UserPrefs/PythonAPI``, which names the folder exactly; outside it
    the machine is asked: the uninstall entries first (they know about any install
    location), then the Program Files folders this system spells, then every
    drive, then per-user installs.  Icons are a nicety: a missing one costs a
    default icon on a tool button, never a broken button.
    """
    for name in ("coat", "CMD"):
        module = sys.modules.get(name)
        source = getattr(module, "__file__", None) if module else None
        if source:
            install = Path(source).resolve().parents[3]
            if (install / "data").is_dir():
                return install
    override = os.environ.get("COATLINK_COAT_DIR")
    if override:
        return Path(override)
    candidates = list(registry_program_dirs())
    candidates += environment_program_roots()
    candidates += drive_program_roots()
    candidates += user_program_roots()
    found = [candidate for candidate in candidates if (candidate / "data").is_dir()]
    if not found:
        return None
    # newest wins: a machine can hold 3DCoat-2025 and 3DCoat-2026 side by side, and
    # the icons belong beside the one being used (a plain first-match picks 2025)
    return sorted(found, key=lambda path: (path.name.lower(), str(path).lower()))[-1]


def read_payload():
    """The files to install, read from beside this module.

    The single-file build replaces this with an embedded copy of the same files.
    """
    scripts = {}
    for name in SCRIPT_FILES:
        scripts[name] = (HERE / name).read_bytes()
    icons = {}
    for name in ICON_FILES:
        icons[name] = (HERE / "icon" / name).read_bytes()
    template = (HERE / TOOLS_TEMPLATE).read_text(encoding="utf-8")
    return {"scripts": scripts, "icons": icons, "tools_xml": template}


class Report(object):
    def __init__(self):
        self.written = []
        self.removed = []
        self.skipped = []
        self.notes = []
        self.verified = True

    def line(self, text):
        self.notes.append(text)


def _write(path, data, report, verify=True):
    """Write bytes, then read them back: a silent half-copy is not an install.

    A folder that cannot be written (a read-only Scripts folder, a sync client
    holding the file) is reported as skipped with the reason, so the run ends with
    "Permission denied: <file>" instead of a traceback nobody can act on.
    """
    if isinstance(data, str):
        data = data.encode("utf-8")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    except OSError as exc:
        report.skipped.append((path.name, str(exc)))
        report.verified = False
        return False
    if verify and path.read_bytes() != data:
        report.verified = False
        report.line("MISMATCH after writing %s" % path)
    report.written.append(path)
    return True


def xml_escape(text):
    """Make a path safe to put inside an XML file.

    ``&`` is legal in a Windows user name and in a folder name, and a single
    unescaped ``&`` makes the whole menu file unreadable to 3D-Coat - which then
    shows no menu at all, with nothing written to the log to say why.
    """
    return (str(text).replace("&", "&amp;")
                     .replace("<", "&lt;")
                     .replace(">", "&gt;"))


def startup_path(scripts_dir):
    """The file 3D-Coat reads to know which extensions to load."""
    return Path(scripts_dir) / "cExtensions" / "startup.txt"


def extension_dir(scripts_dir):
    """Where a ``.3dcpack`` would have put these files."""
    return Path(scripts_dir) / "cExtensions" / APP_DIRNAME


def _register_startup(scripts_dir, report):
    """Add our name to ``startup.txt`` once, keeping a copy of the original."""
    path = startup_path(scripts_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
        if any(line.strip().lower() == APP_DIRNAME.lower() for line in lines):
            report.line("%s is already listed in %s" % (APP_DIRNAME, path.name))
            return
        backup = path.with_name(path.name + ".bak")
        if path.is_file() and not backup.exists():
            backup.write_bytes(path.read_bytes())
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("\n".join(lines + [APP_DIRNAME]) + "\n")
        report.line("listed %s in %s" % (APP_DIRNAME, path.name))
    except OSError as exc:
        report.skipped.append((str(path), str(exc)))


def install(scripts_dir, program=None, report=None):
    """Install the 3D-Coat half the way a ``.3dcpack`` does: as an extension.

    The files go into ``Scripts/cExtensions/CoatLink`` and the name goes into
    ``cExtensions/startup.txt``, which is what makes 3D-Coat load them.  The two
    ``ExtraMenuItems`` XML files are written by the extension itself the first time
    it starts - they hold absolute paths, so they cannot be shipped - and it moves an
    install of an older build out of the way at the same time.

    ``program`` is kept for the old command line and is not used any more: the tool
    buttons take 3D-Coat's default icon, so nothing is written outside 3D-Coat's user
    folder.
    """
    report = report or Report()
    target = extension_dir(scripts_dir)
    for name in SCRIPT_FILES:
        _write(target / name, (HERE / name).read_bytes(), report)
    report.line("installed as an extension: %s" % target)
    _register_startup(scripts_dir, report)
    return report

def _drop_startup(scripts_dir, report):
    """Take our line back out of ``startup.txt``; the file itself stays."""
    path = startup_path(scripts_dir)
    if not path.is_file():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        kept = [line for line in lines if line.strip().lower() != APP_DIRNAME.lower()]
        if kept == lines:
            return
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(("\n".join(kept) + "\n") if kept else "")
        report.removed.append(path)
    except OSError as exc:
        report.skipped.append((str(path), str(exc)))


def uninstall(scripts_dir, program=None, report=None):
    """Take the extension back out: its folder, its startup line, its menu files."""
    report = report or Report()
    scripts_dir = Path(scripts_dir)
    target = extension_dir(scripts_dir)
    for path in sorted(target.rglob("*"), reverse=True):
        try:
            if path.is_file():
                path.unlink()
            else:
                path.rmdir()
            report.removed.append(path)
        except OSError as exc:
            report.skipped.append((str(path), str(exc)))
    if target.is_dir():                      # rglob() never yields the folder itself
        try:
            target.rmdir()
            report.removed.append(target)
        except OSError as exc:
            report.skipped.append((str(target), str(exc)))
    _drop_startup(scripts_dir, report)

    menu_dir = scripts_dir / "ExtraMenuItems"
    stale = [menu_dir / (APP_DIRNAME + ".xml"), menu_dir / (APP_DIRNAME + "Tools.xml")]
    if menu_dir.is_dir():
        for path in sorted(menu_dir.iterdir()):
            if path.name.startswith(APP_DIRNAME + "_") or path.name.startswith("CoatBridge"):
                stale.append(path)
    for path in stale:
        if path.is_file():
            try:
                path.unlink()
                report.removed.append(path)
            except OSError as exc:
                report.skipped.append((str(path), str(exc)))
    return report

def launcher_state_path(scripts_dir):
    """Where 3D-Coat's copy of our registered menu/tool entries lives.

    ``…/Documents/3DCoat/CoatLink.json`` - next to ``UserPrefs``, holding both the
    user's panel settings and the list of launcher entries we added at run time.
    """
    return Path(scripts_dir).parent.parent / "CoatLink.json"


def forget_launchers(scripts_dir, report):
    """Drop the record of the launcher entries we registered.

    Those entries only live for one 3D-Coat session, but the file that says they were
    registered is kept: leaving it behind makes the next install believe the entries
    are already there and skip inserting them - so uninstalling and installing again
    would come back without the Windows-menu entry.  The user's own settings in the
    same file are kept, and a missing or unreadable file is not an error.
    """
    path = launcher_state_path(scripts_dir)
    if not path.is_file():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if not isinstance(data, dict) or not (data.get("menus") or data.get("tools")):
        return
    data["menus"] = []
    data["tools"] = []
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:
        report.skipped.append((path.name, str(exc)))
        return
    report.line("cleared the launcher record in %s (your settings are kept)" % path.name)


def describe(report):
    for path in report.removed:
        print("removed %s" % path)
    for path in report.written:
        print("wrote   %s" % path)
    for name, why in report.skipped:
        print("skipped %s (%s)" % (name, why))
    for note in report.notes:
        print("note    %s" % note)
    print("ok" if report.verified else "INCOMPLETE")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Install the 3D-Coat side of CoatLink.")
    parser.add_argument("--scripts", help="3D-Coat's Scripts folder (found automatically)")
    parser.add_argument("--coat", help="3D-Coat's program folder, for the button icons")
    parser.add_argument("--uninstall", action="store_true", help="take it all back out")
    parser.add_argument("--quiet", action="store_true", help="print nothing on success")
    args = parser.parse_args(argv)

    prefs = user_prefs()
    scripts = Path(args.scripts) if args.scripts else prefs / "Scripts"
    program = Path(args.coat) if args.coat else program_dir()

    if not scripts.is_dir():
        print("3D-Coat's script folder was not found: %s" % scripts, file=sys.stderr)
        print("Run 3D-Coat once, or pass --scripts <folder>.", file=sys.stderr)
        return 1

    print("scripts: %s" % scripts)
    print("program: %s" % (program or "(not found - icons skipped)"))
    if args.uninstall:
        report = uninstall(scripts, program)
        print("CoatLink removed from 3D-Coat.  Restart 3D-Coat.")
    else:
        report = install(scripts, program)
        print("CoatLink installed.  Restart 3D-Coat, then look for Scripts > CoatLink")
        print("and the three buttons at the end of the Sculpt and Paint tool lists.")
    if not args.quiet:
        describe(report)
    return 0 if report.verified else 1


if __name__ == "__main__":
    sys.exit(main())
