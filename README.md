# Coat Bridge

A small, predictable two-way **model** bridge between **Blender** and **3D-Coat**,
built on 3D-Coat's documented AppLink protocol.  Models only: no baking, no
texture nodes, no scene surgery.

Reference implementations read while writing this: the official `io_coat3D`
AppLink that ships inside 3D-Coat (`data/ToolsPresets/InstallAppLinks/Blender4x/`,
~4200 lines across 7 files) and its GitHub cousin `io-coat3d-main`.  This bridge
keeps only what a model round trip needs:

| Official AppLink | Coat Bridge |
| --- | --- |
| Renames objects to `__Name` on export | Never touches names |
| Replaces mesh data, UVs and materials by hidden rules | One rule: geometry in, everything else stays |
| Bakes textures and builds its own node groups | Nothing to do with textures |
| 12 state folders plus a `3DC2Blender` helper directory | One folder, `<exchange>/BlenderBridge` |
| 4200 lines across 7 files | 1000 lines across 6 files |

## Requirements

* Blender 4.2+ (developed and tested on 5.2.0 LTS)
* 3D-Coat 4.8.15+ (tested against 3D-Coat 2026)

## Install

```bash
cp -r coat_bridge "$APPDATA/Blender Foundation/Blender/5.2/scripts/addons/"
```

Enable **Coat Bridge** in `Edit > Preferences > Add-ons`, then open the `3D-Coat`
tab in the 3D view sidebar and press **Detect** once: it finds the exchange
folder, stores it in the add-on preferences and creates
`<exchange>/BlenderBridge`, which 3D-Coat then lists under `File > Export To`.

## Use

**Blender -> 3D-Coat**

1. Select the object to work on (no selection = every visible mesh).
2. Pick what 3D-Coat should do with it: `Per-Pixel Painting`, `Sculpt Object
   (voxel)`, `Retopo Mesh`, `Auto-Retopology`, ... and the file format.
3. **Send to 3D-Coat**.  If 3D-Coat is not running the job waits in the exchange
   folder until it is - the `Start 3D-Coat` button is right there.

**3D-Coat -> Blender**

* After editing, use 3D-Coat's `File > Bring object back`.  With *Auto pull* on,
  the result is imported the moment 3D-Coat writes it, merged **into the object
  it came from**: same name, same materials, same place in the outliner, new
  geometry.
* Or use `File > Export To > BlenderBridge`, then press **Pull from 3D-Coat** -
  that creates a new object and links it for the next round trip.
* `Unlink selected` stops tracking an object, so the next pull becomes a new
  object instead of replacing it.

## Options

| Option | Meaning |
| --- | --- |
| Mode | How 3D-Coat opens the mesh (`[ppp]`, `[vox]`, `[uv]`, `[autopo]`, ...) |
| Format | `OBJ` (materials + UV, recommended), `FBX`, `PLY`, `STL` |
| Auto pull | Watch the exchange folder every 2 s; off = manual **Pull** only |
| Skip dialogs | Let 3D-Coat import and export with its current settings instead of asking |
| Modifiers | Export evaluated meshes |

## Notes

* 3D-Coat registers **two** exchange folders and logs both on startup:
  `Documents/AppLinks/3D-Coat/Exchange` (the documented one, which it reads job
  files from) and `Documents/3DCoat/Exchange` (its own, which receives the
  exports).  The bridge writes the job into the first and watches the return
  signals in every registered root - otherwise a return through
  `File > Export To > BlenderBridge` lands in the second root and is missed.
* The two add-ons coexist: the official AppLink watches `.../export.txt` and
  `.../Blender/`, Coat Bridge owns `.../BlenderBridge/` and leaves any signal
  file it does not own untouched.
* Everything it writes is prefixed `coat_bridge_`, so ownership is never guessed.
* 3D-Coat ignores `extension.txt` in the app folder and hands back FBX through
  `File > Export To`; the bridge reads the format from the returned file and
  enables the FBX add-on on demand.
* Nothing in the Blender scene is renamed, joined or deleted.

## Tests

```bash
tests/run_tests.sh                                   # headless round trip, 58 checks
tests/test_coat_export.sh path/to/a/real/export.fbx   # return leg on a real 3D-Coat file
tests/live_roundtrip.sh 900                           # real 3D-Coat, waits for your click
```

`run_tests.sh` gives Blender a throwaway script folder and drives a full round
trip against two temporary exchange roots: send, protocol files, in-place update,
second-root signals, ignored foreign signals, format switch, watcher, error paths.

`test_coat_export.sh` takes a file 3D-Coat really exported and checks the bridge
pulls it - the second-regression check after a 3D-Coat update.

`live_roundtrip.sh` sends a cube through the real exchange folder to the running
3D-Coat, waits for the return and reports what came back.
