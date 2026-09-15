#!/usr/bin/env bash
# Install the 3D-Coat side of Coat Bridge into 3D-Coat's user script folder.
#
#   coat_side/install.sh [scripts-dir]
#
# Default target: Documents/3DCoat/UserPrefs/Scripts (where 3D-Coat 2026 keeps
# user scripts).  Copies CoatBridge.py and writes the menu entry XML that makes
# it appear in the Scripts menu; nothing else is touched.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="${1:-$HOME/Documents/3DCoat/UserPrefs/Scripts}"
COAT="${2:-/d/Program Files/3DCoat-2026}"

if [ ! -d "$TARGET" ]; then
    echo "no such scripts folder: $TARGET" >&2
    exit 1
fi

DIR="$TARGET/CoatBridge"
mkdir -p "$DIR"
rm -f "$DIR/CoatBridge.py"  # renamed to CoatBridgeLib.py
cp "$REPO/coat_side/CoatBridgeLib.py" "$REPO/coat_side/CoatBridgeQt.py" "$REPO/coat_side/CoatBridgeDialog.py" "$DIR/"
rm -rf "$DIR/__pycache__"

MENU_DIR="$TARGET/ExtraMenuItems"
mkdir -p "$MENU_DIR"
WIN_PATH="$(cygpath -m "$DIR/CoatBridgeQt.py")"

cat > "$MENU_DIR/CoatBridge.xml" <<XML
<ClassArray.ExtraMenuItem>
	<ExtraMenuItem>
		<MenuPath>Scripts</MenuPath>
		<MenuItem>CoatBridge</MenuItem>
		<inRoom></inRoom>
		<inSection></inSection>
		<Command>script:$WIN_PATH</Command>
	</ExtraMenuItem>
</ClassArray.ExtraMenuItem>
XML

echo "script : $DIR/CoatBridgeQt.py  (Qt panel; CoatBridgeLib.py = logic, CoatBridgeDialog.py = native fallback)"
echo "menu   : $MENU_DIR/CoatBridge.xml  (Scripts > Coat Bridge)"

ICON_DIR="$COAT/data/Textures/icons64"
if [ -d "$ICON_DIR" ]; then
    if cp "$REPO/coat_side/icon/CoatBridge.png" "$ICON_DIR/CoatBridge.png" 2>/dev/null; then
        echo "icon   : $ICON_DIR/CoatBridge.png"
    else
        echo "icon   : skipped, $ICON_DIR is not writable (the tool button shows text only)" >&2
    fi
else
    echo "icon   : skipped, $ICON_DIR not found" >&2
fi

echo
echo "In 3D-Coat: run Scripts > Coat Bridge (or restart 3D-Coat so the menu picks it up)."
