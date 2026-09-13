# Coat Bridge

A small, predictable two-way **model** bridge between **Blender** and **3D-Coat**,
built on 3D-Coat's documented AppLink protocol.  Models only: no baking, no
texture nodes, no scene surgery.

## The exchange, in full

```
Documents/AppLinks/3D-Coat/Exchange/     <- job file goes here (3D-Coat polls the root)
    import.txt                               3 lines: what to load, where to return, how to open it
    BlenderBridge/                           <- our folder, everything else lives here
        run.txt                                 empty marker: makes the folder appear in File > Export To
        bridge.obj                              the model we send (fixed name, overwritten each send)
        export.txt                              3D-Coat writes it when it sends a model back
        001.fbx                                 whatever 3D-Coat exported, named by 3D-Coat

Documents/3DCoat/Exchange/               <- 3D-Coat's own root, also written to
    BlenderBridge/                           the same three files; the bridge watches both roots
```

Two files are written by this add-on (`import.txt` at the root, `bridge.<ext>`
in the folder), plus an empty `run.txt`.  That is the whole design.

Reference implementations read while writing this: the official `io_coat3D`
AppLink that ships inside 3D-Coat (`data/ToolsPresets/InstallAppLinks/Blender4x/`,
~4200 lines across 7 files) and its GitHub cousin `io-coat3d-main`.

| Official AppLink | Coat Bridge |
| --- | --- |
| Renames objects to `__Name` on export | Never touches names |
| Replaces mesh data, UVs and materials by hidden rules | One rule: geometry in, everything else stays |
| Bakes textures and builds its own node groups | Nothing to do with textures |
| `3DC2Blender` helper directory, applink object pools, folder size limits | one fixed file name |
| `extension.txt`, `preset.txt`, parameter files, a 12-folder state layout | `import.txt` + the model - nothing else |
| 4200 lines across 7 files | 900 lines across 6 files |

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
`<exchange>/BlenderBridge/`, which 3D-Coat then lists under `File > Export To`.

## Use

**Blender -> 3D-Coat**

1. Select the object to work on (no selection = every visible mesh).
2. Pick what 3D-Coat should do with it: `Per-Pixel Painting`, `Sculpt Object
   (voxel)`, `Retopo Mesh`, `Auto-Retopology`, ... and the file format.
3. **Send to 3D-Coat**.  If 3D-Coat is not running the job waits in the exchange
   folder until it is - the `Start 3D-Coat` button is right there.

**3D-Coat -> Blender**

* Use 3D-Coat's `File > Export To > BlenderBridge` (or `Bring object back`).
  With *Auto pull* on, the result is imported within ~2 s and merged **into the
  object it came from**: same name, same materials, same place in the outliner,
  new geometry.
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

## Notes (all measured on 3D-Coat 2026)

* The job file is polled **in the exchange root only** - a copy inside the app
  folder is ignored, so it stays at the root.
* 3D-Coat registers **two** roots (it logs both on startup) and writes its
  exports into its own one, so the bridge watches the app folder of every root.
* `extension.txt` in the app folder is ignored: 3D-Coat hands back FBX.  The
  bridge reads the format from the returned file and enables the FBX add-on on
  demand.
* Anything 3D-Coat puts inside a `BlenderBridge` folder is ours; anything else is
  left alone, so the official AppLink can stay enabled.
* Nothing in the Blender scene is renamed, joined or deleted.

## Tests

```bash
tests/run_tests.sh                                    # headless round trip, 62 checks
tests/test_coat_export.sh path/to/a/real/export.fbx    # return leg on a real 3D-Coat file
tests/live_roundtrip.sh 900                            # real 3D-Coat, waits for your click
```

`run_tests.sh` gives Blender a throwaway script folder and drives a full round
trip against two temporary exchange roots: send, protocol file contents, in-place
update, second-root signals, ignored foreign signals, format switch, watcher,
error paths.

`test_coat_export.sh` takes a file 3D-Coat really exported and checks the bridge
pulls it - the regression check to run after a 3D-Coat update.

`live_roundtrip.sh` sends a cube through the real exchange folder to the running
3D-Coat, waits for the return and reports what came back.
