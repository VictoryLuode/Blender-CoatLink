# The exchange, in full

## The file layout

```
Documents/AppLinks/3D-Coat/Exchange/     <- the job file goes here (3D-Coat polls the root)
    import.txt                               what to load, where to return, how to open it
    CoatLinkBridge/                     <- our folder; everything else lives in here
        run.txt                                 empty marker: makes the folder appear in File > Export To
        bridge.obj                              the model, both ways: every send and every return overwrites it
        export.txt                              3D-Coat writes it when it hands a model back
        shaders.json                            which shader each exported node carries, written with the model
        paint.json                              the painting room's own object, material and texture-set names,
                                                written with a paint export (the model itself carries none of them)
        pull-history.json                       what we already imported, so a restart does not re-import it
    CoatLink_AfterImport.py                  the script that unparents the import: dropped in by the add-on
    CoatLink_AfterImport.py.ran              its own note that it started: dated, written before anything else
    import.py                                the file 3D-Coat runs itself after an import: runs the script above
    import.py.ran                            and the note that it got that far

Documents/3DCoat/Exchange/               <- 3D-Coat's own root: watched, never written to
    CoatLinkBridge/                     a return from an older session can still be sitting here
```

The folder name **is** the name in 3D-Coat's `File > Export To` list, and the entry comes from
the `run.txt` marker inside it rather than from the folder (measured: a folder renamed to
`*.removed` while keeping its marker is still listed, and `Documents/3DCoat/Exchange/Blender`
without one is not).  That is why the rename from `CoatLink` to `CoatLinkBridge` had to be two
steps - publish the new name, delete the old marker - and why the target is not simply called
`CoatLink`: 3D-Coat's Scripts menu entry for this extension is `CoatLink`, and one name for two
different rows is the thing being fixed.  The old folder is left in place with its files: a
`export.txt` written before the rename still names a model that is still there, and it is still
read as ours.

Both halves put `Documents/AppLinks/3D-Coat/Exchange` first (the Blender add-on in
`applink._candidate_exchange_folders`, the 3D-Coat script in `CoatLinkLib.candidate_roots`), and that
is measured, not preferred: 3D-Coat's engine picks a job file up **only** from that root - a job left
in `Documents/3DCoat/Exchange` sat untouched for two minutes.  With one shared primary a return lands
on the same `bridge.obj` the send wrote, so there is one file to look at.  When the two sides
disagreed, a trip left half its files in each folder and the untouched half looked like "3D-Coat never
exported".

The add-on writes `import.txt` at the root, `bridge.obj`, `CoatLink_AfterImport.py` (the script
`import.txt` points at) and an empty `run.txt`; the two markers are state.  That is the whole
design.

`shaders.json` is the one file that exists only because of a hole in 3D-Coat's export: a sculpt
shader is display shading, and its OBJ writer emits `usemtl ` and `newmtl ` with nothing after
them, so a returned model arrives carrying one nameless material no matter how many shaders the
scene used.  The 3D-Coat half therefore reads each exported node's shader (make it current, then
`CMD.GetCurVolumeShader`), copies that shader preset's stored parameters along, and writes the
map beside the model; the Blender half uses it to name and assign a material per shader.  It is
written after every export and **deleted** when nothing could be read, and the add-on deletes a
stale one when it sends, so a map can never describe a model it did not come with.

`paint.json` exists for the same reason and a second one.  `Export type: paint object` hands over
the painting room's mesh **with its textures**, and 3D-Coat's exporter names nothing in the `.mtl`
there either, so the material a returning model should wear is not in the file.  The 3D-Coat half
therefore reads the painting room's own lists - `Scene.PaintObjectsCount` / `PaintObjectName`,
`PaintMaterialCount` / `PaintMaterialName`, `PaintUVSetsCount` / `PaintUVSetName` - and writes
them beside the model, and the Blender half builds one material per named set, wiring the colour
texture into **Base Color** and a normal map through a **Normal Map** node, each read in the colour
space its slot needs (`sRGB` for colour, `Non-Color` for normal).  Two things the record does *not*
carry, because 3D-Coat's API does not expose them: **which object wears which material** (matched
by name where the names line up, otherwise by the order 3D-Coat lists them) and **which texture file
is which** (decided from the file names - `normal`/`nrm`/`bump` for the normal map, the material's
name or `color`/`albedo` otherwise).  Both decisions are written to the log, so a wrong guess can be
seen rather than guessed at.  A `paint.json` describing nothing is removed, like the shader map.

**What `CMD.GetCurVolumeShader` answers with** (measured on 3D-Coat 2025): `PbrShaders/Gold2/mcubes`
- the shader's place in 3D-Coat's own library.  Its last part names the shader *file* inside the
preset folder (measured across the whole library: every preset carries `mcubes.glsl`), so the
preset is the part before it, and the map carries that as `preset`.  The presets themselves live
in the **installation** (`<install>/UserPrefs/Shaders/PbrShaders/#Metal/Gold2`), not in the user
data folder, so the lookup searches the user's copy first and then the program folder, which is
found by looking on the drives rather than by assuming `Program Files`.  Shaders are filed in
families, so the whole `UserPrefs/Shaders` folder is searched - the PBR family, `NGPreview` and
`CurrentMcubes` all resolve - and two string forms come back: a path inside the library
(`PbrShaders/Gold2/mcubes`) and a name relative to it (`#Metal/Aluminum`).  Both are tried
exactly, with and without the family in front, before falling back to matching a preset by
name; only a folder carrying a `ShaderParams.xml` counts as one.

The material's name is the preset's own name - `Gold2`, not a path - with a qualification when
the library holds **two presets of that name**: measured, four of the shipped names are used
twice (`Gold2`, `Copper`, `Skin`, loose and categorised; `Default`, in two families), and those
are different presets with different stored values, so the second one is named by its place in
the library (`Metal/Gold2`, `NGPreview/Default`) rather than quietly sharing one material.  When
no folder can be worked out, the name is read out of the string instead: the family and the
shader file are dropped, which leaves the preset's name.  The parameters are the preset's own
stored values - `Color` is 8 hex digits, alpha first, and it is carried whether or not the
preset's *look* comes from a texture: measured across the shipped library, 77 of the 102 textured
presets store a real tone (Copper `FF8E4E`, Gold `DFB331`, Clay `9F8272`), and only the glass and
water family stores the near-black placeholder its look ignores.  The flag (`color_from_texture`)
is still written, so the material records where its look came from; no texture travels either way,
and the base colour is the value the material is adjusted from by hand.  Of the ids the presets
store, three are read: `Color` (117 of the 154 presets measured, in the shipped library and the
downloaded ones alike), `Metalness` (106) plus its other spelling `Metallness` (7), and `Opacity`
(149) as alpha.  Every stored value is kept in the material's own record whether it is used or not,
so an id only some other shader pack uses is a one-line mapping away.  A shader nothing
in the library matches costs its parameters, never the assignment.

`bridge.obj` is the model in **both** directions, which is what leaves exactly one axis rule
and one unit rule to keep straight.  An `Export` covers the Sculpt Tree's **own selection** - one
node or several, each with its children (`Mesh.fromVolume(…, with_subtree, all_selected)`, the
second flag set when more than one node is selected) - so nothing else in the scene can leave
by accident.

The file's groups are the objects, with one exception each way.  A group that carries no faces is
not an object: it is the node 3D-Coat wrapped the last import in, and it is dropped from the file
(a face-less group is what an importer may turn into an empty object, and on Blender 5.2 it is
skipped instead - measured).  A group named after the exchange model itself (`bridge`) is the wrap
3D-Coat puts around a model Blender sent, and it is **not sent as an object** at all - its children
are the objects, and if it is somehow the only group with geometry it stays, so a send can never
come back empty.  A group that *owns* faces but lost its group is a merge: the mesh is asked which
object each face belongs to (`Mesh.getFaceObject`) and the export is refused rather than handed
over as a model whose objects nobody can name.

Both sides also keep **one log and one state file**, in 3D-Coat's own data folder
(`Documents/3DCoat/CoatLink.log` and `CoatLink.json`): the log is what the 3D-Coat panel
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
  0 means auto.  A machine can have an older 3D-Coat data folder beside the current one, so the
  **newest** state file is the one read: the running half rewrites its own on every action, and a
  stale file is a scene that is no longer there.  When nothing has reported the units yet, no
  conversion is applied and the status line says `units unknown` - a silent 1:1 is how a model
  arrives a hundred times out.
* **Encoding.**  The files 3D-Coat writes (`export.txt`, the OBJ it hands back) are read in
  whatever encoding they turn out to be in - UTF-8, UTF-16 with or without a byte-order mark, or
  the machine's own code page - worked out from the bytes rather than assumed.  It matters twice
  over for the OBJ, which is rewritten once the packaging group is taken out of it: read as UTF-8
  with the unreadable bytes replaced, an object name outside ASCII would be quietly written back
  damaged.  Everything the bridge itself writes is UTF-8, and every JSON side file is pure ASCII
  (`json` escapes by default), so those reads never have to guess.
* **Axis.**  3D-Coat's `SwapYZ` ("swap the Y and Z scene axes", for Z-up applications) is
  detected the same way, and one rule covers both directions - which is what keeps them from
  drifting apart.  `Axis` can force either convention.  Formats that carry their own axis
  (FBX) are left alone.
* **Reduction.**  A percentage in the 3D-Coat panel goes into 3D-Coat's own decimation slider
  (`$DecimationParams::ReductionPercent`) and the dialog's OK is pressed for you, so its export
  dialog is never seen; the selected-node route passes it to
  `fromReducedVolume(volume, reduction_percent, …)`, whose parameter carries that name.  The
  percentage means *removed*, not *kept*.
* **Textures.**  No switch.  The sculpt export has no UVs for a texture to land on and
  nothing on the Blender side read the files, so a control for them only made the exchange
  folder heavier.  Every export still answers 3D-Coat's own `$ExportOpt::ExportTextures`
  explicitly - to off - because leaving it alone would hand the result over to whatever
  state that dialog was left in.  Paint objects come with their textures by their own route.
* **No leftover parent node.**  3D-Coat wraps an imported file in a node named after it
  (`bridge.obj` → "bridge"), which Blender has no equivalent of.  The unparenting is handed
  over twice, because one handover is not enough: the job file names the script with
  `[pythonfile CoatLink_AfterImport.py]`, and the same script is dropped in beside the job as
  `import.py` - the file 3D-Coat runs by itself when it finds it there, and the only one of
  the two that actually runs (on 2025.17 the directive is read - 3D-Coat prints it in its log
  - but never executed).  Either way the objects move up to the sculpt root and the empty
  wrapper is deleted - only that wrapper, and only if it belongs to this model.  A Pull made
  from the panel does the same in code.  The sculpt tree then matches the Blender outliner.
* **Selection, not the scene.**  `Export` exports `Scene.current()` with
  `with_subtree=True, all_selected=False`, so sculpting in progress cannot leak into Blender,
  and a return that loses its object groups is refused rather than merged.  When the sculpt tree's
  own selection is what drove the send, the status line names how many nodes went; if 3D-Coat's
  extraction merges them into a single object, it says that too - a merged model and a send that
  lost objects look identical otherwise.  The group check that guards this asks the mesh which
  object each face belongs to, and the only call for that is one face at a time, so the packaging
  node - the usual reason for the question - is ruled out first and the rest stops at the first
  offending face.
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
* Anything 3D-Coat puts inside a `CoatLink` folder is ours; anything else is left alone,
  so the official AppLink can stay enabled.
* The Blender UI is drawn the way other top-bar extras are: a panel with
  `bl_space_type = 'TOPBAR'`, `bl_region_type = 'HEADER'`, hooked into `TOPBAR_HT_upper_bar`
  and drawn only where `context.region.alignment == 'RIGHT'`.
* 3D-Coat's tree rows carry an S/V badge (`$VoxTreeBranch.VoxSurf.<object>`) whose tooltip is
  "Press this button to transform surface to voxel representation" - its own conversion, which
  is what `Selected To Voxel` presses.
* `import.txt` has no import-side field mechanism: the documented extra commands
  (`[SkipImport]`, `[SkipExport]`, `[TexOutput]`, `[Option=…]`, `[field …]`, `[click …]`) are
  all for the export side, and there is no `ImportOpt::` field namespace.  Voxelizing an import
  therefore has to happen after the import.
* Nothing in the Blender scene is renamed, joined or deleted.
