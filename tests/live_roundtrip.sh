#!/usr/bin/env bash
# Live round trip against the real, running 3D-Coat.
#
#   tests/live_roundtrip.sh [timeout-seconds] [path/to/blender.exe]
#
# Pass --origin through to the Blender script to also exercise "Send to origin":
#   tests/live_roundtrip.sh --origin
#
# Uses the REAL user script folder (the add-on is installed there) and the REAL
# exchange folder, and never writes user preferences.

set -euo pipefail

TIMEOUT=""
BLENDER_ARG=""
ORIGIN=""
for arg in "$@"; do
    case "$arg" in
        --origin) ORIGIN="--origin" ;;
        *)  if [ -z "$TIMEOUT" ]; then TIMEOUT="$arg"
            elif [ -z "$BLENDER_ARG" ]; then BLENDER_ARG="$arg"
            fi ;;
    esac
done
TIMEOUT="${TIMEOUT:-900}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=tests/find_tools.sh
source "$REPO/tests/find_tools.sh"
BLENDER="${BLENDER_ARG:-$(find_blender || true)}"
if [ -z "$BLENDER" ]; then
    echo "no Blender found - pass one: live_roundtrip.sh <timeout> /path/to/blender.exe" >&2
    exit 2
fi
WIN_REPO="$(cygpath -w "$REPO")"
WORK="$(mktemp -d "${LOCALAPPDATA:-/tmp}/coatlink_live.XXXXXX")"
WIN_WORK="$(cygpath -w "$WORK")"
EXCHANGE="$(cygpath -w "$HOME/Documents/AppLinks/3D-Coat/Exchange")"

echo "blender : $BLENDER"
echo "exchange: $EXCHANGE"
echo "timeout : ${TIMEOUT}s"
echo "origin  : ${ORIGIN:-off}"
echo

# Fail fast: 3D-Coat has to be running and in front, or the job just sits there.
if ! tasklist 2>/dev/null | grep -qi "3dcoatgl64.exe"; then
    echo "3D-Coat is not running - start it, then run this again" >&2
    exit 2
fi

"$BLENDER" --background --factory-startup --python "$WIN_REPO\\tests\\live_roundtrip.py" -- \
    --exchange "$EXCHANGE" --timeout "$TIMEOUT" --report "$WIN_WORK\\report.json" $ORIGIN

echo
echo "report: $WIN_WORK\\report.json"
