# SPDX-License-Identifier: GPL-3.0-or-later
#
# CoatLink - a small, predictable Blender <-> 3D-Coat model bridge.

"""Install (or remove) the 3D-Coat half of CoatLink.

Three ways in, one implementation:

* from an unzipped release or a checkout, by double-clicking ``install.cmd``
  (Windows) or running ``./install.sh`` / ``./install.ps1``
* straight from this file on 3D-Coat's own Python
* from inside 3D-Coat, if you prefer its console::

      exec(open(r"...\\CoatLinkInstall.py", encoding="utf-8").read())

The single file in ``dist/`` is built from this module with the files embedded,
so everything below is the same code either way.

What it does, and nothing else:

    <scripts>/CoatBridge/*.py                     the bridge itself
    <scripts>/ExtraMenuItems/CoatBridge.xml       Scripts > CoatLink entry
    <scripts>/ExtraMenuItems/CoatBridgeTools.xml  the three tool buttons
    <program>/data/Textures/icons64/*.png         button icons, when that
                                                  folder is writable

Both folders are worked out on the spot - no path is baked into anything, which
is exactly why the menu XML is generated here: 3D-Coat needs absolute script
paths, and the only place that knows the right one is the machine installing it.
"""

import argparse
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

#: the folder our scripts live in, under 3D-Coat's Scripts folder
APP_DIRNAME = "CoatBridge"

#: what we install; the scoped-export module is deliberately absent (nothing
#: calls it, and shipping dead code in a released install is just confusing)
SCRIPT_FILES = (
    "CoatBridgeLib.py",
    "CoatBridgeReceipts.py",
    "CoatBridgeScopedExport.py",
    "CoatBridge_Send.py",
    "CoatBridge_Pull.py",
    "CoatBridge_Setup.py",
)

ICON_FILES = (
    "CoatBridge.png",
    "CoatBridge_Send.png",
    "CoatBridge_Pull.png",
    "CoatBridge_Setup.png",
)

MENU_FILES = ("CoatBridge.xml", "CoatBridgeTools.xml")

#: layouts this project used before; removed on sight so an upgrade cannot leave
#: a second copy of the bridge behind
STALE_FILES = (
    "CoatBridge.py",
    "CoatBridgeQt.py",
    "CoatBridgeDialog.py",
)

TOOLS_TEMPLATE = "tools/CoatBridgeTools.xml.in"
PLACEHOLDER = "__SCRIPT_DIR__"

MENU_XML = """<ClassArray.ExtraMenuItem>
\t<ExtraMenuItem>
\t\t<MenuPath>Scripts</MenuPath>
\t\t<MenuItem>CoatBridge</MenuItem>
\t\t<inRoom></inRoom>
\t\t<inSection></inSection>
\t\t<Command>script:{script_dir}/CoatBridge_Setup.py</Command>
\t</ExtraMenuItem>
</ClassArray.ExtraMenuItem>
"""


def windows_path(path):
    """3D-Coat's XML wants forward slashes, whatever the shell gave us."""
    return str(path).replace("\\", "/")


def user_prefs():
    """3D-Coat's user folder (``Documents/3DCoat/UserPrefs``).

    ``COATLINK_PREFS`` overrides it, which is how the tests point somewhere safe.
    """
    override = os.environ.get("COATLINK_PREFS")
    if override:
        return Path(override)
    return Path(os.path.expanduser("~")) / "Documents" / "3DCoat" / "UserPrefs"


def program_dir():
    """3D-Coat's program folder, for the button icons - best effort.

    Inside 3D-Coat the ``coat`` module is loaded from
    ``<install>/UserPrefs/PythonAPI``, which names the folder exactly; outside it
    the usual install locations are searched.  Icons are a nicety: a missing one
    costs a default icon on a tool button, never a broken button.
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
    home = Path(os.path.expanduser("~"))
    candidates = []
    # Both spellings on purpose: this installer normally runs on 3D-Coat's own
    # Python (a Windows program, where "/d/..." is not a path) but an MSYS Python
    # sees only the POSIX form.
    for prefix in ("%s:/", "/%s/"):
        for letter in ("c", "d", "e", "f", "g", "h"):
            root = Path(prefix % letter)
            if not root.is_dir():
                continue
            for folder in ("Program Files", "Program Files (x86)"):
                candidates += sorted(root.glob("%s/3DCoat*" % folder))
    candidates += sorted(home.glob("AppData/Local/Programs/3DCoat*"))
    candidates += sorted(home.glob("AppData/Local/3DCoat*"))
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
    """Write bytes, then read them back: a silent half-copy is not an install."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    if verify and path.read_bytes() != data:
        report.verified = False
        report.line("MISMATCH after writing %s" % path)
    report.written.append(path)


def install(scripts_dir, program=None, payload=None, report=None):
    """Copy the bridge into 3D-Coat's folders; safe to run repeatedly."""
    report = report or Report()
    payload = payload or read_payload()
    scripts_dir = Path(scripts_dir)
    if not scripts_dir.is_dir():
        raise SystemExit("no such scripts folder: %s" % scripts_dir)

    app_dir = scripts_dir / APP_DIRNAME
    app_dir.mkdir(parents=True, exist_ok=True)
    for name, data in sorted(payload["scripts"].items()):
        _write(app_dir / name, data, report)
    for name in STALE_FILES:
        stale = app_dir / name
        if stale.exists():
            stale.unlink()
            report.removed.append(stale)
    cache = app_dir / "__pycache__"
    if cache.is_dir():
        for byte_code in cache.iterdir():
            byte_code.unlink()
        cache.rmdir()

    script_dir = windows_path(app_dir)
    menu_dir = scripts_dir / "ExtraMenuItems"
    menu_dir.mkdir(parents=True, exist_ok=True)
    _write(menu_dir / "CoatBridge.xml", MENU_XML.format(script_dir=script_dir), report)
    tools = payload["tools_xml"].replace(PLACEHOLDER, script_dir)
    if PLACEHOLDER in tools:
        report.line("the tools template still holds %s" % PLACEHOLDER)
        report.verified = False
    _write(menu_dir / "CoatBridgeTools.xml", tools, report)

    icon_dir = Path(program) / "data" / "Textures" / "icons64" if program else None
    if icon_dir and icon_dir.is_dir():
        for name, data in sorted(payload["icons"].items()):
            try:
                _write(icon_dir / name, data, report)
            except OSError as exc:
                report.skipped.append((name, str(exc)))
    else:
        report.line("button icons skipped (%s)" % (icon_dir or "3D-Coat folder not found"))
    return report


def uninstall(scripts_dir, program=None, report=None):
    """Remove exactly what install() puts there, and nothing else."""
    report = report or Report()
    scripts_dir = Path(scripts_dir)
    app_dir = scripts_dir / APP_DIRNAME
    for name in SCRIPT_FILES + STALE_FILES:
        path = app_dir / name
        if path.exists():
            path.unlink()
            report.removed.append(path)
    cache = app_dir / "__pycache__"
    if cache.is_dir():
        for byte_code in cache.iterdir():
            byte_code.unlink()
        cache.rmdir()
    if app_dir.is_dir() and not any(app_dir.iterdir()):
        app_dir.rmdir()
    for name in MENU_FILES:
        path = scripts_dir / "ExtraMenuItems" / name
        if path.exists():
            path.unlink()
            report.removed.append(path)
    if program:
        for name in ICON_FILES:
            path = Path(program) / "data" / "Textures" / "icons64" / name
            if path.exists():
                try:
                    path.unlink()
                except OSError as exc:
                    report.skipped.append((name, str(exc)))
                else:
                    report.removed.append(path)
    return report


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
