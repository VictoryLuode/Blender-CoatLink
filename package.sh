#!/usr/bin/env bash
# Build the release archives into dist/.
#
#   ./package.sh [version] [ref]      version defaults to the newest CHANGELOG
#                                     heading, ref defaults to HEAD
#
#   dist/coat_bridge.zip                 the Blender add-on on its own:
#                                        Edit > Preferences > Add-ons > Install from Disk
#   dist/Blender-CoatLink-<version>.zip  the whole project - sources, both
#                                        installers, tests - ready to unzip anywhere
#
# Both are built from the committed tree (git archive), not from the working
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

FULL="dist/Blender-CoatLink-$VERSION.zip"
mkdir -p dist
rm -f dist/coat_bridge.zip "$FULL"

git archive --format=zip --prefix="coat_bridge/" "$REF:coat_bridge" -o dist/coat_bridge.zip
git archive --format=zip --prefix="Blender-CoatLink-$VERSION/" "$REF" -o "$FULL"

echo
for archive in dist/coat_bridge.zip "$FULL"; do
    printf '%-44s %s\n' "$archive" "$(du -h "$archive" | cut -f1)"
done
echo
unzip -l dist/coat_bridge.zip | tail -3
