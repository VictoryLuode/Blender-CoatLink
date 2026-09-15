# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the in-process Qt panel (CoatBridgeQt.py).

Runs on 3D-Coat's own bundled Python + PySide6 with the offscreen platform, so
the window can really be built and its buttons really be clicked - with `coat`
replaced by the shared fake.  This is the closest thing to running the panel
inside 3D-Coat without 3D-Coat.

    QT_QPA_PLATFORM=offscreen python coat_side/tests/test_coat_qt.py
"""

import os
import sys
import tempfile
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
QT_ENTRY = os.path.join(HERE, "..", "CoatBridgeQt.py")
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

import fake_coat  # noqa: E402

RESULTS = []


def check(name, condition, detail=""):
    RESULTS.append((name, bool(condition), detail))
    print("%-4s %s%s" % ("PASS" if condition else "FAIL", name, "" if condition else "   <- %s" % detail))


def main():
    tmp = tempfile.mkdtemp(prefix="coat_qt_test.")
    own_root, job_root = fake_coat.make_exchange_tree(tmp)
    coat, cmd = fake_coat.build_environment(tmp)
    app = QApplication.instance() or QApplication([])

    # ---- the logic module is import-safe, the entry runs when 3D-Coat runs it ----
    import CoatBridgeLib
    CoatBridge = CoatBridgeLib  # the name the checks below use

    import runpy

    namespace = runpy.run_path(QT_ENTRY)
    check("the Qt entry reports no Qt problem", namespace["QT_ERROR"] == "", namespace["QT_ERROR"])
    check("running the entry opens a window", namespace["_window"][0] is not None)

    # ---- a model Blender queued, like the real workflow ----
    folder = CoatBridge.ensure_folder(job_root)
    queued = os.path.join(folder, "bridge.obj")
    with open(queued, "w", encoding="utf-8") as handle:
        handle.write("# queued model\n")
    with open(CoatBridge.import_txt(job_root), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(queued + "\n" + queued + "\n[ppp]\n")

    # ---- the panel ----
    window = namespace["_window"][0]
    check("the window is titled Coat Bridge", window.windowTitle() == "Coat Bridge", window.windowTitle())
    check("opening twice raises the same window", namespace["main"]() is window)
    check("panel shows the stored format", window.format_box.currentText() == CoatBridge.load_state().get("format", "FBX"),
          window.format_box.currentText())
    check("panel has both transfer buttons",
          window.send_button.text() == "Send to Blender" and window.pull_button.text() == "Pull from Blender")
    check("panel has the utility buttons",
          {window.detect_button.text(), window.folder_button.text(),
           window.blender_button.text(), window.remove_button.text()} ==
          {"Detect", "Folder", "Start Blender", "Remove launcher"})
    check("panel shows the status line", bool(window.status_label.text()), window.status_label.text())

    # ---- Send to Blender (direct export route) ----
    coat.applink_present = False

    def direct_export(path):
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("# exported by the fake 3D-Coat\n")

    coat.direct_export = direct_export
    window.send_button.click()
    app.processEvents()
    check("Send to Blender exports a model", any(path.endswith("bridge.fbx") for path in cmd.calls), cmd.calls)
    check("Send writes the signal Blender watches", os.path.isfile(CoatBridge.signal_path(own_root)))
    check("Send reports in the status line", "Sent to Blender" in window.status_label.text(),
          window.status_label.text())

    # ---- Send to Blender through 3D-Coat's own AppLink target ----
    def applink_export(root):
        with open(CoatBridge.model_path(root, "fbx"), "w", encoding="utf-8") as handle:
            handle.write("# exported by 3D-Coat\n")
        with open(CoatBridge.signal_path(root), "w", encoding="utf-8", newline="\n") as handle:
            handle.write(CoatBridge.model_path(root, "fbx") + "\n")

    coat.applink_present = True
    coat.applink_export = applink_export
    coat.ui.cmd.return_value = lambda *a, **k: applink_export(own_root) or True
    window.send_button.click()
    app.processEvents()
    check("Send prefers 3D-Coat's AppLink target when it exists",
          "AppLink" in window.status_label.text(), window.status_label.text())
    check("Send tells 3D-Coat which file to use",
          any(args and "bridge.fbx" in str(args[0]) for args in coat.ui.setFileForFileDialog.calls))
    coat.applink_present = False

    # ---- Pull from Blender ----
    window.pull_button.click()
    app.processEvents()
    check("Pull imports the queued model", coat.scene_imports == [queued], coat.scene_imports)
    check("Pull consumes the queue", not os.path.isfile(CoatBridge.import_txt(job_root)))
    check("Pull reports in the status line", "Pulled" in window.status_label.text(), window.status_label.text())

    # ---- the utility buttons ----
    window.detect_button.click()
    app.processEvents()
    check("Detect reports the target", "Target ready" in window.status_label.text(), window.status_label.text())

    window.folder_button.click()
    app.processEvents()
    check("Folder reports what it opened", "Opened" in window.status_label.text()
          or "Could not open" in window.status_label.text(), window.status_label.text())

    window.blender_button.click()
    app.processEvents()
    check("Start Blender says so when none is found", "not found" in window.status_label.text(),
          window.status_label.text())

    window.remove_button.click()
    app.processEvents()
    check("Remove launcher calls the API", coat.ui.removeCommandFromMenu.calls == [("CoatBridge",)],
          coat.ui.removeCommandFromMenu.calls)
    check("Remove launcher reports back", "removed" in window.status_label.text().lower(),
          window.status_label.text())

    # ---- format switch ----
    window.format_box.setCurrentText("OBJ")
    app.processEvents()
    check("format switch is stored", CoatBridge.load_state().get("format") == "OBJ", CoatBridge.load_state())
    check("format switch is shown", window.format_box.currentText() == "OBJ")

    # ---- geometry memory ----
    window.move(123, 77)
    window.close()
    app.processEvents()
    check("closing clears the singleton", namespace["_window"][0] is None)
    again = namespace["main"]()
    check("reopening restores the position", (again.x(), again.y()) == (123, 77), (again.x(), again.y()))
    again.close()

    # ---- without Qt the entry falls back to the native dialog ----
    # (runpy returns a copy of the globals, so the fallback is tested on the real
    # module object where QT_ERROR can actually be flipped)
    import CoatBridgeQt as qt_entry

    qt_entry._window[0].close()
    original_error = qt_entry.QT_ERROR
    qt_entry.QT_ERROR = "no Qt in this build"
    coat.dialog_log.clear()
    qt_entry.main()
    check("without Qt it falls back to the native dialog",
          any(name == "show" for name, _args in coat.dialog_log), coat.dialog_log)
    qt_entry.QT_ERROR = original_error

    failed = [item for item in RESULTS if not item[1]]
    print("\nRESULT: %d/%d checks passed" % (len(RESULTS) - len(failed), len(RESULTS)))
    for name, _ok, detail in failed:
        print("FAILED: %s -- %s" % (name, detail))
    shutil.rmtree(tmp, ignore_errors=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
