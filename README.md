# Coat Bridge

A small, predictable two-way model bridge between **Blender** and **3D-Coat**,
built on 3D-Coat's documented AppLink protocol.

Reference implementations read while writing this: the official `io_coat3D`
AppLink that ships inside 3D-Coat (`data/ToolsPresets/InstallAppLinks/Blender4x/`,
~4200 lines across 7 files) and its GitHub cousin `io-coat3d-main`.  This bridge
keeps only the model path, and drops everything that made the official one hard
to live with:

| Official AppLink | Coat Bridge |
| --- | --- |
| Renames objects to `__Name` on export | Never touches names |
| Replaces mesh data, UVs and materials with hidden rules | One rule: geometry in, everything else stays |
| Bakes and wires its own texture node groups | Optional, minimal map hook-up, no extra nodes beyond the maps |
| 12 state folders and a `3DC2Blender` helper directory | One folder, `<exchange>/BlenderBridge` |
| Shares `Exchange/export.txt` with nothing else | Only consumes the files it owns |
| 4200 lines | ~1000 lines, split by concern |

## Requirements

* Blender 4.2+ (developed and tested on 5.2.0 LTS)
* 3D-Coat 4.8.15+ (tested against 3D-Coat 2026)

## Install

```bash
cp -r coat_bridge "$APPDATA/Blender Foundation/Blender/5.2/scripts/addons/"
```

Then enable **Coat Bridge** in `Edit > Preferences > Add-ons` and open the
`3D-Coat` tab in the 3D view sidebar.  Press **Detect** once: it finds the
exchange folder, stores it in the add-on preferences and creates
`<exchange>/BlenderBridge`, which 3D-Coat then lists under `File > Export To`.

## Use

**Blender -> 3D-Coat**

1. Select the object you want to work on (no selection = every visible mesh).
2. Pick what 3D-Coat should do with it: `Per-Pixel Painting`, `Sculpt Object
   (voxel)`, `Retopo Mesh`, `Auto-Retopology`, ... and the file format.
3. **Send to 3D-Coat**.  If 3D-Coat is not running, the job waits in the
   exchange folder until it is - the `Start 3D-Coat` button is right there.

**3D-Coat -> Blender**

* After editing, use 3D-Coat's `File > Bring object back`.  With *Auto pull* on,
  the result is imported the moment 3D-Coat writes it, and it is merged **into
  the object it came from**: same name, same materials, same place in the
  outliner, new geometry.
* Or use `File > Export To > BlenderBridge`, then press **Pull from 3D-Coat** -
  that creates a new object and links it for the next round trip.
* `Unlink selected` stops tracking an object, so the next pull becomes a new
  object instead of replacing it.

## Options

| Option | Meaning |
| --- | --- |
| Mode | How 3D-Coat opens the mesh (`[ppp]`, `[vox]`, `[uv]`, `[autopo]`, ...) |
| Format | `OBJ` (materials + UV, recommended), `FBX`, `PLY`, `STL` |
| Auto pull | Watch the exchange folder; off = manual **Pull** only |
| Apply textures | Wire `textures.txt` maps (base colour, normal, roughness, metallic, emission) into the materials after a pull |
| Skip import / export dialog | Let 3D-Coat use the settings instead of asking |
| Modifiers | Export evaluated meshes |
| Preset | 3D-Coat export preset used on the way back (default `Blender Cycles`) |

## Notes

* The two add-ons coexist: the official AppLink watches `Exchange/export.txt` and
  `Exchange/Blender/`, Coat Bridge additionally owns `Exchange/BlenderBridge/`
  and leaves any signal file it does not own untouched.
* Files it creates are prefixed `coat_bridge_`, so ownership is never guessed.
* Nothing in the Blender scene is renamed, joined or deleted.

## Tests

```bash
tests/run_tests.sh [path/to/blender.exe]
```

Runs Blender headless with a throwaway script folder and drives a full round trip
against a temporary exchange folder: sends a cube, fakes 3D-Coat's return with a
denser sphere, checks the in-place update, the ignored foreign signal, the format
switch, the watcher, the texture hook-up and the error paths.  48 checks.
