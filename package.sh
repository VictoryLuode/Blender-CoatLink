#!/usr/bin/env bash
# Build the release archives into dist/.
#
#   ./package.sh [version]     version defaults to the newest CHANGELOG heading
#
#   dist/coat_bridge.zip                 the Blender add-on on its own:
#                                        Edit > Preferences > Add-ons > Install from Disk
#   dist/Blender-CoatLink-<version>.zip  the whole project - sources, both
#                                        installers, tests - ready to unzip anywhere

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO"

VERSION="${1:-$(grep -m1 '^## v' CHANGELOG.md | sed 's/^## //')}"
if [ -z "$VERSION" ]; then
    echo "no version found in CHANGELOG.md - pass one: ./package.sh v1.2.3" >&2
    exit 1
fi

python3 - "$VERSION" <<'PY'
import os
import subprocess
import sys
import zipfile

version = sys.argv[1]
STAMP = (2026, 1, 1, 0, 0, 0)          # fixed, so the zips are reproducible


def add(zf, path, arcname, executable=False):
    info = zipfile.ZipInfo(arcname.replace(os.sep, "/"), date_time=STAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = (0o755 if executable else 0o644) << 16
    with open(path, "rb") as handle:
        zf.writestr(info, handle.read())


os.makedirs("dist", exist_ok=True)

# 1. the Blender add-on, exactly as "Install from Disk" wants it
with zipfile.ZipFile("dist/coat_bridge.zip", "w") as zf:
    for root, dirs, files in os.walk("coat_bridge"):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__")
        for name in sorted(files):
            if name.endswith(".pyc"):
                continue
            path = os.path.join(root, name)
            add(zf, path, path)

# 2. the whole project: every tracked file, under one top-level folder
tracked = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True).stdout.splitlines()
top = "Blender-CoatLink-%s" % version
with zipfile.ZipFile("dist/Blender-CoatLink-%s.zip" % version, "w") as zf:
    for rel in tracked:
        if not rel or not os.path.isfile(rel):
            continue
        add(zf, rel, "%s/%s" % (top, rel), executable=os.access(rel, os.X_OK))
PY

echo
for archive in dist/*.zip; do
    printf '%-40s %s\n' "$archive" "$(du -h "$archive" | cut -f1)"
done
