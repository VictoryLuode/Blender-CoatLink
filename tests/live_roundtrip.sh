#!/usr/bin/env bash
# Live round trip against the real, running 3D-Coat.
#
#   tests/live_roundtrip.sh [timeout-seconds] [path/to/blender.exe]
#
# Uses the REAL user script folder (the add-on is installed there) and the REAL
# exchange folder, and never writes user preferences.

set -euo pipefail

TIMEOUT="${1:-900}"
BLENDER="${2:-/d/home/Documents/Blender/BlenderBuilds/stable/blender-5.2.0-lts.fbe6228777e7/blender.exe}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WIN_REPO="$(cygpath -w "$REPO")"
WORK="$(mktemp -d "$HOME/AppData/Local/Temp/coat_bridge_live.XXXXXX")"
WIN_WORK="$(cygpath -w "$WORK")"
EXCHANGE="%USERPROFILE%\\Documents\\AppLinks\\3D-Coat\\Exchange"

echo "blender : $BLENDER"
echo "exchange: $EXCHANGE"
echo "timeout : ${TIMEOUT}s"
echo

"$BLENDER" --background --factory-startup --python "$WIN_REPO\\tests\\live_roundtrip.py" -- \
    --exchange "$EXCHANGE" --timeout "$TIMEOUT" --report "$WIN_WORK\\report.json"

echo
echo "report: $WIN_WORK\\report.json"
