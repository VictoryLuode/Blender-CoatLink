#!/usr/bin/env bash
# The Windows installer (install.ps1) must land exactly what the bash installer
# lands - same files, same two XML files, byte for byte once the install root is
# normalised.  PowerShell 5.1 ships with Windows, so this is what a user without
# bash or git will actually run.

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PS="$(command -v powershell.exe || true)"
if [ -z "$PS" ]; then
    echo "powershell.exe not found - skipping the PowerShell installer test"
    exit 0
fi

TMP="$(mktemp -d "${LOCALAPPDATA:-/tmp}/coatlink_ps1_test.XXXXXX")"
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

# two identical trees, one per installer
A="$TMP/bash"
B="$TMP/ps1"
for root in "$A" "$B"; do
    mkdir -p "$root/blender/5.2/scripts/addons" \
             "$root/Documents/3DCoat/UserPrefs/Scripts" \
             "$root/3DCoat-2026/data/Textures/icons64"
done

bash "$REPO/install.sh" "$A/blender/5.2/scripts/addons" \
     "$A/Documents/3DCoat/UserPrefs/Scripts" "$A/3DCoat-2026" > "$TMP/bash.log" 2>&1
[ $? -eq 0 ] && check "the bash installer ran" yes || check "the bash installer ran" no "$(tail -3 "$TMP/bash.log")"

# PowerShell must not have the MSYS path converter rewrite these
MSYS2_ARG_CONV_EXCL='*' "$PS" -NoProfile -ExecutionPolicy Bypass \
    -File "$(cygpath -w "$REPO/install.ps1")" \
    -BlenderAddons "$(cygpath -w "$B/blender/5.2/scripts/addons")" \
    -CoatScripts "$(cygpath -w "$B/Documents/3DCoat/UserPrefs/Scripts")" \
    -CoatDir "$(cygpath -w "$B/3DCoat-2026")" > "$TMP/ps1.log" 2>&1
[ $? -eq 0 ] && check "the PowerShell installer ran" yes || check "the PowerShell installer ran" no "$(tail -5 "$TMP/ps1.log")"
grep -qi "Exception\|Traceback\|not recognized" "$TMP/ps1.log" \
    && check "the PowerShell installer reported no error" no "$(head -5 "$TMP/ps1.log")" \
    || check "the PowerShell installer reported no error" yes

# same file list, relative to each root
( cd "$A" && find . -type f | sort ) > "$TMP/list.bash"
( cd "$B" && find . -type f | sort ) > "$TMP/list.ps1"
if diff -q "$TMP/list.bash" "$TMP/list.ps1" > /dev/null; then
    check "both installers landed the same files" yes
else
    check "both installers landed the same files" no "$(diff "$TMP/list.bash" "$TMP/list.ps1" | head -6)"
fi

# same contents, once each root is replaced by a placeholder (the XMLs carry the
# absolute install path, which is the point of an installer)
norm() {  # norm <file> <root>  - the XMLs carry the install path, in the
          # forward-slash Windows form both installers write
    sed "s|$(cygpath -m "$2")|ROOT|g" "$1" | tr -d '\r'
}
differed=""
while IFS= read -r rel; do
    [ -z "$rel" ] && continue
    if ! diff -q <(norm "$A/$rel" "$A") <(norm "$B/$rel" "$B") > /dev/null; then
        differed="$differed $rel"
    fi
done < "$TMP/list.bash"
if [ -z "$differed" ]; then
    check "every installed file is byte-identical" yes
else
    check "every installed file is byte-identical" no "differs:$differed"
fi

# the XML really points into the tree it was installed into
grep -q "script:$(cygpath -m "$B/Documents/3DCoat/UserPrefs/Scripts")/CoatBridge/CoatBridge_Setup.py" \
    "$B/Documents/3DCoat/UserPrefs/Scripts/ExtraMenuItems/CoatBridge.xml" \
    && check "the XML points at the installed script folder" yes \
    || check "the XML points at the installed script folder" no "$(cat "$B/Documents/3DCoat/UserPrefs/Scripts/ExtraMenuItems/CoatBridge.xml")"

# idempotent
MSYS2_ARG_CONV_EXCL='*' "$PS" -NoProfile -ExecutionPolicy Bypass \
    -File "$(cygpath -w "$REPO/install.ps1")" -BlenderOnly \
    -BlenderAddons "$(cygpath -w "$B/blender/5.2/scripts/addons")" > /dev/null 2>&1
[ -f "$B/blender/5.2/scripts/addons/coat_bridge/__init__.py" ] \
    && check "a second run is harmless" yes || check "a second run is harmless" no

# Automatic detection must sort version directories, not identical 'addons' leaves.
AUTO="$TMP/autodetect"
for version in 3.6 4.0 4.1 4.2 4.3 4.4 4.5 5.0 5.1 5.2 5.9 5.10 backup; do
    mkdir -p "$AUTO/$version/scripts/addons"
done
BLENDER_CONFIG_DIR="$(cygpath -w "$AUTO")" BLENDER_ADDON_DIR='' \
MSYS2_ARG_CONV_EXCL='*' "$PS" -NoProfile -ExecutionPolicy Bypass \
    -File "$(cygpath -w "$REPO/install.ps1")" -BlenderOnly > "$TMP/auto.log" 2>&1
auto_status=$?
if [ "$auto_status" -eq 0 ] && [ -f "$AUTO/5.10/scripts/addons/coat_bridge/__init__.py" ]; then
    check "automatic detection selects the highest numeric Blender version" yes
else
    check "automatic detection selects the highest numeric Blender version" no
fi
for version in 3.6 4.0 4.1 4.2 4.3 4.4 4.5 5.0 5.1 5.2 5.9 backup; do
    [ ! -d "$AUTO/$version/scripts/addons/coat_bridge" ] \
        && check "automatic detection leaves $version alone" yes \
        || check "automatic detection leaves $version alone" no
done

if [ "$failed" -eq 0 ]; then
    echo
    echo "POWERSHELL INSTALLER TEST PASSED"
else
    echo
    echo "POWERSHELL INSTALLER TEST FAILED" >&2
fi
exit "$failed"
