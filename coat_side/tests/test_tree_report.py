# SPDX-License-Identifier: GPL-3.0-or-later
"""The tree report must stay read-only, and must not be able to break a scene.

It is meant to be dropped into a live 3D-Coat session, so the check is deliberately
strict: no call that writes to the host, no call that touches the bridge's signals.
"""
import ast
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
SCRIPT = HERE.parent / "diagnostics" / "tree_report.py"

checks = []


def check(name, ok, detail=None):
    checks.append((name, bool(ok), detail))
    if not ok:
        print("FAIL  %s  <- %s" % (name, detail))


source = SCRIPT.read_text(encoding="utf-8")
check("the report script is there", SCRIPT.is_file(), str(SCRIPT))

try:
    tree = ast.parse(source)
    check("it parses", True)
except SyntaxError as error:
    tree = None
    check("it parses", False, error)

# 1. anything that would change the host, the scene or the bridge
FORBIDDEN = (
    "importMesh", "fromVolume", "fromReducedVolume", "Write(", "Export",
    "moveTo", "remove", "setVisible", "toSurface", "toVoxels", "select",
    "transform_single", "setTransform", "reduction", "SetSlider", "cmd(",
    "dialog", "write_import", "export_txt", "run.txt", "import.txt",
)
called = set()
for node in ast.walk(tree or ast.Module(body=[], type_ignores=[])):
    if isinstance(node, ast.Call):
        target = node.func
        name = getattr(target, "attr", None) or getattr(target, "id", None)
        if name:
            called.add(name)
bad = sorted(name for name in called if name in FORBIDDEN)
check("it calls nothing that writes", not bad, bad)

# 2. what it does reach for: only the read side of the API
for needed in ("sculptRoot", "currentRoom", "childCount", "Volume", "getPolycount"):
    check("it uses %s" % needed, needed in source, needed)

# 3. the report path is 3D-Coat's own folder, and nothing machine specific is baked in
check("the report is named", 'REPORT_NAME = "CoatLink-TreeReport.txt"' in source)
check("no absolute path is baked into the script",
      "C:/" not in source and "C:\\" not in source and "/Users/" not in source)
check("it says it is read-only", "Read-only" in source)

failed = [name for name, ok, _ in checks if not ok]
print("RESULT: %d/%d checks passed" % (len(checks) - len(failed), len(checks)))
if failed:
    print("FAILED: %s" % ", ".join(failed))
    sys.exit(1)
print("TREE REPORT CHECKS PASSED")
