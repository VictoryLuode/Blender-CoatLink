# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the tool-panel buttons - the no-window path.

Each button is a script that acts directly and reports with 3D-Coat's own
floating message, so nothing has to be opened.  The XML that puts those buttons
into the room tool panels is validated too (entries, rooms, script paths, and
that every id has a label in CoatLinkLib.ACTION_LABELS).

    python coat_side/tests/test_coat_tools.py
"""

import os
import runpy
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
COAT_SIDE = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, COAT_SIDE)

import fake_coat  # noqa: E402

RESULTS = []


def check(name, condition, detail=""):
    RESULTS.append((name, bool(condition), detail))
    print("%-4s %s%s" % ("PASS" if condition else "FAIL", name, "" if condition else "   <- %s" % detail))


def main():
    tmp = tempfile.mkdtemp(prefix="coat_tools_test.")
    own_root, job_root = fake_coat.make_exchange_tree(tmp)
    coat, cmd = fake_coat.build_environment(tmp)
    import CoatLinkLib as lib

    # a model Blender queued, like the real workflow
    folder = lib.ensure_folder(job_root)
    queued = os.path.join(folder, "bridge.obj")
    with open(queued, "w", encoding="utf-8") as handle:
        handle.write("# queued model\n")
    with open(lib.import_txt(job_root), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(queued + "\n" + queued + "\n[ppp]\n")

    # ---- the buttons exist and are import-safe ----
    for tool_id in ("CoatLink_Send", "CoatLink_Pull", "CoatLink_Setup"):
        path = os.path.join(COAT_SIDE, "%s.py" % tool_id)
        check("%s.py exists" % tool_id, os.path.isfile(path))
    check("the ids have labels", set(lib.ACTION_LABELS) ==
          {"CoatLink_Send", "CoatLink_Pull", "CoatLink_Setup"}, list(lib.ACTION_LABELS))
    check("every label maps to a real action",
          all(hasattr(lib.CoatLinkPanel, method) for method, _label in lib.ACTION_LABELS.values()),
          lib.ACTION_LABELS)

    # ---- the setup button finds the exchange folder and reports ----
    messages_before = len(coat.messages)
    lib.run_action("CoatLink_Setup")
    check("setup reports through 3D-Coat's message system", len(coat.messages) > messages_before)
    check("setup writes a log line", os.path.isfile(lib.log_path()))

    # ---- the send button exports the selected tree node, opening nothing ----
    # (the whole-scene route has its own tests; the button sends the selection)
    coat.dialog_log.clear()
    status = lib.run_action("CoatLink_Send")
    check("send exports the selected node",
          os.path.isfile(lib.model_path(job_root, lib.EXPORT_FORMAT)),
          lib.model_path(job_root, lib.EXPORT_FORMAT))
    check("send writes the signal Blender watches", os.path.isfile(lib.signal_path(job_root)))
    check("send reports the result", "selected node" in status, status)
    check("send opens no dialog", coat.dialog_log == [], coat.dialog_log)

    # ---- the pull button imports the queue and consumes it ----
    status = lib.run_action("CoatLink_Pull")
    check("pull imports the queued model", coat.scene_imports == [queued], coat.scene_imports)
    check("pull consumes the queue", not os.path.isfile(lib.import_txt(job_root)))
    check("pull reports the result", "Pulled" in status, status)

    # ---- running the entry files the way 3D-Coat does ----
    coat.scene_imports.clear()
    with open(lib.import_txt(job_root), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(queued + "\n" + queued + "\n[ppp]\n")
    runpy.run_path(os.path.join(COAT_SIDE, "CoatLink_Pull.py"))
    check("the entry file pulls without any window",
          coat.scene_imports == [queued] and coat.dialog_log == [], (coat.scene_imports, coat.dialog_log))

    # ---- a second click must work: 3D-Coat imports scripts by module name ----
    import importlib.util

    def click_entry(module_name, filename):
        """What 3D-Coat's importer does: import the file as a named module."""
        path = os.path.join(COAT_SIDE, filename)
        spec = importlib.util.spec_from_file_location(module_name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

    # the pop is deferred to the next frame, so let the Qt event loop run
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])

    def click_with_queue():
        with open(lib.import_txt(job_root), "w", encoding="utf-8", newline="\n") as handle:
            handle.write(queued + "\n" + queued + "\n[ppp]\n")
        click_entry("CoatLinkPkg.CoatLink_Pull", "CoatLink_Pull.py")

    coat.scene_imports.clear()
    click_with_queue()
    check("the first click runs the action", coat.scene_imports == [queued], coat.scene_imports)
    app.processEvents()
    check("the entry leaves the module cache on the next frame",
          "CoatLinkPkg.CoatLink_Pull" not in sys.modules, list(sys.modules)[:3])
    click_with_queue()
    check("the second click runs the action again",
          coat.scene_imports == [queued, queued], coat.scene_imports)
    app.processEvents()
    check("the module cache stays clean", "CoatLinkPkg.CoatLink_Pull" not in sys.modules)

    # ---- the log black box records what happened ----
    log_text = open(lib.log_path(), encoding="utf-8").read()
    check("the log mentions the buttons", "tool CoatLink_Send" in log_text and "tool CoatLink_Pull" in log_text,
          log_text[-200:])
    check("the log records 3D-Coat's own scene scale",
          "coat settings: scale=1.0 units=m" in log_text, log_text[-200:])
    check("the scale note survives a missing API",
          isinstance(lib.scene_scale_note(), str) and lib.scene_scale_note() != "")

    # ---- the tool-panel XML, as the extension writes it on its first start ----
    import CoatLinkMenu

    write_into = os.path.join(lib.user_data_dir(), "UserPrefs", "Scripts", "ExtraMenuItems")
    os.makedirs(write_into, exist_ok=True)
    check("the tool file is written", CoatLinkMenu.write_tools_xml() == ["CoatLinkTools.xml"],
          CoatLinkMenu.extra_menu_dir())
    tree = ET.parse(os.path.join(write_into, "CoatLinkTools.xml"))
    entries = tree.findall("ExtraMenuItem")
    check("it declares every button in both rooms", len(entries) == 6, len(entries))
    ids = [entry.findtext("MenuItem") for entry in entries]
    rooms = sorted({entry.findtext("inRoom") for entry in entries})
    sections = {entry.findtext("inSection") for entry in entries}
    check("the ids match the labelled actions", sorted(set(ids)) == sorted(lib.ACTION_LABELS), sorted(set(ids)))
    check("the rooms are the ones we use", rooms == ["Paint", "Voxels"], rooms)
    check("the entries are tool-panel entries (no menu path)",
          all(not (entry.findtext("MenuPath") or "").strip() for entry in entries))
    check("they land outside the named sections", sections == {"*"}, sections)
    check("every entry points at an existing script",
          all(os.path.isfile(os.path.join(COAT_SIDE, os.path.basename(entry.findtext("Command"))))
              for entry in entries),
          [entry.findtext("Command") for entry in entries])

    # A user folder may legally contain "&" ("C:\Users\Tom & Jerry\..."), and one unescaped
    # ampersand makes the whole file unreadable to 3D-Coat - which then shows no menu and
    # logs nothing.  The path is escaped on the way in, so the file always parses.
    plain = "C:/Users/Tom & Jerry/3DCoat"
    where = lib.xml_escape(CoatLinkMenu.windows_path(plain))
    text = (CoatLinkMenu.MENU_HEAD
            + CoatLinkMenu.MENU_BLOCK % {"path": "Scripts", "id": lib.MENU_ID, "here": where}
            + CoatLinkMenu.MENU_TAIL)
    check("a folder with an & in its name still writes a menu file 3D-Coat can parse",
          "&amp;" in where
          and ET.fromstring(text).findtext("ExtraMenuItem/Command")
          == "script:%s/CoatLink_Setup.py" % plain,
          (where, ET.fromstring(text).findtext("ExtraMenuItem/Command")))

    failed = [item for item in RESULTS if not item[1]]
    print("\nRESULT: %d/%d checks passed" % (len(RESULTS) - len(failed), len(RESULTS)))
    for name, _ok, detail in failed:
        print("FAILED: %s -- %s" % (name, detail))
    shutil.rmtree(tmp, ignore_errors=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
