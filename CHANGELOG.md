# Changelog

## v1.11.0 - 2026-09-13

The export settings live in 3D-Coat, where the export happens.

* The "3D-Coat export" block added in v1.10.0 is **gone from Blender** - the
  job file is back to three lines plus the skip flags.  Export settings belong
  on the side that exports.
* 3D-Coat side, same idea as the bridge always had: the first export reads the
  percentage out of 3D-Coat's own dialog and remembers it
  (`CoatBridge.json`), and every export after that pushes it into 3D-Coat's own
  decimation slider (`CMD.SetSliderValue("$DecimationParams::ReductionPercent")`,
  the id `Scripts/mm_export.as` and `CoreAPI/Templates/CoreAPI_Export/
  auto_export.cpp` both use) and presses OK, so the dialog is never seen again.
* Same mechanism for textures: `Textures: 3D-Coat decides / on / off` cycles in
  the panel and drives `CMD.SetBoolField("$ExportOpt::ExportTextures")`.
* The panel itself is 3D-Coat's own dialog (`coat.dialog()...topRight()`), opened
  by the tool-strip button.  **No Qt, no extra window** - the parked
  `CoatBridgeQt.py` is not installed and nothing imports it.
* Blender addon 1.7.0.  Suites: Blender 77 checks; 3D-Coat 81 + 29 tool + 24 Qt
  (parked module, kept honest).

## v1.10.0 - 2026-09-13

3D-Coat's export dialog, moved into the settings.

* New "3D-Coat export" block in the Blender menu.  The values are written into
  the job file (import.txt) with 3D-Coat's documented syntax, so its export runs
  without stopping at a dialog:
  `[ExportResolution=LOW-POLY|MID-POLY]`, `[CoarseMesh=0|1]`,
  `[ExportTextures=0|1]`, and `[field $ExportOpt::DesiredPolycount = N]`
  (the export dialog's own polycount field, written first because a `[field ...]`
  command replaces earlier option commands).
* Defaults stay neutral: no resolution, no polycount, textures on, coarse off -
  the two always-written lines then simply restate 3D-Coat's current behaviour.
* Nothing is set twice: the 3D-Coat side only consumes the job file, so the
  Blender menu is the single place these live, and they apply to the model
  coming back in both directions.
* Blender addon 1.6.0.  Suite: 86 checks (the job file carries the settings in
  the right order, the dialog stays skipped, the status line and the shared log
  report what was asked for).

## v1.9.0 - 2026-09-13

`Import without materials`.

* New toggle in the Blender menu (`No materials`, off by default): a pulled model
  comes back as bare geometry.  The mesh's own slots are dropped, and the material
  datablocks the returned file brought are removed too - but only when nothing
  else uses them, so the user's own materials are never touched.
* Ordering matters and is handled explicitly: the file's materials are collected
  and cleared before the mesh swap, and the datablocks are only collected after
  the temporary imported object is gone (otherwise it still references them).
* Blender addon 1.5.0.  Tests: 77 checks - the returned mesh has zero material
  slots, the file's material is gone, the user's own material survives, and the
  status line says `no materials`.

## v1.8.0 - 2026-09-13

One format instead of a menu of them.

* Sending is always OBJ: it carries geometry, UVs and materials without unit
  ambiguity.  STL and PLY cannot carry UVs or materials, so they were useless for
  this workflow, and FBX is what 3D-Coat hands back anyway.
* What 3D-Coat returns is read by its file extension, so there is nothing to
  configure on the way back either (the scale match covers the FBX unit factor).
* The `Format` row is gone from the Blender menu and from the 3D-Coat panel, and
  the 3D-Coat `format` setting is no longer stored.
* Blender addon 1.4.0.  Tests: Blender 74 checks (incl. an FBX return imported
  with no format setting), 3D-Coat 52 + 29 + 24.

## v1.7.0 - 2026-09-13

Scale and units: a returned model now comes back at the size it left.

* Cause: 3D-Coat exports with its own scene scale - `Scene.GetSceneScale()` is
  documented as "the length of 1 scene unit when you export the scene" - so a
  round trip can come home at a fixed multiple (x100 with FBX is the classic).
* Blender side: `send` records the model's world-space bounding-box diagonal and
  each pulled model is measured against it.  A difference bigger than 2% is scaled
  away (about the world origin, geometry only) and reported in the status as
  `scale x0.01`; the new `Match scale` toggle (on by default) can switch it off.
  Sane-guarded: factors beyond x1000 are reported but left alone.
* Both sides write the numbers to one shared log,
  `Documents/3DCoat/CoatBridge.log`: the Blender side logs the sent size and the
  correction, the 3D-Coat side logs its own `units=... scale=...` on every action,
  so a future mismatch can be read off instead of guessed.
* Tests: Blender suite 73 checks (a return that is 1.6x too big is asserted to be
  rescaled back to exactly the sent size; a same-size return is left alone; the
  toggle is exercised), 3D-Coat suite 52 + 29 + 26.

## v1.6.0 - 2026-09-13

No window at all: the bridge is now three buttons in 3D-Coat's own tool panel.

* `CoatBridge_Send.py`, `CoatBridge_Pull.py`, `CoatBridge_Setup.py`: plain scripts
  that act directly (export, import, find the folder) and report with 3D-Coat's
  own floating message.  Nothing opens: no dialog, no window, no second process.
* `tools/CoatBridgeTools.xml.in` -> `ExtraMenuItems/CoatBridgeTools.xml`: an entry
  with an empty `MenuPath` plus `inRoom`/`inSection` lands in that room's tool
  panel, so the buttons are declared by file (they survive a restart) instead of
  being injected by a run-once API call.  Voxels and Paint for now.
* Icons: `CoatBridge_Send.png` (arrow leaving a wall), `CoatBridge_Pull.png`
  (arrow arriving), `CoatBridge_Setup.png` (magnifier) in `data/Textures/icons64/`,
  grey glyphs like the shipped tool icons.
* The in-process Qt window is no longer installed (code and its 26 tests stay in
  the repo as an optional reference).  The `Scripts > Coat Bridge` entry now
  opens 3D-Coat's own native dialog, which is optional.
* Labels: 3D-Coat shows the raw id until a translation exists, so every button
  calls `addTranslation` when it runs; if the labels still read as ids, switch to
  `insertInToolset`, which labels them at injection time.
* Tests: `coat_side/tests/run_tests.sh` now also runs the tool-button suite
  (23 checks) - it runs each button headless, verifies the message, the signal
  file, the queue handling and the log, and validates the XML (ids, rooms,
  script paths).

## v1.5.0 - 2026-09-13

The 3D-Coat panel is now a Qt window inside 3D-Coat's process.

* `coat_side/CoatBridgeQt.py`: a PySide6 `QMainWindow` built the way 3D-Coat's own
  Python panels (Python Terminal, Data Tree, AI Assistant) are built.  No
  cExtension and no event loop of our own are needed: 3D-Coat's shipped `QT`
  extension already calls `app.processEvents()` every frame
  (`cModules/QT/QT.py`), so a plain script can own a live window, in the same
  process, with direct access to the `coat` API.
* The window mirrors the Blender menu: `Send to Blender`, `Pull from Blender`,
  `Format [FBX|OBJ]`, `Detect`, `Folder`, `Start Blender`, `Remove launcher`,
  plus a status/detail/hint block.  It remembers its position, starts next to the
  right-hand panel column, refreshes the status twice a second, and a second
  `Scripts > Coat Bridge` just raises the open window.
* `CoatBridge.py` was split into logic + actions and only runs when 3D-Coat runs
  it (`runpy` -> `__name__ == "<run_path>"`), so the Qt panel can import it.
  If Qt is missing, the panel falls back to the native dialog.
* Corrected an earlier claim: the dock/tab row (Layers / FPS-monitor /
  Extensions / Object Inspector) is built into 3D-Coat and cannot be extended by
  third parties - 3D-Coat's own Python panels are windows too, not tabs.
* Tests without 3D-Coat: `coat_side/tests/run_tests.sh` runs the API check, 52
  logic checks and 27 Qt checks - the Qt suite builds the real window offscreen
  on 3D-Coat's own Python and clicks every button.
* Blender side unchanged (65 checks).

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