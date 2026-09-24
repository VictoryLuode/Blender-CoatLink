# CoatLink

**A small, predictable two-way model bridge between Blender and 3D-Coat.** Models only: no
baking, no texture nodes, no scene surgery.

<img src="docs/images/blender-menu.png" width="300" alt="The CoatLink menu, opened from the single CoatLink button in Blender's top bar">
<img src="docs/images/3dcoat-panel.jpg" width="620" alt="The CoatLink panel in 3D-Coat: scope, Send/Pull, To voxels, send options, setup and status">

<sub>The CoatLink menu in Blender's top bar &nbsp;·&nbsp; the CoatLink panel in 3D-Coat.  Both carry
the same sections in the same order.</sub>

* one **CoatLink** button in Blender's top bar and one panel in 3D-Coat - both carry the same
  sections in the same order with the same words
* `Send` / `Pull` in both directions.  Objects keep their names, their materials and their
  place in the outliner; nothing in your scene is renamed, joined or deleted
* units and axes are read from 3D-Coat itself, so 2 m in Blender is 2 m in 3D-Coat
* optional `Send to origin`: hand the model to 3D-Coat's world origin instead of from where it
  sits in the scene - and take it back to the same place when it returns
* optional voxel remesh on send (over the exported copy only), and one-click `To voxels` in
  3D-Coat that converts what the Sculpt Tree is showing

## Install

### Blender - no commands at all

1. Download **`CoatLink-<version>.zip`** from the [latest release](../../releases/latest).
2. In Blender: **Edit > Preferences > Add-ons > ▾ (top right) > Install from Disk…** and pick
   that zip (Blender 4.2 and newer).
3. Enable **CoatLink** in the add-on list, then press **Detect** in its menu.

*Upgrading from an older build?*  Everything used to be called `CoatBridge` / `coat_bridge`:
the add-on's folder, the 3D-Coat scripts folder, the exchange folder, the log, and the tool
and menu ids.  Both sides clean up after themselves — `install.sh` / `install.ps1` move
the old `coat_bridge` add-on folder out of Blender's way, and the 3D-Coat installer (or the
extension itself, the next time 3D-Coat starts) moves `Scripts\CoatBridge` to
`CoatBridge.removed` and deletes the old menu files — so the only
thing left to do is enable **CoatLink** once and press **Detect**.  Links between your
objects and the models they came from survive; the add-on's own settings go back to their
defaults.

### 3D-Coat - install it from inside 3D-Coat

Download **`CoatLink-<version>.3dcpack`** from the latest release, then in 3D-Coat open
**Scripts > Install Extension** and pick that file.  It is 3D-Coat's own package format: nothing
to unzip, no console, no path to edit - and no script Windows has to be persuaded to run.

3D-Coat then lists it under **Windows > Panels > Extensions**.  Tick **CoatLink** there once and
**restart** 3D-Coat.  (3D-Coat loads an extension by the name listed in its `cExtensions/startup.txt`
and only its own install can add that line, so the tick is needed exactly once.)

On that first start the extension puts its menu in place with **your** paths - the entries 3D-Coat
reads carry absolute paths, so they cannot travel inside the package - and it moves whatever an
older build left behind out of the way.  Look for **Scripts > CoatLink**, and for the three tool
buttons at the end of the Voxels and Paint tool lists.

Nothing is written outside 3D-Coat's user folder, and the tool buttons take 3D-Coat's default icon:
deliberate, because a button icon would mean writing into `C:\Program Files`.

Prefer a command, or working from a checkout?  `install.cmd`, `./install.sh`
(git-bash/MSYS/WSL) and `.\install.ps1` (PowerShell, both halves) run the same installer and put
the 3D-Coat half exactly where the package would.  Both folders are worked out on the spot,
wherever 3D-Coat is: the program folder from the uninstall entries Windows keeps, the data folder
by following **your** Documents folder - which is where it is *not* once Documents is redirected to
OneDrive.  3D-Coat from a folder of your own, on any drive, works too.

If Windows refuses to run scripts, start the PowerShell one explicitly - normal and safe for a
script you just downloaded and read:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
```

**Every door ends in the same place** (`coat_side/CoatLinkInstall.py`) - which is also where the
`.3dcpack` puts it.  A test installs with each door into a throwaway tree and compares the results
file by file, so they cannot drift apart.

Then **restart 3D-Coat** and look for **Scripts > CoatLink**.  Three tool buttons also appear
at the end of the Sculpt and Paint tool lists.  To take it all back out:
`install.cmd --uninstall` (or `.\install.ps1 -Uninstall`, `./install.sh --uninstall`,
`python CoatLinkInstall.py --uninstall`) - it removes its own files and nothing else.

Copying the files by hand, explicit install paths and the XML 3D-Coat needs:
[docs/install.md](docs/install.md).

## Use

1. `Scope` picks the selected object (default) or every visible one.  `Import as` picks how
   3D-Coat opens it - `Sculpt Object (voxel)` by default.  `Remesh on send` can voxel-remesh
   the exported copy only; the scene, the names and your own modifiers stay as they are.
2. **`Send`**.  If 3D-Coat is not running, the job waits in the exchange folder until it is -
   `Start 3D-Coat` is right there in the menu.
3. Work in 3D-Coat, then **`File > Export To > CoatLinkBridge`** (or `Bring object back`).
   With **Auto receive** on, the model is imported within ~2 s and merged into the object it
   came from: same name, same materials, same place in the outliner, new geometry.  **Replace in
   place** (on by default) is what does that: switched off, a return arrives as an object of its
   own and nothing already in the scene is written over.  **Shaders as materials** (also on by
   default) gives each returning object a material named after the 3D-Coat shader it was sent
   with - a sculpt shader is display shading that 3D-Coat's exporters never write, so the
   assignment is carried beside the model instead.  Where the shader library holds two presets
   of one name the material is named after the preset's place in it (`Metal/Gold2`), so the two
   never end up as one material.  The values come from the shader preset
   itself; the look it gives in 3D-Coat cannot be copied.

From the 3D-Coat side, `Send` hands over **the node selected in the Sculpt Tree plus its
children** (`Scope: whole scene` uses 3D-Coat's own export instead - the only route that can
carry textures), and `To voxels` converts everything the tree is showing.  It does that by
pressing 3D-Coat's own S/V badge - the conversion you would do by hand - and accepts the
dialog for you, so a scene converts from one click.

The menu's four sections - `Send options`, `Return`, `Setup`, `Status` - are fold-out headers,
the way Blender's own popovers group things.  `Setup` starts folded, everything else open.

What every entry does, on both sides: [docs/menus.md](docs/menus.md).

## How it works

One exchange folder, one file layout, one vocabulary:

```
<3D-Coat exchange root>/
    import.txt                 the job: what to load, where to return, how to open it
    CoatLinkBridge/            our folder - everything else lives in here
        run.txt                empty marker: makes the folder a File > Export To target
        bridge.obj             the model, both directions (one axis rule, one unit rule)
        export.txt             written by 3D-Coat when it hands a model back
        pull-history.json      what was already imported, so a restart does not repeat it
    CoatLink_AfterImport.py    run after the import: drops 3D-Coat's wrapper node
```

The export target is `CoatLinkBridge`, deliberately **not** the add-on's own name: 3D-Coat's
Scripts menu entry for this extension is `CoatLink`, and two different things answering to one
name was the confusing part.  A build from before the rename left its folder behind as
`CoatLink/`; it is not touched, but its marker goes so the old name drops out of the menu, and
anything 3D-Coat handed back into it is still pulled.

Nothing else is written, and only files inside one of our own folders (`CoatLinkBridge`, plus
the pre-rename `CoatLink`) are ever touched -
with one exception: the job file `import.txt`.  3D-Coat polls that file only at the exchange
root, and the official Blender AppLink queues its jobs in the very same file (its own source
writes the model path first).  The two add-ons can therefore stay enabled side by side, but
not send at the same instant: whichever writes last owns the queue.  CoatLink says so in the
log when it replaces a job that was not its own, and it never imports or deletes a job
pointing outside its own folder.  Measurements, the two exchange roots and the differences
from the official AppLink: [docs/protocol.md](docs/protocol.md).

## Requirements

Blender 4.2+ (developed on 5.2 LTS) · 3D-Coat **2025.12 or newer** (tested against 2025 and
2026) · **Windows** - the installers, the exchange layout and both test suites assume it.
The unparenting step after an import - 3D-Coat runs the script the add-on drops beside the job -
needs 3D-Coat 2025.12, so older builds are not supported; 3D-Coat 2026 keeps its own Python and
user data in versioned folders and both halves look those up rather than assuming a name.
3D-Coat ships the Python its half needs, so nothing else has to be installed.

## Known limitations

Stated plainly, because a bridge that quietly does half the job is worse than one that says
so:

* **The `[vox]` import mode is asked for, not guaranteed.**  3D-Coat's own log shows it
  reading that line, but on the build this was developed against the model still arrives in
  *surface* mode (S in the Sculpt Tree).  `To voxels` in the panel is the reliable route; the
  cause has not been identified.
* **No live round trip has been run on this release.**  Both suites run headless against a
  stand-in host; `tests/live_roundtrip.sh` exists for a real one and records the exact job
  file it wrote, which is the evidence the earlier attempts were missing.
* **The reduction percentage is an estimate**, and `To voxels` accepts the conversion
  dialog's defaults - so one object cannot be skipped mid-run.
* **The tool buttons have no icon of their own**: a button icon has to be written into
  3D-Coat's program folder, which needs administrator rights, so they use 3D-Coat's default.
* **3D-Coat's "whole scene" export is 3D-Coat's own**, so what it covers is its decision.

The full list, including what is deliberately not shipped:
[docs/limitations.md](docs/limitations.md).

## Tests

```bash
tests/run_tests.sh                                   # Blender side, headless
coat_side/tests/run_tests.sh                         # 3D-Coat side, stand-in host
tests/test_coat_export.sh path/to/real-export.obj     # the return leg on a file 3D-Coat wrote
tests/live_roundtrip.sh 900                           # the real thing: both apps open
```

No 3D-Coat and no Blender GUI are needed for the suites: the Blender tests drive throwaway
script and exchange folders, and the 3D-Coat tests run against a stand-in `coat` module on
3D-Coat's own Python.  The scripts pick the newest Blender build and 3D-Coat's bundled Python
themselves; `BLENDER=`, `COAT_PYTHON=` and `COAT_DIR=` override.

Current counts: Blender main suite **220/220** plus every regression script and both installer
smoke tests; 3D-Coat logic **166/166**, tools **29/29**, tree report **12/12**, installer
checks, API stub check, idle-redraw check and probe dry run.

## License

GPL-3.0-or-later, see [LICENSE](LICENSE).  Copyright (C) 2026 VictoryLuode.
