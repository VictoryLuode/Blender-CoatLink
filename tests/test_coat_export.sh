#!/usr/bin/env bash
# Verify the return leg with a model that 3D-Coat really exported.
#
#   tests/test_coat_export.sh <model-file> [path/to/blender.exe]
#
# Copies the file into a throwaway exchange root and pulls it through the bridge.
# Nothing outside the temp folder is touched.

set -euo pipefail

MODEL="${1:?usage: test_coat_export.sh <model-file> [blender.exe]}"
BLENDER="${2:-$(ls -d /d/home/Documents/Blender/BlenderBuilds/stable/*/blender.exe 2>/dev/null | sort -V | tail -1)}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WIN_REPO="$(cygpath -w "$REPO")"
WORK="$(mktemp -d "$HOME/AppData/Local/Temp/coat_export_test.XXXXXX")"
WIN_WORK="$(cygpath -w "$WORK")"
SCRIPTS="$WORK/scripts"
mkdir -p "$SCRIPTS/addons"
cp -r "$REPO/coat_bridge" "$SCRIPTS/addons/"
find "$SCRIPTS/addons" -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true

echo "model   : $MODEL"
echo "exchange: $WIN_WORK\\Exchange"
echo

set +e
BLENDER_USER_SCRIPTS="$(cygpath -w "$SCRIPTS")" "$BLENDER" --background --factory-startup \
    --python "$WIN_REPO\\tests\\test_coat_export.py" -- \
    --model "$MODEL" --exchange "$WIN_WORK\\Exchange" --report "$WIN_WORK\\report.json"
status=$?
set -e
echo "exit status: $status"
exit "$status"
