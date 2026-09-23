#!/usr/bin/env bash
# Verify the return leg with a model that 3D-Coat really exported.
#
#   tests/test_coat_export.sh <model-file> [path/to/blender.exe]
#
# Copies the file into a throwaway exchange root and pulls it through the bridge.
# Nothing outside the temp folder is touched.

set -euo pipefail

MODEL="${1:?usage: test_coat_export.sh <model-file> [blender.exe]}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=tests/find_tools.sh
source "$REPO/tests/find_tools.sh"
BLENDER="${2:-$(find_blender || true)}"
if [ -z "$BLENDER" ]; then
    echo "no Blender found - pass one: test_coat_export.sh <model> /path/to/blender.exe" >&2
    exit 2
fi
WIN_REPO="$(cygpath -w "$REPO")"
WORK="$(mktemp -d "${LOCALAPPDATA:-/tmp}/coat_export_test.XXXXXX")"
WIN_WORK="$(cygpath -w "$WORK")"
SCRIPTS="$WORK/scripts"
mkdir -p "$SCRIPTS/addons"
cp -r "$REPO/coatlink" "$SCRIPTS/addons/"
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
