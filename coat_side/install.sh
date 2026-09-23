#!/usr/bin/env bash
# Install (or remove) the 3D-Coat side of CoatLink.
#
#   coat_side/install.sh [scripts-dir] [3dcoat-install-dir] [--uninstall] [--quiet]
#
# A thin wrapper on purpose: the work lives in coat_side/CoatLinkInstall.py, which
# this script, install.cmd, install.ps1 and the single file in dist/ all run, so
# the four of them cannot drift apart.
#
# What lands where:
#   <scripts>/CoatLink/*.py                     the bridge itself
#   <scripts>/ExtraMenuItems/CoatLink.xml       Scripts > CoatLink entry
#   <scripts>/ExtraMenuItems/CoatLinkTools.xml  the three tool buttons
#   <3dcoat>/data/Textures/icons64/*.png          button icons, when writable
#
# Everything else in those folders is left alone, and the two menu XMLs are
# generated with this machine's paths - 3D-Coat needs absolute script paths.

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

# the installer is a Windows program's Python: it cannot resolve an MSYS path
# like /h/Dev/..., so hand it the mixed form (H:/Dev/...)
INSTALLER="$REPO/coat_side/CoatLinkInstall.py"
if command -v cygpath >/dev/null 2>&1; then
    INSTALLER="$(cygpath -m "$INSTALLER")"
fi
exec "$PYTHON" "$INSTALLER" "${ARGS[@]}" "${@:3}"
