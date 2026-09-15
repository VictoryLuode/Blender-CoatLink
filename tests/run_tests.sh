#!/usr/bin/env bash
# Headless end-to-end test for Coat Bridge.
#
#   tests/run_tests.sh [path/to/blender.exe]
#
# Blender gets a throwaway script folder, so the add-on is enabled and driven
# without touching the real user configuration or the real 3D-Coat folder.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BLENDER="${1:-$(ls -d /d/home/Documents/Blender/BlenderBuilds/stable/*/blender.exe 2>/dev/null | sort -V | tail -1)}"
WORK="$(mktemp -d "$HOME/AppData/Local/Temp/coat_bridge_test.XXXXXX")"
WIN_WORK="$(cygpath -w "$WORK")"
WIN_REPO="$(cygpath -w "$REPO")"
SCRIPTS="$WORK/scripts"
EXCHANGE="$WORK/Exchange"
REPORT="$WORK/report.json"

mkdir -p "$SCRIPTS/addons" "$EXCHANGE"
cp -r "$REPO/coat_bridge" "$SCRIPTS/addons/"
rm -rf "$SCRIPTS/addons/coat_bridge/__pycache__"

echo "blender : $BLENDER"
echo "scripts : $WIN_WORK\\scripts"
echo "exchange: $WIN_WORK\\Exchange"
echo

set +e
BLENDER_USER_SCRIPTS="$WIN_WORK\\scripts" "$BLENDER" --background --factory-startup \
    --python "$WIN_REPO\\tests\\test_bridge.py" -- --exchange "$WIN_WORK\\Exchange" --report "$WIN_WORK\\report.json"
status=$?
set -e

echo
if [ ! -f "$REPORT" ]; then
    echo "report: MISSING - the suite did not run to completion"
    exit 1
fi
echo "report: $WIN_WORK\\report.json"
echo "exit status: $status"
exit "$status"
