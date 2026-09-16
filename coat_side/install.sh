#!/usr/bin/env bash
# Install the 3D-Coat side of CoatLink into 3D-Coat's user script folder.
#
#   coat_side/install.sh [scripts-dir] [3dcoat-install-dir]
#
# What lands where:
#   <scripts>/CoatBridge/CoatBridgeLib.py       the exchange logic + actions
#   <scripts>/CoatBridge/CoatBridge_Send.py     tool button: send to Blender
#   <scripts>/CoatBridge/CoatBridge_Pull.py     tool button: pull from Blender
#   <scripts>/CoatBridge/CoatBridge_Setup.py    tool button + Scripts-menu entry (opens the panel)
#   <scripts>/ExtraMenuItems/CoatBridgeTools.xml   the tool buttons (per room)
#   <scripts>/ExtraMenuItems/CoatBridge.xml        the Scripts menu entry
#   <3dcoat>/data/Textures/icons64/CoatBridge*.png the button icons
#
# The tool buttons are plain scripts that act directly and report with 3D-Coat's
# own floating message: no window, no dialog, nothing outside the program.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=tests/find_tools.sh
source "$REPO/tests/find_tools.sh"
TARGET="${1:-$(find_coat_scripts)}"
COAT="${2:-$(find_coat_dir || true)}"

if [ ! -d "$TARGET" ]; then
    echo "no such scripts folder: $TARGET" >&2
    exit 1
fi

DIR="$TARGET/CoatBridge"
mkdir -p "$DIR"
rm -f "$DIR/CoatBridge.py" "$DIR/CoatBridgeQt.py" "$DIR/CoatBridgeDialog.py"   # earlier layouts
cp "$REPO/coat_side/CoatBridgeLib.py" \
   "$REPO/coat_side/CoatBridgeReceipts.py" \
   "$REPO/coat_side/CoatBridgeScopedExport.py" \
   "$REPO/coat_side/CoatBridge_Send.py" \
   "$REPO/coat_side/CoatBridge_Pull.py" \
   "$REPO/coat_side/CoatBridge_Setup.py" \
   "$DIR/"
rm -rf "$DIR/__pycache__"

MENU_DIR="$TARGET/ExtraMenuItems"
mkdir -p "$MENU_DIR"
WIN_DIR="$(cygpath -m "$DIR")"

sed "s#__SCRIPT_DIR__#$WIN_DIR#g" \
    "$REPO/coat_side/tools/CoatBridgeTools.xml.in" > "$MENU_DIR/CoatBridgeTools.xml"

cat > "$MENU_DIR/CoatBridge.xml" <<XML
<ClassArray.ExtraMenuItem>
	<ExtraMenuItem>
		<MenuPath>Scripts</MenuPath>
		<MenuItem>CoatBridge</MenuItem>
		<inRoom></inRoom>
		<inSection></inSection>
		<Command>script:$WIN_DIR/CoatBridge_Setup.py</Command>
	</ExtraMenuItem>
</ClassArray.ExtraMenuItem>
XML

ICON_DIR="$COAT/data/Textures/icons64"
if [ -d "$ICON_DIR" ]; then
    for name in CoatBridge.png CoatBridge_Send.png CoatBridge_Pull.png CoatBridge_Setup.png; do
        cp "$REPO/coat_side/icon/$name" "$ICON_DIR/$name" 2>/dev/null \
            || echo "icon not writable, skipped: $name" >&2
    done
    echo "icons  : $ICON_DIR/CoatBridge_*.png"
else
    echo "icons  : skipped, $ICON_DIR not found" >&2
fi

echo "scripts: $DIR"
echo "buttons: $MENU_DIR/CoatBridgeTools.xml  (Voxels + Paint tool panels)"
echo "menu   : $MENU_DIR/CoatBridge.xml  (Scripts > CoatLink: opens the panel)"
echo
echo "Restart 3D-Coat, then look at the end of the tool list in the Sculpt room."
