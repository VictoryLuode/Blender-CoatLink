# Coat Bridge

A small, predictable two-way **model** bridge between **Blender** and **3D-Coat**.
Models only: no baking, no texture nodes, no scene surgery.

Both halves share one exchange folder, one file layout and one vocabulary, and
their UIs are deliberately mirrors of each other:

| | Blender side | 3D-Coat side |
| --- | --- | --- |
| Where | **Coat Bridge** button in the top bar (right-hand group) | Panel pinned to the **top-right** of the viewport |
| Shape | popover menu | non-modal dialog, 320 px wide |
| First row | `Send to 3D-Coat` / `Pull from 3D-Coat` | `Send to Blender` / `Pull from Blender` |
| Options | `Open as`, toggles | - (one format, nothing to pick) |
| Utilities | `Detect`, `Folder`, `Start 3D-Coat`, `Unlink` | `Detect`, `Folder`, `Start Blender` |
| Last row | status + details box | status + details line |
| Source | `coat_bridge/` (Blender add-on) | `coat_side/CoatBridge.py` (+ menu XML) |

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

**Blender side**

```bash
cp -r coat_bridge "$APPDATA/Blender Foundation/Blender/5.2/scripts/addons/"
```

Enable **Coat Bridge** in `Edit > Preferences > Add-ons`, then press **Detect**
once (in the menu below): it finds the exchange folder, stores it in the add-on
preferences and creates `<exchange>/BlenderBridge/`, which 3D-Coat then lists
under `File > Export To`.

**3D-Coat side**

```bash
coat_side/install.sh                       # copies the script + the menu entry
```

It lands in `Documents/3DCoat/UserPrefs/Scripts/CoatBridge/` and adds
`Scripts > Coat Bridge`.  Run it once - the panel stays open until you close it.
3D-Coat may need a restart before the new menu entry shows up.

The launcher also goes into the **Windows** menu and, with an icon, into the
**tool panel of the rooms listed in `TOOL_ROOMS`** (Voxels by default).  The
panel's `RemoveLauncher` button takes all of that back out again.

### Where the panel can live (and where it cannot)

| Spot | Works | How |
| --- | --- | --- |
| Viewport top-right, non-modal panel | yes | `coat.dialog().noModal().topRight().width()` |
| Room tool panel (a real button in a panel, with icon) | yes | `ui.insertInToolset(room, section, toolID)` |
| Main menus (24 places: File, Edit, View, Windows, Scripts, Voxels, Retopo, Bake, Layers, Textures, ...) | yes | `ui.insertInMenu()` or `ExtraMenuItems/*.xml` |
| Room RMB panel | yes | `coat.start_rmb_panel()` / the room's `RMBMenu.py` |
| Whole custom workspace | yes | `Documents/3DCoat/UserPrefs/Rooms/CustomRooms/<ID>/` |
| Space-panel buttons | no | `show_space_panel("*Subset")` only takes built-in subsets |
| **Right-hand dock column (VoxTree / Layers / Multires / ...)** | **no** | those are built-in window ids in each room's `Layout.xml`; the Python API has no call to register a window, `ui.enableWindow()` only toggles built-ins, and the Qt manager only undocks built-ins |

## Scale and units

3D-Coat exports with its own scene scale (`Scene.GetSceneScale()`: "the length of
1 scene unit when you export the scene"), so a model can come home at a fixed
multiple - x100 with FBX is the classic one.  The bridge does not rely on either
side being configured correctly:

* on send it records the model's size (world-space bounding-box diagonal),
* on pull it measures the model that came back and scales it to the recorded size
  when the two differ by more than 2% (reported in the status as `scale x0.01`),
* `Match scale` in the menu turns that off; a factor beyond x1000 is reported but
  not applied,
* both sides append to `Documents/3DCoat/CoatBridge.log` - the Blender side logs
  the sent size and the correction, the 3D-Coat side logs its own
  `units=... scale=...`, so the real factor is always readable.

## Use

Everything is in one place: the **Coat Bridge** button in the top bar, in the
right-hand group next to the other add-on buttons (Restart, AR, Export, Import).
It opens a popup holding the whole bridge.

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

## Menu contents

| Entry | Meaning |
| --- | --- |
| Send to 3D-Coat | Export the selection and queue it |
| Pull from 3D-Coat | Take a returned model right now |
| Open as | How 3D-Coat opens the mesh (`[ppp]`, `[vox]`, `[uv]`, `[autopo]`, ...) |
| Auto pull | Watch the exchange folder every 2 s; off = manual **Pull** only |
| Skip dialogs | Let 3D-Coat import and export with its current settings |
| Modifiers | Export evaluated meshes |
| No materials | A pulled model arrives as bare geometry (its materials are dropped) |
| Axis / scale | read from 3D-Coat (swap Y/Z + scene scale) and applied on the way out |
| Export settings | live in 3D-Coat's panel: reduction percentage + textures, applied without its dialog |
| Detect | Find the exchange folder and prepare the AppLink folder |
| Folder | Show the exchange folder in the file browser |
| Start 3D-Coat | Launch 3D-Coat so it picks up the queued import |
| Unlink selected | Stop tracking, so the next pull becomes a new object |
| Status box | Last action, target object, linked objects |

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
* The UI is a single popover button in the top bar, drawn the same way as other
  top-bar extras: a panel with `bl_space_type = 'TOPBAR'`,
  `bl_region_type = 'HEADER'`, hooked into `TOPBAR_HT_upper_bar` and drawn only
  where `context.region.alignment == 'RIGHT'`.
* Nothing in the Blender scene is renamed, joined or deleted.

## Tests

```bash
tests/run_tests.sh                                    # Blender side, headless round trip, 65 checks
tests/test_coat_export.sh path/to/a/real/export.fbx    # Blender side, return leg on a real 3D-Coat file
tests/live_roundtrip.sh 900                            # real 3D-Coat, waits for your click
python coat_side/tests/check_coat_api.py               # 3D-Coat side, API names vs the shipped stubs
python coat_side/tests/test_coat_side.py               # 3D-Coat side, 38 logic checks (fake coat module)
```

The scripts pick the newest stable Blender build automatically; pass a path as
the first (or second) argument to override.  The 3D-Coat tests need no 3D-Coat
at all: one parses `coat.pyi` / `CMD.pyi`, the other drives the panel through a
stand-in `coat` module.

`run_tests.sh` gives Blender a throwaway script folder and drives a full round
trip against two temporary exchange roots: send, protocol file contents, in-place
update, second-root signals, ignored foreign signals, format switch, watcher,
error paths.

`test_coat_export.sh` takes a file 3D-Coat really exported and checks the bridge
pulls it - the regression check to run after a 3D-Coat update.

`live_roundtrip.sh` sends a cube through the real exchange folder to the running
3D-Coat, waits for the return and reports what came back.
