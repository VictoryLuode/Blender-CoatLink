# SPDX-License-Identifier: GPL-3.0-or-later
"""A/B one question against a running 3D-Coat: does the job file's mode line land?

Two imports of the same tiny cube, differing only in the extra lines we add:

  official : <model> / <return> / [vox]                      (what 3D-Coat's own
                                                              Blender AppLink writes)
  ours     : the same, plus [SkipImport] [SkipExport] [pythonfile ...]

After each one, the Sculpt Tree is read back with a read-only probe (the tree report),
so the answer is "V" or "S" per node rather than a guess.  The test cube is deleted
again at the end, by exact name.

    python coat_side/diagnostics/mode_ab.py [--keep]

Nothing here is part of the add-on; it drives the exchange folder from outside.
"""
import argparse
import os
import shutil
import subprocess
import sys
import time

DOCUMENTS = os.path.join(os.path.expanduser("~"), "Documents")
ROOT = os.path.join(DOCUMENTS, "AppLinks", "3D-Coat", "Exchange")
REPORT = os.path.join(DOCUMENTS, "3DCoat", "CoatLink-TreeReport.txt")
LOG = os.path.join(DOCUMENTS, "3DCoat", "Log.txt")
HERE = os.path.dirname(os.path.abspath(__file__))
PROBE = os.path.join(HERE, "tree_report.py")

MODEL = "CoatLinkModeTest"
CUBE = """# CoatLink mode test cube
o {name}
v -1 -1 -1
v 1 -1 -1
v 1 1 -1
v -1 1 -1
v -1 -1 1
v 1 -1 1
v 1 1 1
v -1 1 1
f 1 4 3 2
f 5 6 7 8
f 1 2 6 5
f 4 8 7 3
f 1 5 8 4
f 2 3 7 6
""".format(name=MODEL)


def log_size():
    try:
        return os.path.getsize(LOG)
    except OSError:
        return 0


def log_since(mark):
    with open(LOG, "r", encoding="utf-8", errors="replace") as handle:
        handle.seek(mark)
        return handle.read()


def wait_for_import(mark, timeout=25):
    """Wait until 3D-Coat has read a fresh import.txt, and hand back its log."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        text = log_since(mark)
        if "import.txt" in text and "Contence" in text:
            time.sleep(3)                 # let the merge settle before probing
            return text + log_since(mark)
        time.sleep(0.5)
    return log_since(mark)


def probe(timeout=30):
    """Run the read-only tree report inside 3D-Coat.  Returns its text."""
    if os.path.exists(REPORT):
        os.remove(REPORT)
    shutil.copyfile(PROBE, os.path.join(ROOT, "import.py"))
    with open(os.path.join(ROOT, "import.txt"), "w"):
        pass
    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.path.exists(REPORT):
            time.sleep(0.5)
            with open(REPORT, "r", encoding="utf-8", errors="replace") as handle:
                return handle.read()
        time.sleep(0.5)
    return ""


def write_job(variant):
    model = os.path.join(ROOT, MODEL + ".obj")
    back = os.path.join(ROOT, MODEL + "_back.obj")
    with open(model, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(CUBE)
    lines = [model.replace("\\", "/"), back.replace("\\", "/"), "[vox]"]
    if variant == "ours":
        lines.append("[SkipImport]")
        lines.append("[SkipExport]")
        helper = os.path.join(ROOT, "CoatLink_AfterImport.py")
        if os.path.isfile(helper):
            lines.append("[pythonfile %s]" % helper.replace("\\", "/"))
    job = os.path.join(ROOT, "import.txt")
    tmp = job + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")
    os.replace(tmp, job)                  # the write is the signal
    return lines


def tree_after(report):
    """The lines of the tree report that matter: our cube, and any wrapper around it."""
    out = []
    for line in report.splitlines():
        if MODEL.lower() in line.lower() or "mode_test" in line.lower():
            out.append(line.rstrip())
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep", action="store_true", help="do not delete the test cube")
    args = parser.parse_args()

    if not os.path.isdir(ROOT):
        print("exchange folder not found: %s" % ROOT)
        return 1
    print("probe first (is the mechanism alive at all):")
    first = probe()
    print("\n".join(first.splitlines()[-7:]) or "(no report - probe not running)")

    for variant in ("official", "ours"):
        mark = log_size()
        print("\n" + "=" * 60)
        print("variant: %s" % variant)
        lines = write_job(variant)
        print("job file:\n  " + "\n  ".join(lines))
        text = wait_for_import(mark)
        interesting = [line.rstrip() for line in text.splitlines()
                       if any(word in line for word in
                              ("Contence", "[vox]", "[SkipImport]", "[SkipExport]",
                               "pythonfile", "SCULP", "Merge", "Caught Python",
                               "LoadMesh", "Model info"))]
        print("3D-Coat log:\n  " + "\n  ".join(interesting[:14]))
        report = probe()
        found = tree_after(report)
        print("tree says:\n  " + ("\n  ".join(found) if found else "(cube not found)"))
        if not args.keep:
            os.remove(os.path.join(ROOT, MODEL + ".obj"))
            for name in (MODEL + ".obj", MODEL + "_back.obj"):
                path = os.path.join(ROOT, name)
                if os.path.isfile(path):
                    os.remove(path)
    print("\ndone.  test cube left in the scene: %s (delete it by hand, or press "
          "To voxels / remove the node named %s)" % (args.keep, MODEL))
    return 0


if __name__ == "__main__":
    sys.exit(main())
