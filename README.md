# CoatLink

A small, predictable two-way **model** bridge between **Blender** and **3D-Coat**.
Models only: no baking, no texture nodes, no scene surgery.

Both halves share one exchange folder, one file layout and one vocabulary, and
their UIs are deliberately mirrors of each other:

| | Blender | 3D-Coat |
| --- | --- | --- |
| Where | one **CoatLink** button in the top bar | three buttons at the end of the room tool list (Voxels / Paint) |
| The menu | the popover inside that button - the bar holds nothing else | the panel opened from the tool strip |
| Scope | `Scope` droplist: **Selected** / **Whole scene** | the same droplist, at the top of the panel |
| Actions | `Send`, `Pull` | `Send`, `Pull`, and `To voxels` (turns the selected object and its children into voxel volumes) |
| Options | under **Send options**: `Scope` and `Import as` (voxel by default) | the same scope droplist, first thing in the panel |
| Settings | `Auto receive`, `Without materials` | reduction percentage, textures, size readout with `RefreshStats` |
| Below that | under **Setup**: `Axis`, `Scale override`, `Match scale`, `Modifiers`, `Skip dialogs`, then `Detect`, `Open folder`, `Start 3D-Coat`, `Force re-read return signal`, `Unlink selected` | under **Setup**: `Detect`, `Open folder`, `Start Blender`, `Remove tool buttons` |
| Source | `coat_bridge/` (Blender add-on, 8 files) | `coat_side/CoatBridgeLib.py` + three entry scripts + two XML files |

Both menus carry the same sections in the same order with the same words - the two
options (`Scope`, `Import as`), then `Send` / `Pull`, then the settings, then the rest.
Nothing is behind a fold-out on either side: a control you have to unfold is the one
you cannot find when it matters.  The tool-strip buttons keep
their longer labels (`Send to Blender`, `Pull from Blender`) because there they stand
on their own, outside any menu; the panel's own buttons say `Send` and `Pull`.

The 3D-Coat panel is 3D-Coat's **own** dialog (`coat.dialog()...topRight()`), never
a window of ours and never Qt.  Its controls are native too, using the layout
3D-Coat's shipped Autoexport panel uses: `Name,[min,max]` is a number field,
`Name,[#a|#b]` a droplist, `Name` a checkbox.

## Requirements

* Blender 4.2+ (developed and tested on 5.2 LTS)
* 3D-Coat 4.8.15+ (tested against 3D-Coat 2026)
* Windows for the installers and the tests; the add-on itself is OS-independent
* a Python for the 3D-Coat installer - 3D-Coat ships one, so normally there is
  nothing to install

## Install

Pick the first route that works for you.  All three land the same files.

### 1. Blender add-on, no commands at all

1. Download **`coat_bridge.zip`** from the
   [latest release](../../releases/latest).
2. In Blender: **Edit > Preferences > Add-ons > ▾ (top right) > Install from Disk…**
   and pick that zip.  (Blender 4.2 and newer.)
3. Enable **CoatLink** in the add-on list, then press **Detect** in its menu.

That is the whole Blender side - no copying, no paths, no shell.

### 2. 3D-Coat side: double-click it

Unzip the release and **double-click `install.cmd`**.  That is the whole job:

* it uses the Python that 3D-Coat itself ships, so nothing has to be installed
* it works both folders out on the spot and writes the menu entries with **your**
  paths - 3D-Coat needs absolute script paths, which is why the XMLs are generated
  rather than shipped
* it copies the button icons next to 3D-Coat's own when that folder is writable,
  and carries on without them when it is not (no admin rights anywhere).  If
  3D-Coat lives in `C:\Program Files` that folder needs administrator rights -
  run `install.cmd` once **as administrator** to get the icons, or keep the default
  tool icons: the buttons and the panel work either way, and the installer says
  which of the two happened
* it clears out anything an older layout of this project left behind
* running it twice is harmless

Rather not unzip anything?  Download **`CoatLink-Setup.py`** - the same installer
as a single file - and paste one line into 3D-Coat's Python console:

```python
exec(open(r"C:\Downloads\CoatLink-Setup.py", encoding="utf-8").read())
```

With git-bash, MSYS or WSL, `./install.sh` does the 3D-Coat half too.  PowerShell
can do both halves in one go:

```powershell
.\install.ps1
```

If Windows refuses to run scripts, start it explicitly - normal and safe for a
script you just downloaded and read:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
```

**All four doors run the same installer** (`coat_side/CoatLinkInstall.py`), so they
cannot drift apart - a test installs with each and compares the trees byte for byte.

Then **restart 3D-Coat** and look for **Scripts > CoatLink**.  The three tool
buttons also appear at the end of the Sculpt and Paint tool lists.

To take it all back out: `install.cmd --uninstall`, `.\install.ps1 -Uninstall`,
`./install.sh --uninstall`, or `python CoatLinkInstall.py --uninstall`.  It removes
its own files and nothing else.

Explicit paths, when detection is not enough: `-BlenderAddons`, `-CoatScripts`,
`-CoatDir` (PowerShell), the same three in that order or `BLENDER_ADDON_DIR`,
`COAT_SCRIPTS_DIR`, `COAT_DIR` (bash), `--scripts`, `--coat` (Python).  Add
`-BlenderOnly` / `-CoatOnly` for one half.

### 3. No scripts at all - copy the files by hand

Five destinations.  `<ver>` is your Blender version folder.

| What | From | To |
| --- | --- | --- |
| Blender add-on | `coat_bridge\` (7 `.py` files) | `%APPDATA%\Blender Foundation\Blender\<ver>\scripts\addons\coat_bridge\` |
| 3D-Coat scripts | `coat_side\CoatBridge*.py` (5 files: the library, the receipts helper and the three entries) | `%USERPROFILE%\Documents\3DCoat\UserPrefs\Scripts\CoatBridge\` |
| Tool buttons | `coat_side\tools\CoatBridgeTools.xml.in` | `…\Scripts\ExtraMenuItems\CoatBridgeTools.xml`, with every `__SCRIPT_DIR__` replaced by the `CoatBridge` folder above, forward slashes (`C:/Users/…/CoatBridge`) |
| Scripts menu entry | the block below | `…\Scripts\ExtraMenuItems\CoatBridge.xml` |
| Button icons (optional) | `coat_side\icon\*.png` (4 files) | `<3D-Coat program folder>\data\Textures\icons64\` |

`CoatBridge.xml`, verbatim, with the same forward-slash path:

```xml
<ClassArray.ExtraMenuItem>
	<ExtraMenuItem>
		<MenuPath>Scripts</MenuPath>
		<MenuItem>CoatBridge</MenuItem>
		<inRoom></inRoom>
		<inSection></inSection>
		<Command>script:C:/Users/you/Documents/3DCoat/UserPrefs/Scripts/CoatBridge/CoatBridge_Setup.py</Command>
	</ExtraMenuItem>
</ClassArray.ExtraMenuItem>
```

Then start Blender, enable **CoatLink** and press **Detect**.

The two XML files above are the fiddly part - every path in them has to be yours -
so `python coat_side/CoatLinkInstall.py` will write both for you once the scripts
are in place (`--scripts <folder>` if it cannot find them, `--uninstall` to undo).

### Where the 3D-Coat panel can live (and where it cannot)

| Spot | Works | How |
| --- | --- | --- |
| Viewport top-right, non-modal panel | yes | `coat.dialog().noModal().topRight().width()` |
| Room tool panel (a real button in a panel, with icon) | yes | `ui.insertInToolset(room, section, toolID)`, or the XML above |
| Main menus (24 places: File, Edit, View, Windows, Scripts, Voxels, Retopo, Bake, Layers, Textures, …) | yes | `ui.insertInMenu()` or `ExtraMenuItems/*.xml` |
| Room RMB panel | yes | `coat.start_rmb_panel()` / the room's `RMBMenu.py` |
| Whole custom workspace | yes | `Documents/3DCoat/UserPrefs/Rooms/CustomRooms/<ID>/` |
| Space-panel buttons | no | `show_space_panel("*Subset")` only takes built-in subsets |
| **Right-hand dock column (VoxTree / Layers / Multires / …)** | **no** | those are built-in window ids in each room's `Layout.xml`; the Python API has no call to register a window, `ui.enableWindow()` only toggles built-ins, and the Qt manager only undocks built-ins |

## Use

**Blender → 3D-Coat**

1. Select the object to work on (no selection = every visible mesh), or switch on
   the **`Whole scene`** toggle left of `Send` to send every visible object.  The
   status line always says which scope the send used.
2. Pick how 3D-Coat should open it in `Import as`: `Per-Pixel Painting`,
   `Sculpt Object (voxel)`, `Retopo Mesh`, `Auto-Retopology`, …
3. **Send**.  If 3D-Coat is not running the job waits in the exchange folder
   until it is - `Start 3D-Coat` is right there in the menu.

**3D-Coat → Blender**

* `Send to Blender` hands over **the node selected in the sculpt tree, plus its
  children** - not the scene.  The panel's `Send scope` droplist switches that to
  `whole scene`, which is 3D-Coat's own export (and the only route that can carry
  textures).  The selection route extracts the mesh straight from the tree, applies
  the panel's reduction percentage, and refuses rather than guessing: with nothing
  selected it says so and sends nothing.

* 3D-Coat's `File > Export To > BlenderBridge` (or `Bring object back`).  With
  **Auto receive** on, the result is imported within ~2 s and merged into the
  object it came from: same name, same materials, same place in the outliner,
  new geometry.  Separate objects stay separate objects.
* `Unlink selected` stops tracking an object, so the next pull becomes a new
  object instead of replacing it.  `Force re-read return signal` in the
  *Advanced* fold pulls the last model again on purpose.

### Menu contents (Blender side)

| Entry | Meaning |
| --- | --- |
| Whole scene (top bar) | Send every visible object instead of the selection |
| Send / Pull (top bar) | Export the selection and queue it / take a returned model now |
| Import as | How 3D-Coat opens the mesh (`[ppp]`, `[vox]`, `[uv]`, `[autopo]`, …) |
| Auto receive | Watch the exchange folder every 2 s; off = manual **Pull** only |
| Without materials | A pulled model arrives as bare geometry |
| Axis / Scale override | Read from 3D-Coat, or forced (see below) |
| Match scale | Keep the recorded size when a pulled model comes back at another size |
| Modifiers | Export evaluated meshes |
| Skip dialogs | Let 3D-Coat import and export with its current settings |
| Detect / Folder | Find the exchange folder and prepare the AppLink folder / open it |
| Start 3D-Coat | Launch 3D-Coat so it picks up the queued import |
| Force re-read return signal | Pull the last return model again, ignoring the pull record |
| Unlink selected | Stop tracking, so the next pull becomes a new object |

## The exchange, in full

```
Documents/AppLinks/3D-Coat/Exchange/     <- job file goes here (3D-Coat polls the root)
    import.txt                               3 lines: what to load, where to return, how to open it
    BlenderBridge/                           <- our folder, everything else lives here
        run.txt                                 empty marker: makes the folder appear in File > Export To
        bridge.obj                              the model we send (fixed name, overwritten each send)
        export.txt                              3D-Coat writes it when it sends a model back
        bridge.obj                              what 3D-Coat sends back (OBJ both ways)
        pull-history.json                       what we already imported, so a restart does not re-import it
    CoatLink_AfterImport.py                  run by 3D-Coat after the import: unparents the objects

Documents/3DCoat/Exchange/               <- 3D-Coat's own root, also written to
    BlenderBridge/                           the same files; the bridge watches both roots
```

This add-on writes `import.txt` at the root, `bridge.obj` and
`CoatLink_AfterImport.py` (the after-import script `import.txt` points at) and an
empty `run.txt`; the two markers in there are state.  That is the
whole design.  `bridge.obj` is the model in **both** directions, so there is
exactly one axis rule and one unit rule to keep straight.

### What the two sides quietly handle for you

* **Units.** 3D-Coat's scene unit is read from its own state file
  (`Scene.GetSceneUnits()`: centimetres on a default install) and the model is
  multiplied by that factor on the way out, divided back on the way in, so 2 m in
  Blender is 2 m in 3D-Coat.  A size difference that is *not* a clean unit factor
  is reported and left alone, never stretched - your sculpting is safe.
  `Scale override` forces a factor; 0 means auto.
* **Axis.** 3D-Coat's `SwapYZ` ("swap the Y and Z scene axes", for Z-up
  applications) is detected the same way, and one rule covers both directions -
  which is what keeps them from drifting apart.  `Axis` can force either
  convention.  Formats that carry their own axis (FBX) are left alone.
* **Reduction.** A percentage in the 3D-Coat panel goes into 3D-Coat's own
  decimation slider (`$DecimationParams::ReductionPercent`) and the dialog's OK is
  pressed for you, so its export dialog is never seen; the selected-node route
  passes it to `fromReducedVolume(volume, reduction_percent, …)`, whose parameter
  carries that name.  The percentage means *removed*, not *kept*; the panel's
  estimate uses the formula the official template uses
  (`remaining = original × (100 − pct) / 100`) and says so.
* **Textures.** A droplist: let 3D-Coat decide, force on, force off.
* **No leftover parent node.**  3D-Coat wraps an imported file in a node named
  after it (`bridge.obj` -> "bridge"), which Blender has no equivalent of.  The job
  file carries `[pythonfile CoatLink_AfterImport.py]`, so 3D-Coat runs a short
  script right after the import: the objects are moved up to the sculpt root and
  the empty wrapper is deleted - only that wrapper, and only if it is the one for
  this model.  A Pull made from the panel does the same in code.  The sculpt tree
  then matches the Blender outliner.
* **Selection, not the scene.**  `Send` exports `Scene.current()` with
  `with_subtree=True, all_selected=False`, so sculpting in progress cannot leak
  into Blender, and a return that loses its object groups is refused instead of
  being merged.
* **Names.** Objects keep their names in both directions.  Groups that come back
  are matched to the objects they came from and updated in place; renamed objects
  are still found; unrelated same-name objects are never overwritten.

## Design notes

Reference implementations read while writing this: the official `io_coat3D`
AppLink that ships inside 3D-Coat (`data/ToolsPresets/InstallAppLinks/Blender4x/`,
~4200 lines across 7 files) and its GitHub cousin `io-coat3d-main`.

| Official AppLink | CoatLink |
| --- | --- |
| Renames objects to `__Name` on export | Never touches names |
| Replaces mesh data, UVs and materials by hidden rules | One rule: geometry in, everything else stays |
| Bakes textures and builds its own node groups | Nothing to do with textures |
| `3DC2Blender` helper directory, applink object pools, folder size limits | one fixed file name per direction |
| `extension.txt`, `preset.txt`, parameter files, a 12-folder state layout | `import.txt` + the model - nothing else |
| ~4200 lines across 7 files | ~1300 (Blender) + ~1000 (3D-Coat) lines, tests excluded |

Measured on 3D-Coat 2026:

* The job file is polled **in the exchange root only** - a copy inside the app
  folder is ignored, so it stays at the root.
* 3D-Coat registers **two** roots (it logs both on startup) and writes its exports
  into its own one, so the bridge watches the app folder of every root.
* 3D-Coat may also return a model into its own AppLink pool
  (`Documents/3DC2Blender/ApplinkObjects/`).  A file there is accepted only if it
  was written after our send; older ones are left alone.
* `extension.txt` in the app folder is ignored by 3D-Coat - it hands back what it
  wants to.  The bridge reads the format from the returned file.
* Anything 3D-Coat puts inside a `BlenderBridge` folder is ours; anything else is
  left alone, so the official AppLink can stay enabled.
* The Blender UI is drawn the same way as other top-bar extras: a panel with
  `bl_space_type = 'TOPBAR'`, `bl_region_type = 'HEADER'`, hooked into
  `TOPBAR_HT_upper_bar` and drawn only where `context.region.alignment == 'RIGHT'`.
* Nothing in the Blender scene is renamed, joined or deleted.

## Known limitations

Stated plainly, because a bridge that silently does half the job is worse than one
that says so:

* **The face count in 3D-Coat's sculpt tree was reported to climb while the
  CoatLink panel is open.**  The panel's redraw path is proven side-effect free
  (1000 simulated idle redraws, no host calls, no file access) and its statistics
  are manual (`RefreshStats`), but the live cause is **not** identified.  If you
  see it, close the panel; nothing else in the bridge depends on it.
* **Words, not identifiers.**  3D-Coat labels a panel control by its own name unless
  that name is translated, so the panel used to read `SendScope`, `ReductionPercent`,
  `RefreshStats`.  Every one of those now carries a translation (`Scope`, `Reduction
  percent`, `Refresh sizes`, ...), matching the Blender menu where the two sides mean
  the same thing.
* **Nothing is collapsed.**  The older builds hid the advanced half of both menus
  behind an `Advanced` fold-out.  That is gone on both sides; every control is drawn.
* **3D-Coat only reads the exchange folder while it is the active window.**  It logs
  `SetSystemPause: 1` when it loses focus and stops polling: a job file written while
  another application is in front simply sits there until you bring 3D-Coat forward.
  Practical consequence: after `Send`, switch to 3D-Coat (do not leave it minimised)
  and the model appears.  Nothing on the Blender side can change that.
* **A voxel import now asks to be voxelized.**  When the mode is `[vox]`, the
  after-import script that rides along in the job file is written with
  `VOXELIZE = True`, and it converts the objects of the imported group with
  `Volume.toVoxels()` before unparenting them - skipping anything already voxelized, so
  a second run is harmless, and leaving the packaging node alone.  This is the
  belt-and-braces half of the next point: it can only work if 3D-Coat runs the
  `[pythonfile ...]` line at all, which has not been observed on the build this was
  written against, so the panel's `To voxels` button is still the guaranteed path.
* **The import mode is asked for, not guaranteed.**  Blender writes the mode on the
  third line of `import.txt` (`[vox]` for a voxel import) and 3D-Coat's own log shows
  it reading that line - but models have still arrived in *surface* mode, as
  `S` in the Sculpt Tree (`Volume.isSurface()`, against `isVoxelized()`).  Two things
  are suspects and neither is confirmed: the `[SkipImport]` / `[SkipExport]` lines we
  add to make the trip silent (3D-Coat documents `[SkipImport]` as "skip the import
  dialog, default options will be used", and the official Blender AppLink never adds
  it), and the `[pythonfile ...]` line (documented for 3D-Coat 2025.12+, and the
  after-import unparenting it runs did not happen either).  Until that is settled the
  panel's **`To voxels`** button is the reliable way to get a voxel volume: it
  converts the current object, walks into packaging nodes rather than converting them,
  counts what was already voxel, and reports failures instead of throwing.
* **On the 3D-Coat side "whole scene" means 3D-Coat's own export,** so what it
  covers is 3D-Coat's decision (it can include hidden volumes).  The panel prints
  that under the droplist instead of pretending otherwise.  Sending only the
  *visible* tree objects from 3D-Coat would need one of 3D-Coat's own commands -
  `Export Selected Objects` ("selected Sculpt Tree layers") or the
  decimate-and-export-all-visible-volumes action - and neither has been verified
  here, so nothing was guessed into the release.
* **Unparenting the imported objects relies on `[pythonfile …]`,** which the
  AppLink documentation says needs 3D-Coat 2025.12 or newer; on an older build the
  job file keeps the line, 3D-Coat ignores it, and the model arrives under its
  `bridge` parent as before.  The index 3D-Coat wants for "append to the root" is
  not documented either, so both spellings are tried and the result is checked with
  `parent()` instead of assumed.
* **The selected-node export is new and has not been through a live round trip
  yet.**  The API calls are the documented ones (`Scene.current()`, `fromVolume`,
  `fromReducedVolume`, `Mesh.Write`), the OBJ it produces is validated line by line,
  and everything that could go wrong has a test - but grouping, positions and units
  after a real send still have to be confirmed on a live 3D-Coat.
* **The reduction percentage is not verified end to end.**  The panel writes the
  same slider 3D-Coat's own scripts write, and that field belongs to the "decimate
  to Retopo" flow in 3D-Coat's sources; whether the AppLink export honours it on
  every path is untested.  The panel labels its number an estimate.
* **Receipts only cover imports made through the bridge.**  If 3D-Coat's own
  AppLink auto-imports a model, no receipt is written, and the bridge does not
  pretend otherwise.
* **Windows-oriented.**  Both installers and the test scripts assume Windows paths
  (`cygpath`, `%APPDATA%`).  The Blender add-on itself is OS-independent; the
  3D-Coat half is plain Python and only its installer is Windows-specific.
* **Installing through 3D-Coat's own extension system** (`.3dcpack`, "Install
  Extension" in 3D-Coat) would need no console, no double-click and no unzip at
  all.  It is not shipped because the package layout for scripts and menu entries
  is not documented anywhere we could verify - 3D-Coat's own builder would have to
  produce a reference package first.  Downloading `CoatLink-Setup.py` is the
  closest thing today.
* **Subtree-scoped export** (only the current node plus its children, instead of
  the whole sculpt tree) exists on the `parked/subtree-scoped-panel` branch.  It is
  **not** in the released code, because the grouping, positions and units of its
  output were never verified on a live round trip.

## Tests

```bash
tests/run_tests.sh                        # Blender side: main suite, every regression
                                          # script and both installers, headless
coat_side/tests/run_tests.sh              # 3D-Coat side: API stubs, logic, tools, probe, install
tests/test_coat_export.sh path/to/real-export.obj   # return leg on a file 3D-Coat really wrote
tests/live_roundtrip.sh 900               # the real 3D-Coat, waits for your click
```

No 3D-Coat and no Blender GUI are needed for the suites: the Blender tests drive
throwaway script and exchange folders, and the 3D-Coat tests run against a
stand-in `coat` module on 3D-Coat's own Python.  The scripts pick the newest
Blender build and 3D-Coat's bundled Python automatically; set `BLENDER=`,
`COAT_PYTHON=`, `COAT_DIR=` or pass a path to override.

Current counts: Blender main suite **113/113**, plus the regression scripts and
both installer smoke tests; 3D-Coat logic **103/103**, tools **29/29**, installer
**29/29**, plus the API stub check, the idle-redraw check, the probe dry run and
the install smoke tests.

## License

GPL-3.0-or-later, see [LICENSE](LICENSE).  Copyright (C) 2026 VictoryLuode.
