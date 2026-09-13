# Changelog

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
