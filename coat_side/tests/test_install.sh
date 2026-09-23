#!/usr/bin/env bash
# Install smoke test: run the real installer into a throwaway tree and check
# what landed.  install.sh is the one part of this project that used to be
# verified only by hand - and a hand-edited copy list broke it silently once.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# a temp tree on a real drive: install.sh writes C:/... paths (cygpath -m) and the
# XML check has to be able to resolve them again
TMP="$(mktemp -d "${LOCALAPPDATA:-/tmp}/coat_install_test.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT

failed=0
check() {  # check <name> <condition-result>
    if [ "$2" = "yes" ]; then echo "PASS $1"; else echo "FAIL $1"; failed=1; fi
}

SCRIPTS="$TMP/Documents/3DCoat/UserPrefs/Scripts"
COAT="$TMP/3DCoat-2026"
mkdir -p "$SCRIPTS" "$COAT/data/Textures/icons64"

PYTHON="$(command -v python3 || command -v python || true)"
if [ -z "$PYTHON" ]; then echo "no python on PATH"; exit 1; fi

bash "$REPO/coat_side/install.sh" "$SCRIPTS" "$COAT" > "$TMP/install.log" 2>&1
[ -s "$TMP/install.log" ] && echo "PASS the installer says what it did" || { echo "FAIL installer quiet"; failed=1; }
grep -q "Traceback\|not found\|No such file" "$TMP/install.log" && { echo "FAIL installer reported a problem"; cat "$TMP/install.log"; failed=1; }

for name in CoatLink.py CoatLinkLib.py CoatLinkMenu.py CoatLink_Send.py CoatLink_Pull.py CoatLink_Setup.py; do
    [ -f "$SCRIPTS/cExtensions/CoatLink/$name" ] && check "installed $name" yes || check "installed $name" no
done
grep -qx "CoatLink" "$SCRIPTS/cExtensions/startup.txt" && check "startup.txt lists the extension" yes \
    || check "startup.txt lists the extension" no

# The menu files are the extension's job, not the installer's: they hold this
# machine's absolute paths, so they are written when 3D-Coat starts the extension
# (the Python tests cover that writing).  The installer must leave none behind.
[ -z "$(ls -A "$SCRIPTS/ExtraMenuItems" 2>/dev/null)" ] && echo "PASS the installer writes no menu file" \
    || { echo "FAIL the installer wrote a menu file"; failed=1; }

# every script the extension will point at must be installed beside it
missing=""
for name in CoatLink_Send.py CoatLink_Pull.py CoatLink_Setup.py; do
    [ -f "$SCRIPTS/cExtensions/CoatLink/$name" ] || missing="$missing $name"
done
if [ -z "$missing" ]; then check "the extension has every script its menu will name" yes
else check "missing scripts:$missing" no; fi

# idempotent: a second run must not break anything, or list the extension twice
bash "$REPO/coat_side/install.sh" "$SCRIPTS" "$COAT" > /dev/null 2>&1
[ -f "$SCRIPTS/cExtensions/CoatLink/CoatLinkLib.py" ] && echo "PASS a second install is harmless" || { echo "FAIL reinstall"; failed=1; }
[ "$(grep -cx "CoatLink" "$SCRIPTS/cExtensions/startup.txt")" = "1" ] && echo "PASS the extension is listed once" \
    || { echo "FAIL the extension is listed twice"; failed=1; }

# nothing is written into the program folder any more: the tool buttons take
# 3D-Coat's default icon, so no icon and no Program Files permission is involved
[ -z "$(ls -A "$COAT/data/Textures/icons64")" ] && echo "PASS the program folder is untouched" \
    || { echo "FAIL something was written into the program folder"; failed=1; }

if [ "$failed" -eq 0 ]; then echo "\nINSTALL SMOKE TEST PASSED"; else echo "\nINSTALL SMOKE TEST FAILED"; fi
exit "$failed"
