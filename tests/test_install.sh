#!/usr/bin/env bash
# Install smoke test for the Blender side.
#
# Runs the real ./install.sh into a throwaway tree, checks what landed on both
# halves, then makes Blender actually enable the add-on from that tree - a copy
# list that is only verified by hand broke this project once already.

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=tests/find_tools.sh
source "$REPO/tests/find_tools.sh"

BLENDER_BIN="$(find_blender || true)"
[ -n "$BLENDER_BIN" ] || { echo "no Blender found (set BLENDER=...)"; exit 2; }

TMP="$(mktemp -d "${LOCALAPPDATA:-/tmp}/coatlink_install_test.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT

failed=0
check() {  # check <name> <yes|no> [detail]
    if [ "$2" = "yes" ]; then
        echo "PASS $1"
    else
        echo "FAIL $1${3:+ - $3}"
        failed=1
    fi
}

ADDONS="$TMP/blender/5.2/scripts/addons"
SCRIPTS="$TMP/Documents/3DCoat/UserPrefs/Scripts"
COAT="$TMP/3DCoat-2026"
mkdir -p "$ADDONS" "$SCRIPTS" "$COAT/data/Textures/icons64"

bash "$REPO/install.sh" "$ADDONS" "$SCRIPTS" "$COAT" > "$TMP/install.log" 2>&1
[ -s "$TMP/install.log" ] && check "the installer says what it did" yes \
    || check "the installer says what it did" no "silent"
grep -q "Traceback\|No such file\|not found" "$TMP/install.log" \
    && check "the installer reported no problem" no "$(cat "$TMP/install.log")" \
    || check "the installer reported no problem" yes

for name in __init__.py applink.py bridge.py receipts.py transfer.py ui.py watcher.py; do
    [ -f "$ADDONS/coatlink/$name" ] && check "installed coatlink/$name" yes \
        || check "installed coatlink/$name" no
done
[ -z "$(find "$ADDONS/coatlink" -name __pycache__ -print -quit)" ] \
    && check "no byte-code cache in the installed add-on" yes \
    || check "no byte-code cache in the installed add-on" no

# both halves are installed by the same command: the 3D-Coat half as an extension,
# so what matters is the folder and the startup list - the menu XML files are written
# by the extension itself the first time 3D-Coat starts it
[ -f "$SCRIPTS/cExtensions/CoatLink/CoatLinkLib.py" ] \
    && check "installed the 3D-Coat half too" yes || check "installed the 3D-Coat half too" no
grep -qx "CoatLink" "$SCRIPTS/cExtensions/startup.txt" \
    && check "3D-Coat is told to load it" yes || check "3D-Coat is told to load it" no

# the real proof: Blender boots with that script folder and enables the add-on
out="$(BLENDER_USER_SCRIPTS="$(cygpath -w "$TMP/blender/5.2/scripts")" \
    "$BLENDER_BIN" --background --factory-startup --python-exit-code 1 \
    --python-expr "import bpy; bpy.ops.preferences.addon_enable(module='coatlink'); a = bpy.context.preferences.addons.get('coatlink'); print('ADDON-ENABLED', a.module if a else 'MISSING')" 2>&1)"
case "$out" in
    *"ADDON-ENABLED coatlink"*) check "Blender enables the installed copy" yes ;;
    *)                             check "Blender enables the installed copy" no "$(printf '%s' "$out" | tail -6)" ;;
esac

# --coat-only must leave the Blender tree alone
ADDONS2="$TMP/blender-only/scripts/addons"
mkdir -p "$ADDONS2"
bash "$REPO/install.sh" --coat-only "$ADDONS2" "$SCRIPTS" "$COAT" > /dev/null 2>&1
[ -z "$(find "$ADDONS2" -mindepth 1 -print -quit)" ] \
    && check "--coat-only leaves the Blender side alone" yes \
    || check "--coat-only leaves the Blender side alone" no

# git-bash hands every path over as /c/Users/..., and the installer is a Windows
# program's Python that cannot resolve one: a bare MSYS path used to arrive as
# \c\Users\... and the install stopped with "script folder was not found".  The
# three positional slots are fixed (add-ons, scripts, program) whatever the flags
# are, so --coat-only still fills the add-ons slot with something ignored.
if command -v cygpath >/dev/null 2>&1; then
    MSYS_TMP="$(cygpath -u "$TMP")"
    rm -rf "$SCRIPTS/cExtensions"
    bash "$REPO/install.sh" --coat-only "$ADDONS2" "$MSYS_TMP/Documents/3DCoat/UserPrefs/Scripts" \
        "$MSYS_TMP/3DCoat-2026" > "$TMP/msys-install.log" 2>&1
    [ -f "$SCRIPTS/cExtensions/CoatLink/CoatLinkLib.py" ] \
        && check "an MSYS-style path installs the 3D-Coat half too" yes \
        || check "an MSYS-style path installs the 3D-Coat half too" no "$(tail -3 "$TMP/msys-install.log")"
fi

# an older build called itself `coat_bridge`: installing over it must move that folder out
# of Blender's search path (kept on disk, not deleted) instead of leaving two CoatLinks
mkdir -p "$ADDONS/coat_bridge"
echo "old build" > "$ADDONS/coat_bridge/OLD-BUILD.txt"
bash "$REPO/install.sh" "$ADDONS" "$SCRIPTS" "$COAT" > "$TMP/upgrade.log" 2>&1
[ -f "$ADDONS/coatlink/__init__.py" ] \
    && check "installing over an older build still lands the add-on" yes \
    || check "installing over an older build still lands the add-on" no
[ -d "$ADDONS/coat_bridge" ] \
    && check "the older coat_bridge folder leaves Blender's search path" no \
    || check "the older coat_bridge folder leaves Blender's search path" yes
moved="$(find "$(dirname "$ADDONS")" -maxdepth 1 -name 'coat_bridge.removed-*' -type d -print -quit)"
if [ -n "$moved" ] && [ -f "$moved/OLD-BUILD.txt" ]; then
    check "the older build is kept beside the add-ons folder, not deleted" yes
else
    check "the older build is kept beside the add-ons folder, not deleted" no "moved=$moved"
fi
grep -q "moved the older coat_bridge build aside" "$TMP/upgrade.log" \
    && check "the installer says where the older build went" yes \
    || check "the installer says where the older build went" no

# idempotent
bash "$REPO/install.sh" "$ADDONS" "$SCRIPTS" "$COAT" > /dev/null 2>&1
[ -f "$ADDONS/coatlink/__init__.py" ] && check "a second install is harmless" yes \
    || check "a second install is harmless" no

if [ "$failed" -eq 0 ]; then
    echo
    echo "BLENDER INSTALL SMOKE TEST PASSED"
else
    echo
    echo "BLENDER INSTALL SMOKE TEST FAILED" >&2
fi
exit "$failed"
