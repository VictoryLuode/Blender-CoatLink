#!/usr/bin/env bash
# Install CoatLink: the Blender add-on, the 3D-Coat scripts, or both.
#
#   ./install.sh                          detect both and install
#   ./install.sh --blender-only           just the add-on
#   ./install.sh --coat-only              just the 3D-Coat half
#
# Optional explicit locations, in this order:
#
#   ./install.sh [blender-addons-dir] [3dc-scripts-dir] [3dc-program-dir]
#
#     blender-addons-dir  ...\Blender\<version>\scripts\addons
#     3dc-scripts-dir     ...\Documents\3DCoat\UserPrefs\Scripts
#     3dc-program-dir     the 3D-Coat program folder (only for the button icons)
#
# Each one can also come from the environment: BLENDER_ADDON_DIR,
# COAT_SCRIPTS_DIR, COAT_DIR.
#
# The Blender half is a plain copy - nothing else to do.  The 3D-Coat half is
# installed by coat_side/install.sh, which also writes the menu entry and the
# tool-button XML, and is safe to run twice.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tests/find_tools.sh
source "$REPO/tests/find_tools.sh"

mode=both
args=()
for arg in "$@"; do
    case "$arg" in
        --blender-only) mode=blender ;;
        --coat-only)    mode=coat ;;
        *)              args+=("$arg") ;;
    esac
done

addons="${args[0]:-${BLENDER_ADDON_DIR:-}}"
coat_scripts="${args[1]:-${COAT_SCRIPTS_DIR:-}}"
coat_dir="${args[2]:-${COAT_DIR:-}}"

# ---- Blender side ----------------------------------------------------------
if [ "$mode" != "coat" ]; then
    if [ -z "$addons" ]; then
        addons="$(find_blender_addons || true)"
    fi
    if [ -z "$addons" ]; then
        echo "Blender add-on folder not found.  Pass it as the first argument:" >&2
        echo "  ./install.sh \"\$APPDATA/Blender Foundation/Blender/<version>/scripts/addons\"" >&2
        exit 1
    fi
    mkdir -p "$addons"
    # An earlier build installed itself as `coat_bridge`.  Leaving that folder in the
    # add-ons search path would show two CoatLinks in Blender's list, so it is moved one
    # level out (out of Blender's reach, still on disk) - never deleted.
    if [ -d "$addons/coat_bridge" ]; then
        legacy="$(dirname "$addons")/coat_bridge.removed-$(date +%Y%m%d-%H%M%S)"
        mv "$addons/coat_bridge" "$legacy"
        echo "add-on : moved the older coat_bridge build aside -> $legacy"
    fi
    rm -rf "$addons/coatlink"
    cp -r "$REPO/coatlink" "$addons/coatlink"
    find "$addons/coatlink" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
    echo "add-on : $addons/coatlink"
    echo "         enable it in Edit > Preferences > Add-ons, then press Detect"
fi

# ---- 3D-Coat side ----------------------------------------------------------
if [ "$mode" != "blender" ]; then
    if [ -z "$coat_scripts" ]; then
        coat_scripts="$(find_coat_scripts)"
    fi
    if [ -z "$coat_dir" ]; then
        coat_dir="$(find_coat_dir || true)"
    fi
    if [ -n "$coat_dir" ]; then
        bash "$REPO/coat_side/install.sh" "$coat_scripts" "$coat_dir"
    else
        bash "$REPO/coat_side/install.sh" "$coat_scripts"
    fi
    echo "         restart 3D-Coat, then look for Scripts > CoatLink"
fi
