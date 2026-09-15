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

if [ ! -d "$TARGET" ]; then
    echo "no such scripts folder: $TARGET" >&2
    exit 1
fi

DIR="$TARGET/CoatBridge"
mkdir -p "$DIR"
cp "$REPO/coat_side/CoatBridge.py" "$DIR/"
rm -rf "$DIR/__pycache__"

MENU_DIR="$TARGET/ExtraMenuItems"
mkdir -p "$MENU_DIR"
WIN_PATH="$(cygpath -m "$DIR/CoatBridge.py")"

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

echo "script : $DIR/CoatBridge.py"
echo "menu   : $MENU_DIR/CoatBridge.xml  (Scripts > Coat Bridge)"
echo
echo "In 3D-Coat: run Scripts > Coat Bridge (or restart 3D-Coat so the menu picks it up)."
