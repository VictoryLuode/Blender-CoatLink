# Changelog

## v1.3.0 - 2026-09-13

The 3D-Coat side, mirroring the Blender menu.

* `coat_side/CoatBridge.py`: a non-modal panel pinned to the top-right of the
  3D-Coat viewport (`coat.dialog().caption().noModal().topRight().width(320)`),
  with the same caption, row order and wording as the Blender menu.
* `Send to Blender` drives 3D-Coat's own AppLink target when it exists
  (`ui.presentInUI("$BlenderBridge")` + `ui.setFileForFileDialog` + `ui.cmd`),
  and falls back to `CMD.ExportObjectsAndTextures`; either way the Blender side
  gets the signal it waits for.
* `Pull from Blender` imports exactly what Blender queued
  (`Scene.importMesh` on the model named in `import.txt`) and then consumes that
  queue file, so 3D-Coat's own AppLink poller cannot import it a second time.
* `Detect`, `Folder`, `Start Blender` (via `io.listBlenderInstallFolders`), an
  `FBX`/`OBJ` format switch persisted in `Documents/3DCoat/CoatBridge.json`, and
  a self-diagnosing status line.
* Menu entry `Scripts > Coat Bridge`, from `ExtraMenuItems/CoatBridge.xml` and
  an idempotent self-registration, so a bare copy of the .py also works.
* Verified without 3D-Coat running: `coat_side/tests/check_coat_api.py` proves
  every API call exists in 3D-Coat's shipped `coat.pyi` / `CMD.pyi` stubs, and
  `coat_side/tests/test_coat_side.py` runs the panel against a fake `coat`
  module - 38 checks covering the exchange layout, the queue, both export
  routes, the signal files, settings persistence and the panel layout.

## v1.2.0 - 2026-09-13

One menu, in the top bar.

* The whole UI is now a popover button in the top bar, in the right-hand group
  next to the other add-on extras - same recipe as the bundled `auto_reload`
  extension (`bl_space_type='TOPBAR'`, `bl_region_type='HEADER'`, hooked with
  `TOPBAR_HT_upper_bar.prepend`, drawn when `context.region.alignment == 'RIGHT'`).
* The 3D-view sidebar panel and its Details sub-panel are gone: send, pull, mode,
  format, the three toggles, detect/folder/launch/unlink and the status box are
  all inside the one menu.
* Verified: 65-check headless suite (the panel, the top-bar hook and the absence
  of the sidebar panel are asserted) + `tests/test_coat_export.sh` on a real
  3D-Coat export.
* Test scripts now pick the newest stable Blender build instead of a pinned path
  (Blender Launcher replaced 5.2.0 with 5.2.1 LTS during this work).

## v1.1.0 - 2026-09-13

Simpler exchange: everything lives in one folder.

* The model is always `BlenderBridge/bridge.<ext>` - no per-send file names
  (`coat_bridge_out/back`) any more.
* `extension.txt` is gone: measured against 3D-Coat 2026, it is ignored.
* The root-level `export.txt` is no longer a separate return channel to reason
  about: a return is accepted when it points inside a `BlenderBridge` folder,
  wherever the signal file sits.
* Ownership is one rule: *files inside a BlenderBridge folder are ours*.  The
  `coat_bridge_` prefix rule and the pending-path matching are gone.
* The job file stays in the exchange root on purpose: 3D-Coat only polls it
  there (a copy inside the app folder was ignored for 3 minutes, the root copy
  was taken within 20 seconds).
* Remembers a single target object per send instead of a path-keyed table.
* Verified: 62-check headless suite and `tests/test_coat_export.sh` on a real
  3D-Coat export (4280 vertices / 8556 polygons).

## v1.0.0 - 2026-09-13

First release.  Models only, by design.

* Two-way model bridge on the 3D-Coat AppLink protocol: `Send to 3D-Coat` and
  `Pull from 3D-Coat`, plus a 2 s auto-pull watcher.
* In-place update: a returned model replaces the geometry of the object it came
  from, keeping its name, materials and placement.
* Formats: OBJ (default), FBX, PLY, STL.  The FBX add-on is enabled on demand.
* 3D-Coat side setup is one click: `Detect` creates
  `<exchange>/BlenderBridge/` so 3D-Coat lists the target under
  `File > Export To`.
* One `Skip dialogs` switch covers 3D-Coat's import and export dialogs.
* Handles 3D-Coat's two registered exchange roots: the job file goes to the
  documented root, return signals are looked for in every root.
