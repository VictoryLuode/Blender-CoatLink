# Changelog

## v1.4.0 - 2026-09-13

Where the 3D-Coat launcher can live, after checking every option the host offers.

* Research result, with evidence: 3D-Coat's right-hand dock column (VoxTree,
  Layers, Multires, ...) is a closed set.  `Layout.xml` names those windows and
  the Python API has no way to register another one - `ui.enableWindow()` only
  toggles built-ins, and the Qt window manager only undocks built-ins.  The
  embeddable spots are the room tool panels, the menus, the RMB panel, and
  custom rooms.
* `insertInToolset(room, "", "CoatBridge")` puts a button at the end of a room's
  tool list, with the icon `data/Textures/icons64/CoatBridge.png` (grey glyph,
  same style as the shipped tool icons) and the label from `addTranslation`.
  `TOOL_ROOMS` starts with `Voxels` so the result can be judged before adding
  more rooms.
* The panel gained `RemoveLauncher`: it calls `removeCommandFromMenu` and clears
  the record, so the injected menu entries and tool button can always be removed
  again.
* `install.sh` installs the icon too and reports when the folder is not writable.
* 3D-Coat side tests: 51 checks (`check_coat_api.py` still proves every call
  exists in the shipped stubs).  Blender side unchanged at 65 checks.

## v1.3.0 - 2026-09-13