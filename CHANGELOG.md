# Changelog

## v1.0.0 - 2026-09-13

First release.

* Two-way model bridge on the 3D-Coat AppLink protocol: `Send to 3D-Coat` and
  `Pull from 3D-Coat`, plus an auto-pull watcher.
* In-place update: a returned model replaces the geometry of the object it came
  from, keeping its name, materials and placement.
* Files owned by the bridge are prefixed `coat_bridge_` and are the only signal
  files it consumes, so it can run next to the official AppLink.
* Formats: OBJ (default), FBX, PLY, STL.  The FBX add-on is enabled on demand.
* 3D-Coat side setup is one click: `Detect` creates
  `<exchange>/BlenderBridge/{run.txt,extension.txt}` so 3D-Coat lists the target
  under `File > Export To`.
* Optional texture hook-up from `textures.txt` (base colour, normal, roughness,
  metallic, emission) straight onto the Principled BSDF.
* 48-check headless end-to-end suite (`tests/run_tests.sh`).
