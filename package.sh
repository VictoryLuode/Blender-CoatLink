#!/usr/bin/env bash
# Build the release archives into dist/.
#
#   ./package.sh [version] [ref]      version defaults to the newest CHANGELOG
#                                     heading, ref defaults to HEAD
#
#   dist/CoatLink-<version>.zip          the Blender add-on on its own:
#                                        Edit > Preferences > Add-ons > Install from Disk
#   dist/CoatLink-<version>.3dcpack      the 3D-Coat half, in 3D-Coat's own package
#                                        format: Scripts > Install Extension
#   dist/CoatLink-<version>-full.zip     the whole project - sources, both
#                                        installers, tests - ready to unzip anywhere
#
# The product name and the version are in every file name, so a folder holding two
# releases cannot be mixed up.
#
# All of them are built from the committed tree (git archive), not from the working
# copy, so what people download is exactly what the repository holds.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO"

VERSION="${1:-$(grep -m1 '^## v' CHANGELOG.md | sed 's/^## //')}"
REF="${2:-HEAD}"
if [ -z "$VERSION" ]; then
    echo "no version found in CHANGELOG.md - pass one: ./package.sh v1.2.3" >&2
    exit 1
fi

ADDON="dist/CoatLink-$VERSION.zip"
FULL="dist/CoatLink-$VERSION-full.zip"
PACK="dist/CoatLink-$VERSION.3dcpack"
mkdir -p dist
rm -f "$ADDON" "$FULL" "$PACK"

# `git archive` asks the checkout configuration what line endings to write, and on a
# machine whose git defaults to CRLF that produced archives with CRLF while the
# repository stores LF - so the downloads differed from the sources.  Both settings are
# pinned here, which is what makes the archives equal the committed bytes.
ARCHIVE=(git -c core.autocrlf=false -c core.eol=lf archive --format=zip)

"${ARCHIVE[@]}" --prefix="coatlink/" "$REF:coatlink" -o "$ADDON"
"${ARCHIVE[@]}" --prefix="CoatLink-$VERSION/" "$REF" -o "$FULL"

# the 3D-Coat half as a .3dcpack - 3D-Coat's own package format, installed from its
# Scripts > Install Extension menu.  Staged from the committed sources like the
# archives above, so the package holds exactly what the repository holds.
PYTHON="$(command -v python3 || command -v python || true)"
if [ -z "$PYTHON" ]; then
    echo "note: no python found, skipped $PACK" >&2
else
    # staged inside dist/, not /tmp: git is a native Windows program and cannot write
    # to an MSYS path like /tmp/...
    STAGE="$(mktemp -d "dist/.stage.XXXXXX")"
    trap 'rm -rf "$STAGE"' EXIT
    # git archive writes a zip here; unpack it with unzip, not tar
    "${ARCHIVE[@]}" "$REF:coat_side" -o "$STAGE/coat_side.zip" || exit 1
    unzip -q "$STAGE/coat_side.zip" -d "$STAGE" || exit 1
    rm -f "$STAGE/coat_side.zip"
    "$PYTHON" "$STAGE/tools/pack_3dcpack.py" "$STAGE" "$PACK" >/dev/null || exit 1
fi

echo
for archive in "$ADDON" "$FULL" "$PACK"; do
    [ -f "$archive" ] && printf '%-44s %s\n' "$archive" "$(du -h "$archive" | cut -f1)"
done
echo
unzip -l "$ADDON" | tail -3
