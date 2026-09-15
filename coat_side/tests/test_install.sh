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

bash "$REPO/coat_side/install.sh" "$SCRIPTS" "$COAT" > "$TMP/install.log" 2>&1
[ -s "$TMP/install.log" ] && echo "PASS the installer says what it did" || { echo "FAIL installer quiet"; failed=1; }
grep -q "Traceback\|not found\|No such file" "$TMP/install.log" && { echo "FAIL installer reported a problem"; cat "$TMP/install.log"; failed=1; }

for name in CoatBridgeLib.py CoatBridge_Send.py CoatBridge_Pull.py CoatBridge_Setup.py; do
    [ -f "$SCRIPTS/CoatBridge/$name" ] && check "installed $name" yes || check "installed $name" no
done
for name in CoatBridgeTools.xml CoatBridge.xml; do
    [ -f "$SCRIPTS/ExtraMenuItems/$name" ] && check "installed $name" yes || check "installed $name" no
done

# every script the XMLs point at must exist, and nothing stale may be referenced
entries=0
bad=""
for name in CoatBridgeTools.xml CoatBridge.xml; do
    path="$SCRIPTS/ExtraMenuItems/$name"
    while read -r target; do
        target="${target#script:}"
        entries=$((entries + 1))
        # script:C:/Users/... -> /c/Users/...
        host="/c${target#C:}"
        [ -f "$host" ] || bad="$bad $name->$(basename "$target")"
    done < <(grep -o 'script:[^<]*' "$path" 2>/dev/null)
    if grep -q "CoatBridgeDialog\.py\|CoatBridgeQt\.py" "$path" 2>/dev/null; then
        bad="$bad $name-references-deleted-entry"
    fi
done
if [ -z "$bad" ]; then check "every XML entry points at a real script ($entries entries)" yes
else check "XML references broken:$bad" no; fi

# idempotent: a second run must not break anything
bash "$REPO/coat_side/install.sh" "$SCRIPTS" "$COAT" > /dev/null 2>&1
[ -f "$SCRIPTS/CoatBridge/CoatBridgeLib.py" ] && echo "PASS a second install is harmless" || { echo "FAIL reinstall"; failed=1; }

if [ "$failed" -eq 0 ]; then echo "\nINSTALL SMOKE TEST PASSED"; else echo "\nINSTALL SMOKE TEST FAILED"; fi
exit "$failed"
