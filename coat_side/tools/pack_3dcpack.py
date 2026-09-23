# SPDX-License-Identifier: GPL-3.0-or-later
"""Build 3D-Coat's own package format for the 3D-Coat half.

A ``.3dcpack`` is the tree to install, zipped, rooted at 3D-Coat's *data* folder -
so the entries here are ``UserPrefs/Scripts/cExtensions/CoatLink/...`` and 3D-Coat's
``Scripts > Install Extension`` puts them where the extension loader looks.

Nothing machine-specific goes in: the ``ExtraMenuItems`` XML files carry absolute
paths, so the extension writes them itself on its first start (see CoatLinkMenu),
and the tool buttons take 3D-Coat's default icon.

    python coat_side/tools/pack_3dcpack.py <source-dir> <out.3dcpack>
"""

import importlib.util
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent          # coat_side/tools
COAT_SIDE = HERE.parent                          # coat_side
PACKAGE_ROOT = "UserPrefs/Scripts/cExtensions/CoatLink/"


def script_files():
    """The file list the installer uses, so pack and installer cannot drift."""
    spec = importlib.util.spec_from_file_location("coatlink_install",
                                                  COAT_SIDE / "CoatLinkInstall.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.SCRIPT_FILES


def build(source, out_path, files=None):
    """Write the package; returns the entries it holds."""
    source = Path(source)
    names = list(files or script_files())
    missing = [name for name in names if not (source / name).is_file()]
    if missing:
        raise SystemExit("missing from %s: %s" % (source, ", ".join(missing)))
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            info = zipfile.ZipInfo(PACKAGE_ROOT + name)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            data = (source / name).read_bytes()
            archive.writestr(info, data.replace(b"\r\n", b"\n"))
    return [PACKAGE_ROOT + name for name in names]


def main(argv):
    if len(argv) != 3:
        raise SystemExit(__doc__.strip().splitlines()[-1].strip())
    entries = build(argv[1], argv[2])
    print("wrote %s (%d files)" % (argv[2], len(entries)))
    for entry in entries:
        print("  " + entry)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
