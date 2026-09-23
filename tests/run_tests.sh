#!/usr/bin/env bash
# Headless end-to-end test for CoatLink.
#
#   tests/run_tests.sh [path/to/blender.exe]
#
# Blender gets throwaway script and config folders, so the add-on is enabled and
# driven without touching the real user configuration or the real 3D-Coat folder.
# Every regression script under tests/ is run in its own Blender session: they all
# exercise the same add-on, and one aborted session must not hide the rest.

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=tests/find_tools.sh
source "$REPO/tests/find_tools.sh"
BLENDER="${1:-$(find_blender || true)}"
if [ -z "$BLENDER" ]; then
    echo "no Blender found - pass one: tests/run_tests.sh /path/to/blender.exe" >&2
    exit 2
fi
WORK="$(mktemp -d "${LOCALAPPDATA:-/tmp}/coatlink_test.XXXXXX")"
WIN_WORK="$(cygpath -w "$WORK")"
WIN_REPO="$(cygpath -w "$REPO")"
SCRIPTS="$WORK/scripts"
EXCHANGE="$WORK/Exchange"
CONFIG="$WORK/config"
REPORT="$WORK/report.json"

mkdir -p "$SCRIPTS/addons" "$EXCHANGE" "$CONFIG"
cp -r "$REPO/coatlink" "$SCRIPTS/addons/"
rm -rf "$SCRIPTS/addons/coatlink/__pycache__"

echo "blender : $BLENDER"
echo "scripts : $WIN_WORK\\scripts"
echo "exchange: $WIN_WORK\\Exchange"
echo

failed=0

blender_run() {
    BLENDER_USER_SCRIPTS="$WIN_WORK\\scripts" \
    BLENDER_USER_CONFIG="$WIN_WORK\\config" \
        "$BLENDER" --background --factory-startup --python-exit-code 1 "$@"
}

# ---- the main suite: reports pass/fail counts into report.json ----------------
echo "──────────────── tests/test_bridge.py (main suite) ────────────────"
set +e
blender_run --python "$WIN_REPO\\tests\\test_bridge.py" \
    -- --exchange "$WIN_WORK\\Exchange" --report "$WIN_WORK\\report.json"
status=$?
set -e
echo

# ---- every standalone regression script --------------------------------------
for script in test_receipts.py test_retry.py test_delayed_signal.py \
              test_obj_groups.py test_object_names.py test_target_identity.py \
              test_pull_history.py; do
    echo "──────────────── tests/$script ────────────────"
    set +e
    blender_run --python "$WIN_REPO\\tests\\$script"
    code=$?
    set -e
    [ "$code" -eq 0 ] || failed=1
    echo
done

if [ ! -f "$REPORT" ]; then
    echo "report: MISSING - the main suite did not run to completion"
    exit 1
fi
echo "report: $WIN_WORK\\report.json"
echo "main suite exit status: $status"
[ "$status" -eq 0 ] || failed=1

# ---- the installers ---------------------------------------------------------
echo "──────────────── tests/test_install.sh (installers) ────────────────"
set +e
bash "$REPO/tests/test_install.sh"
code=$?
set -e
[ "$code" -eq 0 ] || failed=1
echo

echo "──────────────── tests/test_install_ps1.sh (Windows installer) ────────────────"
set +e
bash "$REPO/tests/test_install_ps1.sh"
code=$?
set -e
[ "$code" -eq 0 ] || failed=1
echo

if [ "$failed" -eq 0 ]; then
    echo "ALL BLENDER SIDE TESTS PASSED"
else
    echo "SOME BLENDER SIDE TESTS FAILED" >&2
fi
exit "$failed"
