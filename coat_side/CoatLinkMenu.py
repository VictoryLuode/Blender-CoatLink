# SPDX-License-Identifier: GPL-3.0-or-later
#
# CoatLink - the 3D-Coat side's own install: the menu entry, the tool buttons, and
# the cleanup of what older builds left behind.
#
# A .3dcpack has no installer to run, so everything the installer used to write is
# written here instead, from the extension's onStartup - and again whenever the
# panel opens, which is what repairs a machine where the files went missing.
#
# Two rules decide the shape of this module:
#
#   * The Scripts entry is *inserted* at run time (``coat.ui.insertInMenu``), not declared
#     in ``Scripts/ExtraMenuItems/*.xml``.  The XML route was tried and does not show the
#     entry on the machine this is developed against, while an insertion does - and an id
#     that is in both places is listed twice, so the declaration is retired here.
#   * The XML carries absolute paths, so it cannot be shipped inside the package -
#     it is generated here, per machine, and only rewritten when it changed.

import os

import CoatLinkLib as lib
from CoatLinkLib import MENU_ID, MENU_PATHS, TOOL_ACTIONS, TOOL_ROOMS, log


def windows_path(path):
    """3D-Coat's XML wants forward slashes, whatever the shell gave us."""
    return str(path).replace("\\", "/")


#: 3D-Coat reads these as XML.  Declaring the encoding costs a line and removes the guess
#: a non-ASCII user folder would otherwise depend on; escaping the path is what keeps a
#: folder called "Docs & Stuff" from making the whole file unreadable (see lib.xml_escape).
MENU_HEAD = '<?xml version="1.0" encoding="UTF-8"?>\n<ClassArray.ExtraMenuItem>\n'
MENU_TAIL = "</ClassArray.ExtraMenuItem>\n"

MENU_BLOCK = (
    "\t<ExtraMenuItem>\n"
    "\t\t<MenuPath>%(path)s</MenuPath>\n"
    "\t\t<MenuItem>%(id)s</MenuItem>\n"
    "\t\t<inRoom></inRoom>\n"
    "\t\t<inSection></inSection>\n"
    "\t\t<Command>script:%(here)s/CoatLink_Setup.py</Command>\n"
    "\t</ExtraMenuItem>\n"
)

TOOL_BLOCK = (
    "\t<ExtraMenuItem>\n"
    "\t\t<MenuPath></MenuPath>\n"
    "\t\t<MenuItem>%(id)s</MenuItem>\n"
    "\t\t<inRoom>%(room)s</inRoom>\n"
    "\t\t<inSection>*</inSection>\n"
    "\t\t<Command>script:%(here)s/%(id)s.py</Command>\n"
    "\t</ExtraMenuItem>\n"
)

MENU_FILE = "CoatLink.xml"
TOOLS_FILE = "CoatLinkTools.xml"


def script_dir():
    """The ``…/UserPrefs/Scripts`` folder these files live in.

    Walked to from ``__file__`` rather than assumed: a .3dcpack installs this into
    ``Scripts/cExtensions/CoatLink``, a hand install lands in ``Scripts/CoatLink``,
    and the 4.x layout is ``<data>/Scripts``.  Returns "" when nothing matches.
    """
    folder = os.path.dirname(os.path.abspath(__file__))
    for _ in range(6):
        if os.path.basename(folder).lower() == "scripts":
            return folder
        parent = os.path.dirname(folder)
        if parent == folder:
            break
        folder = parent
    # Nothing named Scripts above us: this copy was started from somewhere else, or
    # it is a test tree.  3D-Coat's own folder is where the files have to end up
    # anyway, and it is known rather than guessed (``COATLINK_DOCS`` override first).
    try:
        data = lib.user_data_dir()
    except Exception:
        return ""
    for candidate in (os.path.join(data, "UserPrefs", "Scripts"),
                      os.path.join(data, "Scripts")):
        if os.path.isdir(candidate):
            return candidate
    return ""


def here():
    """The folder these scripts actually live in.

    That is what goes into the XML: a .3dcpack copy sits in
    ``Scripts/cExtensions/CoatLink``, a hand install in ``Scripts/CoatLink``, and the
    command has to name the copy that is running.
    """
    return os.path.dirname(os.path.abspath(__file__))


def is_extension_copy():
    """True when this copy runs from ``Scripts/cExtensions/CoatLink``."""
    parent = os.path.dirname(here())
    return os.path.basename(parent).lower() == "cextensions"


def extra_menu_dir():
    scripts = script_dir()
    return os.path.join(scripts, "ExtraMenuItems") if scripts else ""


def _write_if_changed(path, text):
    """Write a file only when its content differs; returns the path or ""."""
    try:
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                if handle.read() == text:
                    return ""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    except OSError as exc:
        log("%s could not be written: %s" % (os.path.basename(path), exc))
        return ""
    return path


def _write_extra(name, text):
    folder = extra_menu_dir()
    if not folder:
        log("no ExtraMenuItems folder found next to %s" % os.path.abspath(__file__))
        return []
    return [name] if _write_if_changed(os.path.join(folder, name), text) else []


def retire_menu_xml():
    """Delete the Scripts XML: that entry is inserted at run time now.

    A function rather than a deleted file, because a machine upgrading from an older
    build still has it - and an id that is declared there *and* inserted at run time is
    listed twice.
    """
    folder = extra_menu_dir()
    if not folder:
        return []
    path = os.path.join(folder, MENU_FILE)
    try:
        if os.path.isfile(path):
            os.remove(path)
            return [MENU_FILE]
    except OSError as exc:
        log("%s could not be removed: %s" % (MENU_FILE, exc))
    return []


def write_tools_xml():
    """The tool buttons: one entry per button per room, in TOOL_ROOMS order."""
    where = lib.xml_escape(windows_path(here()))
    blocks = "".join(TOOL_BLOCK % {"room": room, "id": action, "here": where}
                     for room in TOOL_ROOMS for action in TOOL_ACTIONS)
    return _write_extra(TOOLS_FILE, MENU_HEAD + blocks + MENU_TAIL)


#: files older builds wrote that point at scripts which are gone
LEGACY_FILES = ("CoatBridge.xml", "CoatBridgeTools.xml")
#: a hand install puts the scripts straight in here; a .3dcpack uses cExtensions
CLASSIC_FOLDER = "CoatLink"
PRERENAME_FOLDER = "CoatBridge"


def _menu_files_name(folder):
    """True when a menu file on disk still points into ``folder``.

    3D-Coat builds its menus from these files at *startup* and does not read them
    again in that session.  So a folder that a menu file still names must not be
    moved aside yet: the entry the user is looking at would point at nothing until
    the next start.  Rewriting the file first and moving on the *following* start
    keeps every session's entry working.
    """
    where = extra_menu_dir()
    if not where or not folder:
        return False
    wanted = windows_path(folder).lower() + "/"
    try:
        names = os.listdir(where)
    except OSError:
        return False
    for name in names:
        if not name.lower().endswith(".xml"):
            continue
        try:
            with open(os.path.join(where, name), "r", encoding="utf-8",
                      errors="replace") as handle:
                text = handle.read().lower()
        except OSError:
            continue
        if wanted in text:
            return True
    return False


def _remove(path, report):
    try:
        os.remove(path)
        report.append("removed " + os.path.basename(path))
    except OSError:
        pass


def clean_old_installs(defer_classic=False):
    """Take the leftovers of older builds out of 3D-Coat's way.

    Only 3D-Coat's own user folder is touched, and only things this project wrote:
    a file that would now point at nothing is deleted, and a whole scripts folder is
    *moved aside*, never deleted - a hand install may still have notes in it.

    ``defer_classic`` leaves the hand-install folder alone for this start: a menu
    file still names it, so the entry built from that file still works, and the move
    happens on the next start once that file points at us instead.
    """
    report = []
    scripts = script_dir()
    folder = extra_menu_dir()
    if not scripts or not folder:
        return report
    # 3D-Coat writes a file of its own for every run-time insertion; an id that is
    # also in our XML gets listed twice, and that file is what does it.
    try:
        names = os.listdir(folder)
    except OSError:
        names = []
    for name in names:
        if name.startswith(MENU_ID + "_") and name.endswith(".xml"):
            _remove(os.path.join(folder, name), report)
    for name in LEGACY_FILES:
        path = os.path.join(folder, name)
        if os.path.isfile(path):
            _remove(path, report)
    for name in (PRERENAME_FOLDER, CLASSIC_FOLDER):
        if name == CLASSIC_FOLDER:
            if not is_extension_copy():
                continue      # a hand install is allowed to live there
            if defer_classic:
                report.append("left %s in place for now: a menu file still names it"
                              % name)
                continue
        path = os.path.join(scripts, name)
        if not os.path.isdir(path):
            continue
        aside = path + ".removed"
        index = 1
        while os.path.exists(aside):
            aside = "%s.removed-%d" % (path, index)
            index += 1
        try:
            os.rename(path, aside)
            report.append("moved %s aside -> %s" % (name, os.path.basename(aside)))
        except OSError as exc:
            report.append("could not move %s aside: %s" % (name, exc))
    return report


def ensure():
    """What the extension does at startup: clean up, then write what is ours.

    Called from ``onStartup`` and again whenever the panel opens, so a machine where
    the XML files went missing repairs itself without anything being reinstalled.
    Never raises.
    """
    report = []
    written = []
    try:
        lib.add_translations()
    except Exception:
        pass
    try:
        # Asked *before* the XML is rewritten: what matters is whether the file
        # 3D-Coat has just read for its menu still names the hand-install folder.
        classic = os.path.join(script_dir(), CLASSIC_FOLDER)
        report = clean_old_installs(defer_classic=_menu_files_name(classic))
        written = retire_menu_xml() + write_tools_xml()
    except Exception as exc:
        log("registering the launcher failed: %s" % exc)
        return {"cleaned": report, "written": written}
    for line in report:
        log(line)
    if written:
        log("wrote %s" % ", ".join(written))
    return {"cleaned": report, "written": written}
