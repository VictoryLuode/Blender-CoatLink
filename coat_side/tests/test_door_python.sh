#!/usr/bin/env bash
# The Windows doors have to find 3D-Coat's bundled Python wherever it really is.
#
# It ships inside 3D-Coat's *Documents* folder, and %USERPROFILE%\Documents is
# only a guess - redirect Documents to OneDrive and the folder moves with it while
# the old path stops existing.  install.cmd used to look in exactly one place, so
# on such a machine it would have said "No Python found" next to a working install.
#
# This runs the real door against a fake Documents folder and checks which Python
# it picked, by name, from the door's own output.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
FAILURES=0

check() {
    if [ "$2" = "1" ]; then echo "PASS $1"; else echo "FAIL $1  -> $3"; FAILURES=$((FAILURES + 1)); fi
}

# a stand-in python.exe: only has to exist, the door prints the path before using it
FAKE_HOME="$TMP/home"
PY_DIR="$FAKE_HOME/OneDrive/Documents/3DCoat/python-3.11"
mkdir -p "$PY_DIR"
cp "$(cygpath -u "$SYSTEMROOT")/System32/cmd.exe" "$PY_DIR/python.exe" 2>/dev/null \
    || cp "/c/Windows/System32/cmd.exe" "$PY_DIR/python.exe"
DOCS="$(cygpath -w "$FAKE_HOME/OneDrive/Documents")"

out="$(cd "$REPO" && USERPROFILE="$(cygpath -w "$FAKE_HOME")" COATLINK_DOCS="$DOCS" \
        cmd.exe /c install.cmd </dev/null 2>&1)"
echo "$out" | grep -q "Using .*python-3.11.python.exe" \
    && check "install.cmd finds the Python under a redirected Documents" 1 \
    || check "install.cmd finds the Python under a redirected Documents" 0 "$out"

# and the downloading door has to carry the same detection - the two must not drift
for name in 'COATLINK_DOCS' 'OneDrive' 'python-\*' 'reg query'; do
    grep -q "$name" "$REPO/CoatLink-Setup.cmd" \
        && check "CoatLink-Setup.cmd carries: $name" 1 \
        || check "CoatLink-Setup.cmd carries: $name" 0 "missing"
done
grep -q "COATLINK_DOCS" "$REPO/install.ps1" \
    && check "install.ps1 honours COATLINK_DOCS" 1 || check "install.ps1 honours COATLINK_DOCS" 0 "missing"

echo
if [ "$FAILURES" -eq 0 ]; then echo "door python checks passed"; else echo "SOME DOOR CHECKS FAILED"; fi
exit "$FAILURES"
