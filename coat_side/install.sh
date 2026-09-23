#!/usr/bin/env bash
# Install (or remove) the 3D-Coat side of CoatLink.
#
#   coat_side/install.sh [scripts-dir] [3dcoat-install-dir] [--uninstall] [--quiet]
#
# A thin wrapper on purpose: the work lives in coat_side/CoatLinkInstall.py, which
# this script, install.cmd and install.ps1 all run, so the three of them cannot
# drift apart.
#
# What lands where (the same files, and in the same place, as a .3dcpack puts them):
#   <scripts>/cExtensions/CoatLink/*.py          the bridge itself
#   <scripts>/cExtensions/startup.txt            our name, added once (backed up)
#
# The two ExtraMenuItems XML files are not installed: they hold absolute paths, so
# the extension writes them itself the first time 3D-Coat starts it, and it moves an
# older install (a hand install straight in Scripts, or the pre-rename folders) out
# of the way at the same time.  Nothing is written outside 3D-Coat's user folder -
# the tool buttons take 3D-Coat's default icon.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=tests/find_tools.sh
source "$REPO/tests/find_tools.sh"

SCRIPTS="${1:-$(find_coat_scripts)}"
COAT="${2:-$(find_coat_dir || true)}"

PYTHON="$(find_coat_python || true)"          # 3D-Coat ships its own Python
if [ -z "$PYTHON" ]; then
    PYTHON="$(command -v python3 || command -v python || true)"
fi
if [ -z "$PYTHON" ]; then
    echo "no Python found: start 3D-Coat once (it ships one) or install Python" >&2
    exit 1
fi

ARGS=( --scripts "$SCRIPTS" )
[ -n "$COAT" ] && ARGS+=( --coat "$COAT" )
# anything past the two paths is passed straight through (--uninstall, --quiet)

# the installer is a Windows program's Python: it cannot resolve an MSYS-style
# path, so hand it the mixed form (drive letter, forward slashes)
INSTALLER="$REPO/coat_side/CoatLinkInstall.py"
if command -v cygpath >/dev/null 2>&1; then
    INSTALLER="$(cygpath -m "$INSTALLER")"
fi
exec "$PYTHON" "$INSTALLER" "${ARGS[@]}" "${@:3}"
