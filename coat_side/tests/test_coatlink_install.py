# SPDX-License-Identifier: GPL-3.0-or-later
"""One installer, several doors - and it must not touch anything that is not ours.

Checks, on plain Python with no 3D-Coat present:

  * the single file in dist/ carries exactly the same files as the checkout
  * installing with either one produces byte-identical trees
  * the generated menu XMLs hold this machine's paths, with no placeholder left
  * running twice changes nothing, and stale layouts are cleared out
  * unrelated files in the same folders survive install and uninstall
  * an unwritable icon folder is reported, not fatal
"""

import importlib.util
import io
import os
import shutil
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
COAT_SIDE = HERE.parent
ROOT = COAT_SIDE.parent
sys.path.insert(0, str(COAT_SIDE))
sys.path.insert(0, str(HERE))

import CoatLinkInstall as checkout                       # noqa: E402
from tools import build_standalone                       # noqa: E402

FAILURES = []


def check(name, ok, detail=None):
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> %r" % (detail,)))
    if not ok:
        FAILURES.append(name)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def tree(root):
    """Every file under root: relative path (forward slashes) -> bytes."""
    return {str(p.relative_to(root)).replace("\\", "/"): p.read_bytes()
            for p in sorted(Path(root).rglob("*")) if p.is_file()}


def normalise(blob, root):
    """Erase one install root from a file's contents.

    The menu XMLs hold the absolute path of the folder they point at - that is the
    whole reason they are generated - so two installs in different folders can
    only be compared after that one difference is normalised away.
    """
    for form in (str(root), str(root).replace("\\", "/"), str(root).replace("/", "\\")):
        blob = blob.replace(form.encode("utf-8"), b"<ROOT>")
    return blob


def comparable(root):
    return {name: normalise(blob, root) for name, blob in tree(root).items()}


def fresh(tmp):
    scripts = Path(tmp) / "Scripts"
    coat = Path(tmp) / "3DCoat"
    (coat / "data" / "Textures" / "icons64").mkdir(parents=True)
    scripts.mkdir(parents=True)
    return scripts, coat


def main():
    tmp = Path(tempfile.mkdtemp(prefix="coatlink_install."))

    # ---- the single file carries the same payload ------------------------------
    standalone_path = Path(tmp) / "built" / "CoatLink-Setup.py"
    build_standalone.build(standalone_path)
    standalone = load(standalone_path, "coatlink_standalone")

    same = checkout.read_payload()
    other = standalone.read_payload()
    check("embedded payload matches the checkout payload",
          same["scripts"] == other["scripts"] and same["icons"] == other["icons"]
          and same["tools_xml"] == other["tools_xml"],
          sorted(same["scripts"]))

    # ---- installing with either one gives the same tree ------------------------
    a_scripts, a_coat = fresh(tmp / "a")
    b_scripts, b_coat = fresh(tmp / "b")
    checkout.install(a_scripts, a_coat, payload=same)
    standalone.install(b_scripts, b_coat, payload=other)
    left, right = comparable(tmp / "a"), comparable(tmp / "b")
    check("both installers write an identical tree",
          left == right,
          sorted(set(left) ^ set(right))
          or [k for k in left if left[k] != right.get(k)])

    # ---- the scripts really are the project's files ---------------------------
    written = a_scripts / "CoatBridge"
    for name in checkout.SCRIPT_FILES:
        source = COAT_SIDE / name
        check("%s is byte-identical to the source" % name,
              (written / name).read_bytes() == source.read_bytes())

    # ---- menu XMLs: real paths, no placeholder --------------------------------
    menu = a_scripts / "ExtraMenuItems"
    expected = str(written).replace("\\", "/")
    script_xml = (menu / "CoatBridge.xml").read_text(encoding="utf-8")
    tools_xml = (menu / "CoatBridgeTools.xml").read_text(encoding="utf-8")
    check("the Scripts entry points at this machine's path",
          ("script:%s/CoatBridge_Setup.py" % expected) in script_xml, script_xml[:120])
    check("the tool buttons point at this machine's path",
          tools_xml.count("script:%s/" % expected) == 6, tools_xml.count("script:"))
    check("no placeholder survives",
          checkout.PLACEHOLDER not in script_xml and checkout.PLACEHOLDER not in tools_xml)
    check("both rooms get all three buttons",
          tools_xml.count("<inRoom>Voxels</inRoom>") == 3
          and tools_xml.count("<inRoom>Paint</inRoom>") == 3)

    # ---- icons land beside 3D-Coat's own --------------------------------------
    for name in checkout.ICON_FILES:
        check("icon %s installed" % name,
              (a_coat / "data" / "Textures" / "icons64" / name).read_bytes()
              == (COAT_SIDE / "icon" / name).read_bytes())

    # ---- other people's files stay put ----------------------------------------
    theirs_script = a_scripts / "CoatBridge" / "SomebodyElses.py"
    theirs_menu = a_scripts / "ExtraMenuItems" / "SomebodyElses.xml"
    theirs_script.write_bytes(b"mine\n")
    theirs_menu.write_bytes(b"mine\n")

    # ---- stale layouts are cleared --------------------------------------------
    for stale in ("CoatBridgeQt.py", "CoatBridge.py", "CoatBridgeScopedExport.py"):
        (a_scripts / "CoatBridge" / stale).write_text("old\n", encoding="utf-8")
    before = tree(a_scripts)
    report = checkout.install(a_scripts, a_coat, payload=same)
    after = tree(a_scripts)
    check("a second install is harmless and still reports ok", report.verified)
    check("stale files from earlier layouts are gone",
          not any(k.endswith("CoatBridgeQt.py") or k.endswith("CoatBridgeScopedExport.py")
                  for k in after), sorted(k for k in after if "Coat" in k))
    check("unrelated files survive an install",
          after["CoatBridge/SomebodyElses.py"] == b"mine\n"
          and after["ExtraMenuItems/SomebodyElses.xml"] == b"mine\n")
    check("only our files differ between the first and the second install",
          set(before) - set(after) <= {"CoatBridge/" + name
                                       for name in checkout.STALE_FILES},
          sorted(set(before) - set(after)))

    # ---- the 3D-Coat program folder is found, or overridden ------------------
    found = checkout.program_dir()
    check("the 3D-Coat program folder is found on this machine",
          bool(found) and (Path(found) / "data").is_dir(), found)
    override = tmp / "overridden_coat"
    (override / "data" / "Textures" / "icons64").mkdir(parents=True)
    os.environ["COATLINK_COAT_DIR"] = str(override)
    try:
        check("COATLINK_COAT_DIR overrides the search",
              Path(checkout.program_dir()) == override, checkout.program_dir())
        checkout.install(a_scripts, checkout.program_dir(), payload=same)
        check("icons land in the folder that was found",
              (override / "data" / "Textures" / "icons64" / "CoatBridge.png").is_file())
    finally:
        del os.environ["COATLINK_COAT_DIR"]

    # ---- unwritable icon folder is reported, not fatal ------------------------
    no_icons = Path(tmp) / "no_coat_here"
    quiet_report = checkout.install(a_scripts, no_icons, payload=same)
    check("a missing 3D-Coat folder only skips the icons",
          quiet_report.verified and any("icons skipped" in note for note in quiet_report.notes),
          quiet_report.notes)

    # ---- uninstall removes ours and nothing else -----------------------------
    removed = checkout.uninstall(a_scripts, a_coat)
    left = sorted(tree(a_scripts))
    expected = sorted([str(theirs_script.relative_to(a_scripts)).replace("\\", "/"),
                       str(theirs_menu.relative_to(a_scripts)).replace("\\", "/")])
    check("our scripts and menus are gone", left == expected, left)
    check("unrelated files are still there", left == expected, left)
    check("uninstall reports what it removed",
          any(str(p).endswith("CoatBridgeLib.py") for p in removed.removed))
    check("the icons are gone too",
          not any((a_coat / "data" / "Textures" / "icons64" / n).exists()
                  for n in checkout.ICON_FILES))

    # ---- the command line works, and says what it did ------------------------
    c_scripts, c_coat = fresh(tmp / "c")
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = checkout.main(["--scripts", str(c_scripts), "--coat", str(c_coat)])
    printed = buffer.getvalue()
    check("the command line installs and returns 0", code == 0, code)
    check("it names the Scripts menu and the buttons",
          "Scripts > CoatLink" in printed and "tool lists" in printed, printed[:200])
    check("a missing scripts folder is refused", checkout.main(["--scripts", str(Path(tmp) / "nope")]) == 1)
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = checkout.main(["--scripts", str(c_scripts), "--coat", str(c_coat), "--uninstall"])
    check("the command line uninstalls", code == 0 and not (c_scripts / "CoatBridge").exists())

    # ---- nothing outside the two folders was touched --------------------------
    outside = sorted(str(p.relative_to(tmp)).replace("\\", "/")
                     for p in Path(tmp).rglob("*") if p.is_file())
    check("nothing was written outside the script and icon folders",
          all(name.startswith(("a/", "b/", "c/", "built/", "overridden_coat/"))
              for name in outside),
          [name for name in outside
           if not name.startswith(("a/", "b/", "c/", "built/", "overridden_coat/"))][:5])

    shutil.rmtree(tmp, ignore_errors=True)
    print("\nRESULT: %s" % ("installer checks passed" if not FAILURES
                            else "FAILED: " + ", ".join(FAILURES)))
    sys.stdout.flush()
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
