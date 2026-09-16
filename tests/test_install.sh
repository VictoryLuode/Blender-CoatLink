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
    [ -f "$ADDONS/coat_bridge/$name" ] && check "installed coat_bridge/$name" yes \
        || check "installed coat_bridge/$name" no
done
[ -z "$(find "$ADDONS/coat_bridge" -name __pycache__ -print -quit)" ] \
    && check "no byte-code cache in the installed add-on" yes \
    || check "no byte-code cache in the installed add-on" no

# both halves are installed by the same command
[ -f "$SCRIPTS/CoatBridge/CoatBridgeLib.py" ] \
    && check "installed the 3D-Coat half too" yes || check "installed the 3D-Coat half too" no
[ -f "$SCRIPTS/ExtraMenuItems/CoatBridge.xml" ] \
    && check "installed the 3D-Coat menu entry" yes || check "installed the 3D-Coat menu entry" no

# the real proof: Blender boots with that script folder and enables the add-on
out="$(BLENDER_USER_SCRIPTS="$(cygpath -w "$TMP/blender/5.2/scripts")" \
    "$BLENDER_BIN" --background --factory-startup --python-exit-code 1 \
    --python-expr "import bpy; bpy.ops.preferences.addon_enable(module='coat_bridge'); a = bpy.context.preferences.addons.get('coat_bridge'); print('ADDON-ENABLED', a.module if a else 'MISSING')" 2>&1)"
case "$out" in
    *"ADDON-ENABLED coat_bridge"*) check "Blender enables the installed copy" yes ;;
    *)                             check "Blender enables the installed copy" no "$(printf '%s' "$out" | tail -6)" ;;
esac

# --coat-only must leave the Blender tree alone
ADDONS2="$TMP/blender-only/scripts/addons"
mkdir -p "$ADDONS2"
bash "$REPO/install.sh" --coat-only "$SCRIPTS" "$COAT" > /dev/null 2>&1
[ -z "$(find "$ADDONS2" -mindepth 1 -print -quit)" ] \
    && check "--coat-only leaves the Blender side alone" yes \
    || check "--coat-only leaves the Blender side alone" no

# idempotent
bash "$REPO/install.sh" "$ADDONS" "$SCRIPTS" "$COAT" > /dev/null 2>&1
[ -f "$ADDONS/coat_bridge/__init__.py" ] && check "a second install is harmless" yes \
    || check "a second install is harmless" no

if [ "$failed" -eq 0 ]; then
    echo
    echo "BLENDER INSTALL SMOKE TEST PASSED"
else
    echo
    echo "BLENDER INSTALL SMOKE TEST FAILED" >&2
fi
exit "$failed"
