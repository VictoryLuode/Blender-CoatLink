# The exchange, in full

## The file layout

```
Documents/AppLinks/3D-Coat/Exchange/     <- the job file goes here (3D-Coat polls the root)
    import.txt                               what to load, where to return, how to open it
    BlenderBridge/                           <- our folder; everything else lives in here
        run.txt                                 empty marker: makes the folder appear in File > Export To
        bridge.obj                              the model, both ways: every send and every return overwrites it
        export.txt                              3D-Coat writes it when it hands a model back
        pull-history.json                       what we already imported, so a restart does not re-import it
    CoatLink_AfterImport.py                  run by 3D-Coat after the import: unparents the objects
    CoatLink_AfterImport.py.ran              the helper's own note that it ran: dated, written first

Documents/3DCoat/Exchange/               <- 3D-Coat's own root: watched, never written to
    BlenderBridge/                           a return from an older session can still be sitting here
```

Both halves put `Documents/AppLinks/3D-Coat/Exchange` first (the Blender add-on in
`applink._candidate_exchange_folders`, the 3D-Coat script in `CoatBridgeLib.candidate_roots`), and that
is measured, not preferred: 3D-Coat's engine picks a job file up **only** from that root - a job left
in `Documents/3DCoat/Exchange` sat untouched for two minutes.  With one shared primary a return lands
on the same `bridge.obj` the send wrote, so there is one file to look at.  When the two sides
disagreed, a trip left half its files in each folder and the untouched half looked like "3D-Coat never
exported".

The add-on writes `import.txt` at the root, `bridge.obj`, `CoatLink_AfterImport.py` (the script
`import.txt` points at) and an empty `run.txt`; the two markers are state.  That is the whole
design.

`bridge.obj` is the model in **both** directions, which is what leaves exactly one axis rule
and one unit rule to keep straight.

Both sides also keep **one log and one state file**, in 3D-Coat's own data folder
(`Documents/3DCoat/CoatBridge.log` and `CoatBridge.json`): the log is what the 3D-Coat panel
shows, and the file is where the axis and unit records below are read from.  Each side works
that folder out from its own location instead of guessing at `Documents`, so a redirected
Documents (OneDrive) or a `COAT_FILES_PATH` install moves both together.  A side that lands one
folder lower - 3D-Coat's own `UserPrefs` - splits one trip's evidence across two files *and*
leaves the other side reading a stale axis/unit record, which is exactly what the old split did.

## What the two sides quietly handle for you

* **Units.**  3D-Coat's scene unit is read from its own state file (`Scene.GetSceneUnits()`:
  centimetres on a default install) and applied on the way out, divided back on the way in, so
  2 m in Blender is 2 m in 3D-Coat.  A size difference that is *not* a clean unit factor is
  reported and left alone, never stretched - your sculpting is safe.  `Scale` forces a factor;
  0 means auto.
* **Axis.**  3D-Coat's `SwapYZ` ("swap the Y and Z scene axes", for Z-up applications) is
  detected the same way, and one rule covers both directions - which is what keeps them from
  drifting apart.  `Axis` can force either convention.  Formats that carry their own axis
  (FBX) are left alone.
* **Reduction.**  A percentage in the 3D-Coat panel goes into 3D-Coat's own decimation slider
  (`$DecimationParams::ReductionPercent`) and the dialog's OK is pressed for you, so its export
  dialog is never seen; the selected-node route passes it to
  `fromReducedVolume(volume, reduction_percent, …)`, whose parameter carries that name.  The
  percentage means *removed*, not *kept*.
* **Textures.**  A droplist: let 3D-Coat decide, force on, force off.
* **No leftover parent node.**  3D-Coat wraps an imported file in a node named after it
  (`bridge.obj` → "bridge"), which Blender has no equivalent of.  The job file carries
  `[pythonfile CoatLink_AfterImport.py]`, so 3D-Coat runs a short script right after the
  import: the objects move up to the sculpt root and the empty wrapper is deleted - only that
  wrapper, and only if it belongs to this model.  A Pull made from the panel does the same in
  code.  The sculpt tree then matches the Blender outliner.
* **Selection, not the scene.**  `Send` exports `Scene.current()` with
  `with_subtree=True, all_selected=False`, so sculpting in progress cannot leak into Blender,
  and a return that loses its object groups is refused rather than merged.
* **Names.**  Objects keep their names in both directions.  Groups that come back are matched
  to the objects they came from and updated in place; renamed objects are still found;
  unrelated same-name objects are never overwritten.
* **Receipts.**  Both sides write down what the other received, so the status line can say
  "3D-Coat received: …".  A receipt only exists for an import made through the bridge - 3D-Coat
  auto-importing on its own writes none, and the bridge does not pretend otherwise.

## Design notes, and what was measured

Reference implementations read while writing this: the official `io_coat3D` AppLink that ships
inside 3D-Coat (`data/ToolsPresets/InstallAppLinks/Blender4x/`, ~4200 lines across 7 files)
and its GitHub cousin `io-coat3d-main`.

| Official AppLink | CoatLink |
| --- | --- |
| Renames objects to `__Name` on export | Never touches names |
| Replaces mesh data, UVs and materials by hidden rules | One rule: geometry in, everything else stays |
| Bakes textures and builds its own node groups | Nothing to do with textures |
| `3DC2Blender` helper directory, applink object pools, folder size limits | one fixed file name per direction |
| `extension.txt`, `preset.txt`, parameter files, a 12-folder state layout | `import.txt` + the model - nothing else |
| ~4200 lines across 7 files | ~1300 (Blender) + ~1100 (3D-Coat) lines, tests excluded |

Measured on 3D-Coat 2025/2026:

* The job file is polled **in the exchange root only** - a copy inside the app folder is
  ignored, so it stays at the root.
* 3D-Coat registers **two** roots (it logs both on startup) and writes its exports into its own
  one, so the bridge watches the app folder of every root.
* 3D-Coat may also return a model into its own AppLink pool
  (`Documents/3DC2Blender/ApplinkObjects/`).  A file there is accepted only if it was written
  after our send; older ones are left alone.
* `extension.txt` in the app folder is ignored by 3D-Coat - it hands back what it wants to.
  The bridge reads the format from the returned file.
* Anything 3D-Coat puts inside a `BlenderBridge` folder is ours; anything else is left alone,
  so the official AppLink can stay enabled.
* The Blender UI is drawn the way other top-bar extras are: a panel with
  `bl_space_type = 'TOPBAR'`, `bl_region_type = 'HEADER'`, hooked into `TOPBAR_HT_upper_bar`
  and drawn only where `context.region.alignment == 'RIGHT'`.
* 3D-Coat's tree rows carry an S/V badge (`$VoxTreeBranch.VoxSurf.<object>`) whose tooltip is
  "Press this button to transform surface to voxel representation" - its own conversion, which
  is what `To voxels` presses.
* `import.txt` has no import-side field mechanism: the documented extra commands
  (`[SkipImport]`, `[SkipExport]`, `[TexOutput]`, `[Option=…]`, `[field …]`, `[click …]`) are
  all for the export side, and there is no `ImportOpt::` field namespace.  Voxelizing an import
  therefore has to happen after the import.
* Nothing in the Blender scene is renamed, joined or deleted.
