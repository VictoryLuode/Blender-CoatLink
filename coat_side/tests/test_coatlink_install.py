# SPDX-License-Identifier: GPL-3.0-or-later
"""The 3D-Coat installer, now that it installs the half as an extension.

What it has to get right: the files land in ``Scripts/cExtensions/CoatLink``, the
name goes into ``cExtensions/startup.txt`` (once, with a backup of the original),
nothing is written outside 3D-Coat's user folder any more, and taking it back out
leaves other extensions and other people's menu files alone.

    python coat_side/tests/test_coatlink_install.py
"""

import importlib.util
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
INSTALLER = os.path.join(HERE, "..", "CoatLinkInstall.py")
RESULTS = []


def check(name, condition, detail=""):
    RESULTS.append((name, bool(condition), detail))
    print("%-4s %s%s" % ("PASS" if condition else "FAIL", name,
                         "" if condition else "   <- %s" % (detail,)))


def load_installer():
    spec = importlib.util.spec_from_file_location("coatlink_install", INSTALLER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fresh(tmp, name):
    """A 3D-Coat user folder with the folders it always has, plus an extension."""
    root = os.path.join(tmp, name)
    scripts = os.path.join(root, "UserPrefs", "Scripts")
    os.makedirs(os.path.join(scripts, "ExtraMenuItems"))
    os.makedirs(os.path.join(scripts, "cExtensions"))
    with open(os.path.join(scripts, "cExtensions", "startup.txt"), "w", encoding="utf-8") as h:
        h.write("debugger\nQT\n")
    with open(os.path.join(scripts, "ExtraMenuItems", "CoatMenu.xml"), "w", encoding="utf-8") as h:
        h.write("x\n")
    return root, scripts


def read(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def tree(root):
    found = []
    for base, _dirs, files in os.walk(root):
        for name in files:
            found.append(os.path.relpath(os.path.join(base, name), root).replace("\\", "/"))
    return sorted(found)


def main():
    tmp = tempfile.mkdtemp(prefix="coatlink_install_test.")
    checkout = load_installer()
    root, scripts = fresh(tmp, "a")
    target = os.path.join(scripts, "cExtensions", "CoatLink")
    startup = os.path.join(scripts, "cExtensions", "startup.txt")

    report = checkout.install(scripts)

    check("the extension folder is created", os.path.isdir(target), tree(root))
    missing = [name for name in checkout.SCRIPT_FILES
               if not os.path.isfile(os.path.join(target, name))]
    check("every file of the 3D-Coat half is installed", not missing, missing)
    check("the extension entry point is one of them",
          "CoatLink.py" in checkout.SCRIPT_FILES
          and os.path.isfile(os.path.join(target, "CoatLink.py")))
    check("startup.txt lists the extension", "CoatLink" in read(startup).split(), read(startup))
    check("a backup of the original startup.txt is kept",
          os.path.isfile(startup + ".bak") and read(startup + ".bak") == "debugger\nQT\n")
    check("installing again adds no second line",
          checkout.install(scripts) is not None and read(startup).count("CoatLink") == 1, read(startup))
    check("nothing is written outside 3D-Coat's user folder",
          all(name.startswith("UserPrefs/") for name in tree(root)), tree(root))
    check("no icon is installed any more", not any(name.endswith(".png") for name in tree(root)))
    check("the report says where it went",
          any("cExtensions" in note for note in report.notes), report.notes)

    # an install of the older build, straight in Scripts, is moved aside - by the
    # extension on its first start; the installer leaves it alone so nothing is lost
    classic = os.path.join(scripts, "CoatLink")
    os.makedirs(classic)
    with open(os.path.join(classic, "CoatLinkLib.py"), "w", encoding="utf-8") as h:
        h.write("old\n")
    checkout.install(scripts)
    check("a hand install is left for the extension to move aside",
          os.path.isdir(classic) and os.path.isdir(target))


    # ---- uninstall ----
    menu_dir = os.path.join(scripts, "ExtraMenuItems")
    for name in ("CoatLink.xml", "CoatLinkTools.xml", "CoatLink_Old.xml",
                 "CoatBridge.xml", "CoatBridgeTools.xml"):
        with open(os.path.join(menu_dir, name), "w", encoding="utf-8") as h:
            h.write("x\n")

    checkout.uninstall(scripts)

    check("uninstall removes the extension folder", not os.path.isdir(target), tree(root))
    check("and our line from startup.txt", "CoatLink" not in read(startup).split(), read(startup))
    check("other extensions stay listed", read(startup).split() == ["debugger", "QT"], read(startup))
    check("our menu files are gone",
          not os.path.exists(os.path.join(menu_dir, "CoatLink.xml"))
          and not os.path.exists(os.path.join(menu_dir, "CoatLinkTools.xml")))
    check("3D-Coat's insertion file for our id is gone",
          not os.path.exists(os.path.join(menu_dir, "CoatLink_Old.xml")))
    check("the pre-rename menu files are gone",
          not os.path.exists(os.path.join(menu_dir, "CoatBridge.xml"))
          and not os.path.exists(os.path.join(menu_dir, "CoatBridgeTools.xml")))
    check("somebody else's menu file is left alone",
          os.path.isfile(os.path.join(menu_dir, "CoatMenu.xml")))

    # ---- a full round trip on a second machine ----
    root2, scripts2 = fresh(tmp, "b")
    startup2 = os.path.join(scripts2, "cExtensions", "startup.txt")
    checkout.install(scripts2)
    checkout.uninstall(scripts2)
    check("a round trip leaves the user folder as it was",
          tree(root2) == ["UserPrefs/Scripts/ExtraMenuItems/CoatMenu.xml",
                          "UserPrefs/Scripts/cExtensions/startup.txt",
                          "UserPrefs/Scripts/cExtensions/startup.txt.bak"],
          tree(root2))
    check("and startup.txt is back to its two lines",
          read(startup2).split() == ["debugger", "QT"], read(startup2))

    failed = [name for name, ok, _detail in RESULTS if not ok]
    print("")
    print("RESULT: %d/%d checks passed" % (len(RESULTS) - len(failed), len(RESULTS)))
    if failed:
        print("FAILED: " + "; ".join(failed))
        return 1
    print("installer checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
