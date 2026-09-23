# SPDX-License-Identifier: GPL-3.0-or-later
"""The 3D-Coat extension entry point, under a fake 3D-Coat.

3D-Coat loads ``CoatLink.py`` as a *module* and keeps the ``cExtension`` instance
alive, so the test does the same: stub ``cPy.cCore``, load the copy from a
``Scripts/cExtensions/CoatLink`` tree, instantiate it and call ``onStartup``.  What
that has to achieve is checked here - the two XML files land in 3D-Coat's folder
with the extension's own paths in them, and the leftovers of an older install are
moved out of the way rather than deleted.

    python coat_side/tests/test_coatlink_extension.py
"""

import importlib.util
import os
import shutil
import sys
import tempfile
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fake_coat import build_environment  # noqa: E402  (shared fake 3D-Coat API)

HERE = os.path.dirname(os.path.abspath(__file__))
COAT_SIDE = os.path.join(HERE, "..")
HALF = ("CoatLink.py", "CoatLinkLib.py", "CoatLinkMenu.py", "CoatLink_Send.py",
        "CoatLink_Pull.py", "CoatLink_Setup.py", "CoatLinkReceipts.py",
        "CoatLinkScopedExport.py")

RESULTS = []


def check(name, condition, detail=""):
    RESULTS.append((name, bool(condition), detail))
    print("%-4s %s%s" % ("PASS" if condition else "FAIL", name,
                         "" if condition else "   <- %s" % (detail,)))


def _stub_cpy():
    """3D-Coat's own extension base class, which only 3D-Coat can provide."""
    cpy = types.ModuleType("cPy")
    ccore = types.ModuleType("cPy.cCore")

    class cExtension(object):
        def __init__(self):
            self.started = []

    ccore.cExtension = cExtension
    cpy.cCore = ccore
    sys.modules["cPy"] = cpy
    sys.modules["cPy.cCore"] = ccore


def load_half(where, *parts):
    """Copy the 3D-Coat half into ``where/parts`` and load CoatLink.py from it."""
    target = os.path.join(where, *parts)
    os.makedirs(target, exist_ok=True)
    for name in HALF:
        shutil.copy(os.path.join(COAT_SIDE, name), target)
    _stub_cpy()
    spec = importlib.util.spec_from_file_location("CoatLink", os.path.join(target, "CoatLink.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules["CoatLink"] = module
    spec.loader.exec_module(module)
    return module, target


def read(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def touch(path, text="x\n"):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def main():
    tmp = tempfile.mkdtemp(prefix="coatlink_ext_test.")
    build_environment(tmp)
    scripts = os.path.join(tmp, "Documents", "3DCoat", "UserPrefs", "Scripts")
    extra = os.path.join(scripts, "ExtraMenuItems")
    os.makedirs(extra)

    # An older install of the same tool sitting straight in Scripts, the pre-rename
    # leftovers, 3D-Coat's own file for an old run-time insertion, and a menu file
    # that belongs to somebody else - an upgrade has to sort out the first three and
    # leave the last one alone.
    classic = os.path.join(scripts, "CoatLink")
    os.makedirs(classic)
    touch(os.path.join(classic, "CoatLinkLib.py"), "old\n")
    prerename = os.path.join(scripts, "CoatBridge")
    os.makedirs(prerename)
    touch(os.path.join(extra, "CoatBridge.xml"))
    touch(os.path.join(extra, "CoatLink_Old.xml"))
    theirs = os.path.join(extra, "CoatMenu.xml")
    touch(theirs)

    module, target = load_half(tmp, "Documents", "3DCoat", "UserPrefs", "Scripts",
                               "cExtensions", "CoatLink")
    module.CoatLinkExtension().onStartup()

    menu = os.path.join(extra, "CoatLink.xml")
    check("the extension writes the menu file", os.path.isfile(menu))
    check("and the tool file", os.path.isfile(os.path.join(extra, "CoatLinkTools.xml")))
    text = read(menu)
    check("its command points at the extension's own copy",
          "script:%s/CoatLink_Setup.py" % target.replace("\\", "/") in text, text)
    check("the older hand install is moved aside, not deleted",
          not os.path.isdir(classic)
          and os.path.isfile(os.path.join(classic + ".removed", "CoatLinkLib.py")))
    check("the pre-rename scripts folder is moved aside",
          not os.path.isdir(prerename) and os.path.isdir(prerename + ".removed"))
    check("the pre-rename menu file is gone",
          not os.path.exists(os.path.join(extra, "CoatBridge.xml")))
    check("3D-Coat's own insertion file for our id is gone",
          not os.path.exists(os.path.join(extra, "CoatLink_Old.xml")))
    check("somebody else's menu file is left alone", os.path.exists(theirs))

    import CoatLinkMenu
    check("starting again writes nothing (the files are already current)",
          CoatLinkMenu.ensure()["written"] == [])

    # ---- a hand install must not move itself aside ----
    tmp2 = tempfile.mkdtemp(prefix="coatlink_ext_test2.")
    build_environment(tmp2)
    scripts2 = os.path.join(tmp2, "Documents", "3DCoat", "UserPrefs", "Scripts")
    os.makedirs(os.path.join(scripts2, "ExtraMenuItems"))
    for name in ("CoatLink", "CoatLinkLib", "CoatLinkMenu"):
        sys.modules.pop(name, None)          # load the second copy, not the first
    module2, target2 = load_half(tmp2, "Documents", "3DCoat", "UserPrefs", "Scripts", "CoatLink")
    module2.CoatLinkExtension().onStartup()
    check("the copy itself stays where it was put", os.path.isdir(target2))
    check("and it writes the menu file for its own folder",
          os.path.isfile(os.path.join(scripts2, "ExtraMenuItems", "CoatLink.xml")))

    failed = [name for name, ok, _detail in RESULTS if not ok]
    print("")
    print("RESULT: %d/%d checks passed" % (len(RESULTS) - len(failed), len(RESULTS)))
    if failed:
        print("FAILED: " + "; ".join(failed))
        return 1
    print("EXTENSION CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
