# Changelog

## v1.0.0 - 2026-09-13

First release.  Models only, by design.

* Two-way model bridge on the 3D-Coat AppLink protocol: `Send to 3D-Coat` and
  `Pull from 3D-Coat`, plus a 2 s auto-pull watcher.
* In-place update: a returned model replaces the geometry of the object it came
  from, keeping its name, materials and placement.
* Files owned by the bridge are prefixed `coat_bridge_` and are the only signal
  files it consumes, so it can run next to the official AppLink.
* Formats: OBJ (default), FBX, PLY, STL.  The FBX add-on is enabled on demand.
* 3D-Coat side setup is one click: `Detect` creates
  `<exchange>/BlenderBridge/{run.txt,extension.txt}` so 3D-Coat lists the target
  under `File > Export To`.
* One `Skip dialogs` switch covers 3D-Coat's import and export dialogs.
* Verified: 50-check headless suite (`tests/run_tests.sh`), plus a live round trip
  against a running 3D-Coat (`tests/live_roundtrip.sh`) - 3D-Coat consumed the
  job file and imported the model.
