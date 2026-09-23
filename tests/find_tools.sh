#!/usr/bin/env bash
# Locate the tools this project drives.  Sourced by the scripts, not run.
#
#   source tests/find_tools.sh
#   BLENDER="$(find_blender)"
#
# Every function honours its explicit override first (BLENDER, BLENDER_ADDON_DIR,
# COAT_PYTHON, COAT_DIR, COAT_SCRIPTS_DIR), then searches the usual locations and
# returns the newest match.  Nothing here assumes a user name or a drive letter.
#
# Globs go through nullglob arrays on purpose: `compgen -G` returns only the
# first match under MSYS, which silently picks the wrong build.

# the filesystem a path lives on: ntfs for a local disk, smbfs for a mapped share
fs_type_of() {
    local drive
    drive="$(df -P "$1" 2>/dev/null | tail -1 | awk '{print $1}')"
    case "$drive" in
        [A-Za-z]:) mount 2>/dev/null | awk -v d="$drive" '$1 == d { print $5; exit }' ;;
        *) printf '%s\n' "" ;;
    esac
}

# newest Blender executable
find_blender() {
    if [ -n "${BLENDER:-}" ] && [ -f "$BLENDER" ]; then
        printf '%s\n' "$BLENDER"
        return 0
    fi
    local had_nullglob=0
    if shopt -q nullglob; then had_nullglob=1; fi
    shopt -s nullglob

    local -a all=()
    local drive

    # a normal installer
    all+=( "$HOME"/AppData/Local/Programs/Blender*/*/blender.exe )
    all+=( "/c/Program Files/Blender Foundation"/Blender*/*/blender.exe )
    all+=( "/d/Program Files/Blender Foundation"/Blender*/*/blender.exe )

    # Blender Launcher keeps its build library under Scoop's persist folder
    for drive in /c /d /e /f /g /h; do
        [ -d "$drive" ] || continue
        all+=( $drive/Scoop/persist/blender-launcher/BlenderBuilds/*/*/blender.exe )
        all+=( $drive/Scoop/apps/blender-launcher/current/BlenderBuilds/*/*/blender.exe )
    done

    # a build folder of its own, wherever the documents tree currently lives:
    # that tree gets reorganised from time to time, so walk the drives instead of
    # assuming one layout
    all+=( "$HOME"/BlenderBuilds/*/*/blender.exe )
    all+=( "$HOME"/Documents/Blender/BlenderBuilds/*/*/blender.exe )
    for drive in /c /d /e /f /g /h; do
        [ -d "$drive" ] || continue
        all+=( $drive/home/Documents/Blender/BlenderBuilds/*/*/blender.exe )
        all+=( $drive/Documents/Blender/BlenderBuilds/*/*/blender.exe )
    done

    if [ "$had_nullglob" -eq 0 ]; then shopt -u nullglob; fi
    if [ ${#all[@]} -eq 0 ]; then return 1; fi

    # A build on a mapped network drive cannot be started here at all - Windows
    # fails with "side-by-side configuration is incorrect" - so when both kinds
    # are present, the local ones win.
    local -a local=()
    local candidate
    for candidate in "${all[@]}"; do
        case "$(fs_type_of "$candidate")" in
            smbfs|nfs|cifs|net) continue ;;
        esac
        local+=( "$candidate" )
    done
    if [ ${#local[@]} -gt 0 ]; then
        all=( "${local[@]}" )
    fi

    printf '%s\n' "${all[@]}" | sort -V | tail -1
}

# newest Blender user "scripts/addons" folder - where an add-on gets installed
find_blender_addons() {
    if [ -n "${BLENDER_ADDON_DIR:-}" ]; then
        printf '%s\n' "$BLENDER_ADDON_DIR"
        return 0
    fi
    local had_nullglob=0
    if shopt -q nullglob; then had_nullglob=1; fi
    shopt -s nullglob
    local root="${BLENDER_CONFIG_DIR:-$HOME/AppData/Roaming/Blender Foundation/Blender}"
    local -a group=( "$root"/*/scripts/addons )
    if [ "$had_nullglob" -eq 0 ]; then shopt -u nullglob; fi
    if [ ${#group[@]} -eq 0 ]; then return 1; fi
    printf '%s\n' "${group[@]}" | sort -V | tail -1
}

# 3D-Coat's own bundled Python, which the 3D-Coat side tests run on
find_coat_python() {
    if [ -n "${COAT_PYTHON:-}" ] && [ -f "$COAT_PYTHON" ]; then
        printf '%s\n' "$COAT_PYTHON"
        return 0
    fi
    local had_nullglob=0
    if shopt -q nullglob; then had_nullglob=1; fi
    shopt -s nullglob
    local -a group=( "$HOME"/Documents/3DCoat/python-*/python.exe )
    if [ "$had_nullglob" -eq 0 ]; then shopt -u nullglob; fi
    if [ ${#group[@]} -eq 0 ]; then return 1; fi
    printf '%s\n' "${group[@]}" | sort -V | tail -1
}

# the 3D-Coat program folder (only used to drop the button icons beside its own)
find_coat_dir() {
    if [ -n "${COAT_DIR:-}" ] && [ -d "$COAT_DIR" ]; then
        printf '%s\n' "$COAT_DIR"
        return 0
    fi
    local had_nullglob=0
    if shopt -q nullglob; then had_nullglob=1; fi
    shopt -s nullglob
    local -a group=( "/c/Program Files"/3DCoat* )
    if [ ${#group[@]} -eq 0 ]; then group=( "/d/Program Files"/3DCoat* ); fi
    if [ ${#group[@]} -eq 0 ]; then group=( "/e/Program Files"/3DCoat* ); fi
    if [ ${#group[@]} -eq 0 ]; then group=( "/c/Program Files (x86)"/3DCoat* ); fi
    if [ ${#group[@]} -eq 0 ]; then group=( "$HOME"/AppData/Local/Programs/3DCoat* ); fi
    if [ ${#group[@]} -eq 0 ]; then group=( "$HOME"/AppData/Local/3DCoat* ); fi
    if [ "$had_nullglob" -eq 0 ]; then shopt -u nullglob; fi
    if [ ${#group[@]} -eq 0 ]; then return 1; fi
    printf '%s\n' "${group[@]}" | sort -V | tail -1
}

# 3D-Coat's script folder (where the 3D-Coat side of the bridge is installed)
find_coat_scripts() {
    if [ -n "${COAT_SCRIPTS_DIR:-}" ]; then
        printf '%s\n' "$COAT_SCRIPTS_DIR"
        return 0
    fi
    printf '%s\n' "$HOME/Documents/3DCoat/UserPrefs/Scripts"
}
