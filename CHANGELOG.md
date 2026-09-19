# Changelog

## v1.16.22

Two behaviour changes the user asked for.  Everything else is unchanged.

* **3D-Coat sends the node selected in the sculpt tree**, plus its children, instead
  of the whole scene.  The panel gained one droplist for it (`selected node` /
  `whole scene`), defaulting to the selection.  The extraction goes through
  3D-Coat's own `Scene.current()` + `Mesh().fromVolume(volume, with_subtree=True,
  all_selected=False)`, and a reduction percentage is applied with
  `fromReducedVolume` - the parameter is named `reduction_percent` there, which is
  also the wording the panel uses.  There is deliberately **no fallback to the
  whole-scene export**: with nothing selected the button says so and sends nothing,
  and a result that loses its object groups is refused rather than merged.
  The whole-scene route (3D-Coat's own export dialog, textures included) is still
  there - as an explicit choice, not as a silent default.
* **Blender opens models in 3D-Coat as a voxel sculpt object by default** (`Import
  as` now starts on `Sculpt Object (voxel)` and that entry is listed first).

Also fixed: `check_coat_api.py` looked for 3D-Coat's type stubs at a hardcoded
`D:\Program Files\3DCoat-2026`, so the API check quietly stopped checking when
3D-Coat moved to another drive and version folder.  It now searches, newest wins,
with `COAT_API` as an override.

Notes from the live install: with 3D-Coat in `C:\Program Files` the icon folder needs
administrator rights, so the installer skips the four icons and says so - the buttons
and the panel work regardless, and running it as administrator once copies them.

Tests: 3D-Coat logic 106/106 (the send path has its own file, `test_scoped_send.py`,
19 checks - scope, subtree flag, reduction, empty selection, missing geometry and a
merge that loses groups), tools 29/29, installer 32/32, API stub check (now really
running), idle redraw, probe dry run, install smoke.  Blender: see v1.16.19's suite.

## v1.16.21

Installing the 3D-Coat half is now one step instead of three, and the plugin code
itself is unchanged from v1.16.19 (Blender 1.10.17).

* **One installer, four doors.** `coat_side/CoatLinkInstall.py` holds the install
  logic; `install.cmd` (double-click on Windows), `install.sh`, `install.ps1` and
  the single-file `CoatLink-Setup.py` all run it.  The shell and PowerShell
  installers used to carry their own copies of the logic, which is exactly how two
  installers drift apart - now a test installs with each and compares the trees
  byte for byte after normalising the generated paths.
* **Double-click path.** Unzip, double-click `install.cmd`: it finds 3D-Coat's own
  bundled Python, writes the scripts and both menu XMLs with this machine's paths,
  copies the button icons when that folder is writable and says so when it is not.
  No admin rights, no PATH edits, nothing to configure.
* **Single-file path.** `dist/CoatLink-Setup.py` is the same installer with the
  files embedded: download one file and paste one line into 3D-Coat's Python
  console.  `package.sh` builds it, and it is published as its own release asset.
* **Uninstall.** `--uninstall` / `-Uninstall` removes exactly what was installed
  (scripts, the two menu XMLs, the icons) and leaves every other file alone.
* The scoped-export module is no longer installed: nothing calls it.

Tests: 3D-Coat installer **29/29** (new), plus the existing suites unchanged -
Blender 113/113 and its regression scripts, 3D-Coat logic 103/103, tools 29/29,
API stub check, idle-redraw check, probe dry run, both installer smoke tests.

## v1.16.20

Release prep - the bridge code itself is unchanged from v1.16.19 (Blender 1.10.17).

* **Installers for both halves.** `install.ps1` does the whole job on Windows with
  nothing but PowerShell (no bash, no git); `install.sh` is the same for bash,
  MSYS and WSL. Both find Blender's add-on folder, 3D-Coat's script folder and its
  program folder on their own, take explicit paths or `-BlenderOnly` / `-CoatOnly`,
  and can be run twice.
* `tests/test_install_ps1.sh` proves the PowerShell installer and the bash
  installer land byte-identical files, XML included.
* `package.sh` builds the two release archives: `coat_bridge.zip` for Blender's
  *Install from Disk*, and the full source archive.
* GPL-3.0-or-later LICENSE, `.gitattributes` so the repo and every checkout use one
  line ending, and a README rewritten for people who did not write the thing:
  three install routes (easiest first), the actual current UI, and an honest
  "known limitations" section.
* The test scripts now locate the newest Blender build, 3D-Coat's bundled Python,
  the 3D-Coat program folder and the script folders themselves - every hard-coded
  author path is gone (`tests/find_tools.sh`), and the install smoke tests are part
  of the suite.

## v1.16.19

* Persist the pull record in the exchange folder (pull-history.json), so restarting
  Blender no longer reimports the return file that is still sitting there. A model
  whose version changed is imported normally, an explicit pull still overrides the
  record, and a damaged record falls back to importing instead of blocking.
* tests/run_tests.sh now runs every standalone regression script (seven of them were
  never wired into the suite) in its own isolated Blender session.
* Blender 1.10.17. Tests: main suite 113/113 plus receipts, retry, delayed signal,
  OBJ groups, object names, target identity, pull history; 3D-Coat logic 103/103,
  tools 29/29, API stub check, idle redraw, probe dry run, install smoke.

## v1.16.17

* Stabilize installed panel: no scene queries or filesystem reads during idle redraw; control changes persist only when edited. Disable process callback and automatic receipt display on Coat panel pending host issue verification. Manual stats only.
* Block foreign return adoption without prior send; do not mask later pull status with earlier send receipt.
* Pending subtree implementation backed up, not installed.
* Blender 1.10.15; 113 regression checks and 1000 simulated idle cycles passed. Live face-count growth remains unverified.

## v1.16.16

* Persist export aliases on Blender objects; map multi-object returns independently, preserving Blender-side renamed targets and avoiding unrelated same-name objects. New return groups stay separate.
* Single-object legacy return retains last-sent-target fallback. Coat-side renames without retained aliases cannot be reliably mapped.
* Real Blender reversed-order / rename / collision regression passed; existing suite 113/113. Blender add-on 1.10.14.

## v1.16.15

* Receiver-generated file-version receipts after successful Python imports; native AppLink imports bypassing these hooks remain unconfirmed. Hash cache avoids rehashing unchanged models every draw.
* Filter model discovery by extension so receipt sidecars are never imported.
* Correct reduction wording to removed percentage based on official auto_export.cpp. Selected-volume remaining-face estimate explicitly unverified for AppLink export.
* Read-only Coat diagnostic supplied; live Coat verification blocked because application was not running.
* Blender 1.10.13; tests 113/113, Coat simulated 101/101 + 29/29, receipt tests and installation smoke passed.

## v1.16.14

* Compact native panels: advanced/maintenance settings hidden by default; Blender keeps transfer shortcuts on top bar instead of duplicating them.
* Normal Pull respects deduplication; force re-read is advanced-only. Empty receive offers an action; send notification says queued. Successful pull includes object count.
* No receipt handshake or estimated polygon counts claimed; those remain unverified.
* Blender 1.10.12; regression 113/113; Coat logic 101/101, tools 29/29 and install smoke passed.

## v1.16.13

* Remove TargetSize and ApplySize controls from the native 3D-Coat panel; retain read-only size display. No export or unit changes.
* 3D-Coat logic 100/100, tools 29/29, installation smoke test passed. Installed library byte-verified.

## v1.16.12

* Enable OBJ group splitting on return: 3D-Coat exports object boundaries as g records. Distinct groups become separate Blender Objects.
* Real Blender regression: Hull and Turret become two meshes. Existing suite 113/113.
* Blender add-on 1.10.11.

## v1.16.11

* Auto pull deduplicates successful file versions across delayed mirror signals (canonical path, nanosecond mtime and size). Modified exports still import; explicit manual pull can repeat. Session cache bounded to 128 paths.
* Real Blender delayed-signal and retry regressions pass; existing suite 113/113.
* Blender add-on 1.10.10. No UI or unit changes.

## v1.16.10

* Failed or missing returned models no longer permanently acknowledge their signal. Automatic pull retries without requiring a new export.txt.
* Real Blender regression covers delayed model creation and transient import failure. Existing 113 checks pass.
* Blender add-on 1.10.9; no UI or unit-setting changes.

## v1.16.9

* Fix first return / deleted target: resolve replacement targets only among objects existing before import. Never delete an arriving object as its own temporary source.
* Real Blender regression covers first import and repeated import with absent/stale target names.
* Blender add-on 1.10.8. UI and 3D-Coat settings unchanged.

## v1.16.8 - 2026-09-13

"StructRNA of type Object has been removed" on pull - the real one this time.

* Cause: removing the temporary imported object pushes an undo step, and Blender
  invalidates **every** Python reference when that happens - including the target
  we were working on.  With `Import without materials` on, the target was used
  again immediately after that removal, and the whole pull failed there.  (v1.16.3
  re-resolved the objects once at the start; it had to happen *after* the removal
  too.)
* The target is now re-resolved by name after every step that can kill a
  reference, and `_match_scale` re-resolves its own object as well, so a reference
  that dies mid-flight is "the object went away" instead of a failed pull.
* A failed import now writes the **traceback** and the context (target name, object
  count) into the shared log - the message alone could not say which line failed.
* Regression test: a target that is invalidated mid-import is survived and the
  geometry still lands on the re-created object.
* Blender add-on 1.10.7.  Suite 113 checks.

## v1.16.7 - 2026-09-13

"the model never arrives" - the return can come from 3D-Coat's own pool.

* Reported, and visible in the status line as
  `Ignored export.txt outside BlenderBridge: 3DC015.fbx`: 3D-Coat had exported
  into its **own** AppLink folder (`Documents/3DC2Blender/ApplinkObjects`) rather
  than our `BlenderBridge` one, and the bridge only accepted files inside
  `BlenderBridge` - so the trip completed and Blender quietly ignored it.
* A signal pointing outside `BlenderBridge` is now accepted when the file it
  lists was written **after our last send** (that is this trip's model); older
  ones are still ignored, and the official AppLink's own signal is still never
  deleted - only read.
* Second, the unit conversion is applied to **OBJ only**: an FBX declares its own
  units and axes, and converting those again would put the model 100x off (or
  rotated) twice.
* Third, a pull now records its outcome in the shared log (`pull: ...`) and a pull
  that arrives while another is running says so instead of returning silently -
  the silence is what made this one hard to see.
* Blender add-on 1.10.6.  Suite 111 checks.

## v1.16.6 - 2026-09-13

Units are matched automatically - that is why models arrived small.

* Measured from the real exchange folder: Blender sent a 2.20 m cube and 3D-Coat
  kept it ~100x smaller.  3D-Coat reports `scene_units: CENTIMETERS` with
  `scene_scale: 1.0`, so the mismatch was never the scene scale (the number the
  v1.14 attempt used, and it is 1.0 on this machine, which is why nothing
  changed): Blender writes **metres**, 3D-Coat's scene is in **centimetres**.
* The bridge now converts by unit: `Scene.GetSceneUnits()` is read from 3D-Coat's
  state file and the factor is 100 (centimetres), 1000 (millimetres), 1 (metres),
  39.37 (inches) or 3.28 (feet), times the scene scale times Blender's own scene
  unit scale.  Nothing to type; `3D-Coat scale` overrides it if ever needed.
* The same conversion is undone on the way home, so the returned model lands at
  the size it was sent at - and the size "correction" now only ever fixes a unit
  factor: a difference that is *not* one of those is the model itself (a sculpt, a
  reduction) and is left alone and reported, instead of stretching someone's work.
* Tests are isolated from the real 3D-Coat state file from the start now (they
  used to read this machine's settings partway through, which is why the numbers
  moved between runs).  Suite 103 checks.
* Blender add-on 1.10.5.

## v1.16.3 - 2026-09-13

"StructRNA of type Object has been removed" on pull.

* The import pushes an undo step, and Blender invalidates the Python references
  to objects when it does - so the object `import_model()` handed back could
  already be dead, and touching it failed the whole pull.  Reproduced in a test
  (the failure message came out identical to the one on screen).
* The pull now takes the arriving objects' **names** from the scene instead of
  from those references (strings cannot go stale), and resolves the target and
  the temp object by name through `_object()`, which treats a dead struct as
  "gone" rather than as an error.
* A pull can no longer run twice at once: the watcher's timer and a click used to
  be able to overlap on the same model.  A second call while one is running is
  skipped.
* Blender add-on 1.10.3.  Suite 97 checks.

## v1.16.2 - 2026-09-13

A pull imports one model, not one per signal.

* Reported: the same model sometimes landed in Blender twice.  Cause found and
  reproduced in a test: 3D-Coat leaves a signal in **both** exchange roots (and
  can write the model into both), and the pull imported once per signal - same
  path twice, two "Pulled" lines, two passes over the same mesh.
* The pull now reads every signal first and then imports exactly **one** model,
  the newest, marking all the signals as seen and consuming the ones that list
  nothing foreign.  A deliberate re-pull (the button) still works, and a signal
  the official AppLink owns is still left alone.
* Regression checks: a signal in both roots imports exactly once, leaves no extra
  object behind, consumes both signals, and reports it once.
* Blender add-on 1.10.2.  Blender suite 94 checks.

## v1.16.1 - 2026-09-13

Cleanup after the audit, and the version rule.

* Deleted the parked Qt panel and its tests (no Qt, no extra window - it had no
  business staying in the tree), the stale `CoatBridgeDialog.py` (also removed
  from an installed 3D-Coat and from `install.sh`'s stale list), and the
  decision mock-up in `docs/`.
* Removed a dead helper and made every action log 3D-Coat's scale/units/axis once
  instead of twice.
* README brought back in line with reality: what each side looks like now, what
  the bridge handles quietly (scale, axis, reduction, textures, size), the real
  sizes of both halves.
* From here the version only ever moves in the last place (`v1.16.1`, `v1.16.2`,
  ...); the first two numbers are the user's to allow.  Blender add-on 1.10.1.

## v1.16.0 - 2026-09-13

A size block in 3D-Coat's panel.

* The panel now reads the current object's size out of 3D-Coat itself
  (`Scene.current().Volume().calcWorldSpaceAABB()`), shows it live, and has a
  target-size field: type the size you want and `ApplySize` scales the object in
  place (`mat4.ScalingAt(centre, factor)` + `transform_single`, so it grows about
  its own centre and does not wander).  Nothing is exported, re-imported or
  round-tripped to change a size.
* Refusals are explicit rather than silent: a zero or non-numeric target, a
  degenerate object, and "nothing selected" each say what happened; the factor
  goes into the log.
* Still no Qt and no extra window: the panel is 3D-Coat's own dialog and the
  controls are native (`Name,[min,max]` number fields, droplists, buttons).
* 3D-Coat suite 102 checks; the test harness no longer dies when a check passes
  a tuple as its detail.

## v1.15.0 - 2026-09-13

One format, one axis rule, both directions.

* Measured from a real round trip: the model Blender sent was 0.12 m across and
  the file 3D-Coat returned (FBX) was **empty**, and the two directions used
  different formats - OBJ out, FBX back.  An FBX declares its own up-axis while
  an OBJ does not, so the two directions could never be made to agree on
  orientation.
* 3D-Coat now hands the model back as **OBJ too**, so the axis rule (the `Axis`
  setting, fed by 3D-Coat's own swap-Y/Z option) applies to the export and the
  import identically.  This is what was meant to keep the two from drifting.
* Blender still reads an FBX return (any older or hand-made file), but no longer
  overrides the axes of a format that carries its own - that is how a model ends
  up rotated twice.
* Blender addon 1.10.0.  Suites: Blender 90 checks; 3D-Coat 88 + 29 + 24.

## v1.14.0 - 2026-09-13

Size and axis: detected on the 3D-Coat side, matched on the Blender side.

* **Scale.** 3D-Coat's `ApplyMeasurementScale` exports in natural units, which
  means an incoming model is divided by its scene scale and arrives small by
  exactly that factor.  The 3D-Coat side now writes its own numbers
  (`Scene.GetSceneScale()`, `GetSceneUnits()`, and the `SwapYZ` option) into its
  state file on every action, and Blender reads that file and sends the model
  multiplied by the scene scale - so a 2 m cube is 2 scene units in 3D-Coat.
  `3D-Coat scale` in the menu overrides it (0 = use 3D-Coat's own number).
* **Axis.** `SwapYZ` - 3D-Coat's "swap the Y and Z scene axes" option for Z-up
  applications - is picked up the same way.  The OBJ exporter/importer is given
  the matching `forward_axis`/`up_axis` pair (`NEGATIVE_Z`/`Y` normally,
  `Y`/`Z` when 3D-Coat swaps), so the model keeps its orientation.  `Axis` in the
  menu can force either convention.
* Verified through Blender's real exporter, not by inspection: the tests parse
  the OBJ Blender wrote and check the coordinates are 100x bigger and that Y/Z
  are exchanged, plus the manual override and the "no data from 3D-Coat" default.
* Blender addon 1.9.0.  Suites: Blender 90 checks; 3D-Coat 88 + 29 tool + 24 Qt.

## v1.13.0 - 2026-09-13

Send and Pull on the bar itself.

* The top bar now carries three entries in one row: the `Coat Bridge` settings
  menu, then **Send** (EXPORT icon) and **Pull** (IMPORT icon) to its right, so a
  round trip is one click instead of two.  The menu keeps the same two buttons
  plus every setting.
* The menu icon moved to COLLAPSEMENU so it no longer looks like Send.
* Blender addon 1.8.0.  Suite: 81 checks - the drawer really builds the three
  entries in that order, and still draws nothing on the left-hand side.

## v1.12.0 - 2026-09-13

A number field in 3D-Coat's panel - typed, not captured.

* The reduction percentage is now a **native number field in the panel**
  (`ReductionPercent,[0,100]`), and textures a native droplist (3D-Coat decides
  / on / off) - both in 3D-Coat's own dialog, still no Qt and no extra window.
  The layout syntax comes from 3D-Coat's shipped Autoexport example panel:
  `Name,[min,max]` is a number field bound to that attribute, `Name,[#a|#b]` a
  droplist, `Name,group1` a radio group, `Name,folder` / `Name,save:*.fbx` file
  pickers.  (`coat.dialog()` itself only documents buttons, which is why the
  earlier version had to capture the value from 3D-Coat's dialog instead of
  typing it - that capture still runs when the field is left at 0.)
* Typing a number stores it (`panel.process()` persists every frame), and every
  export pushes it into 3D-Coat's own decimation slider and presses OK, so the
  export dialog is never seen.  0 hands the choice back to 3D-Coat's dialog.
* 3D-Coat side suite: 81 checks (the panel really carries the two controls, the
  number field starts at the stored value, typing stores it, the droplist
  tri-state round-trips, and the export path still fills 3D-Coat's dialog in).

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