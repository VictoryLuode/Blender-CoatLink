# Known limitations, in full

Stated plainly, because a bridge that silently does half the job is worse than one that says
so.  The short version is on the [README](../README.md).

## Verified incompletely or not at all

* **`Export type: paint object` has never been run on a real pair.**  The 3D-Coat half's
  panel row and export call are unit-tested against the fake 3D-Coat only, and the Blender
  half's material build is unit-tested against a fabricated `paint.json` and two 1×1 PNGs.
  What is *not* measured, and cannot be until someone exports a real paint room: where
  `PathForTextures` actually puts the files and what it names them, whether 3D-Coat exports
  only the current paint object or all of them, whether the OBJ then carries UVs, and whether
  its texture names are the ones this side matches on.  Until that run, treat the texture
  wiring as an expectation with a log line, not a promise.
* **The paint texture split is made from file names** (`normal`/`nrm`/`bump` for a normal
  map, the material's name or `color`/`albedo` otherwise, and "the only file left" as a
  fallback) because the export names nothing and 3D-Coat's API does not expose the pairing of
  object to material either.  Both choices go in the log; neither is guaranteed.

* **A live round trip has been run once**, on Blender 5.2 and 3D-Coat 2025.17 (2026-09-23).
  3D-Coat's own log shows it reading the job file this side wrote - `[vox]`, `[SkipImport]`,
  `[SkipExport]`, `[pythonfile …]` - and importing the OBJ (its `Model info:` line counted the
  objects), and the return leg left a dated receipt naming the object it pulled.  What that
  does **not** cover: grouping, positions, scale and axis on real geometry (including
  `Send to origin`, whose file is checked here but which has never been watched landing on the
  origin in a running 3D-Coat), a second machine,
  a second 3D-Coat build, or the selected-node export.  **Several nodes selected in the Sculpt
  Tree go out as one model** (the extraction's `all_selected` flag, documented in 3D-Coat's own
  `CoreAPI.h`); that path is unit-tested against the fake 3D-Coat only - whether the live build
  brings each selected node's **children** along as well is expected, not measured.
  `tests/live_roundtrip.sh` runs the
  real thing (both applications open) and records the add-on version and the exact
  `import.txt` it wrote - until it has been run, "works on a live pair" is an expectation,
  not a fact.
* **The `[vox]` import mode is asked for, not guaranteed.**  The mode line is written and
  3D-Coat's own log shows it being read, but on the build this was developed against the model
  still arrives in *surface* mode (`S` in the Sculpt Tree, `Volume.isSurface()` against
  `isVoxelized()`).  Two suspects, neither confirmed: the `[SkipImport]` / `[SkipExport]` lines
  that make the trip silent (3D-Coat documents `[SkipImport]` as "skip the import dialog,
  default options will be used", and the official Blender AppLink never adds it), and the
  `[pythonfile …]` line.  **`Selected To Voxel` in the panel is the reliable route** - see below.
* **`[pythonfile …]` is not executed on 2025.17, and the unparenting no longer depends on it.**
  A live trip on 2026-09-23 (Blender 5.2, 3D-Coat 2025.17) settled it: the job file carried the
  line, 3D-Coat's own log printed it as part of the job, and nothing ran - no `PyImportFile`
  line for the helper, no marker, no log line.  The unparenting now rides on `import.py`, which
  is what that log shows being run and what the shipped AppLinks spec describes: a file with
  that name beside the job is executed by 3D-Coat itself, and deleted with the job when the
  import is through.  The `[pythonfile …]` line is kept as a spare for builds that do run it.
  **Not yet confirmed on a live pair:** that 3D-Coat runs *our* `import.py` (it also has a file
  of that name of its own), so the panel reports the step as evidence, not as a guarantee.  Two
  dated notes are accepted as that evidence - the job's `import.py.ran` and the helper's
  `CoatLink_AfterImport.py.ran` - and a note says the step started, never that the voxel
  conversion or the unparenting then succeeded.
* **A returned model can arrive in pieces.**  3D-Coat's own AppLink export writes the model and
  the signal itself, and the signal can land while the file is still growing: the import then
  finds no objects.  The pull now waits a moment for the size and mtime to stop changing, calls
  such a failure what it is (`the file was still being written`), retries on the next watcher
  tick, and writes the traceback to the log once per file version instead of once per tick -
  one trip used to leave 50 identical tracebacks and bury the one that mattered.  A file that
  never settles is still imported, so waiting cannot lose a return.
* **The selected-node export has not been through a live round trip.**  The API calls are the
  documented ones (`Scene.current()`, `fromVolume`, `fromReducedVolume`, `Mesh.Write`), the OBJ
  it produces is validated line by line, and everything that could go wrong has a test - but
  grouping, positions and units after a real send still have to be confirmed.
* **The reduction percentage is not verified end to end.**  The panel writes the same slider
  3D-Coat's own scripts write, and that field belongs to the "decimate to Retopo" flow in
  3D-Coat's sources; whether every AppLink export path honours it is untested.  The panel calls
  its number an estimate.
* **`Selected To Voxel` accepts the conversion dialog's defaults**, because it presses that dialog's OK
  itself (otherwise every object would need a click).  Consequence: a single object cannot be
  skipped mid-run - switch it off in the tree first, and it will be left alone.
* **The face count in 3D-Coat's sculpt tree was reported to climb while the panel was open.**
  The panel's redraw path is proven side-effect free (500 idle redraws touch no host API, no
  state file and no queue file) and its statistics are manual, but the live cause was never
  reproduced.  If you see it, close the panel; nothing else in the bridge depends on it.

## Deliberately narrow

* **Models only.**  No baking, no texture nodes, no scene surgery.  The texture files stay out
  of the exchange folder unless the panel's `Textures` droplist asks for them, and even then
  they can travel only through 3D-Coat's own whole-scene export.
* **A returned model can only land on an object this bridge linked**, and `Replace in place` is
  the switch for it: off, a return arrives as an object of its own and nothing in the scene is
  written over.  It is Blender-side only - the 3D-Coat panel has nothing that could act on it -
  and with it off the two corrections that need the object the send came from (`Match scale`,
  and the position a `Send to origin` recorded) have no target to apply to.
* **A shader travels as its name and its preset's stored values, never as its look.**
  `Shaders as materials` gives each returned object a material named after the 3D-Coat shader it
  was sent with and fills in that preset's own base colour and metallic; everything else stays
  Blender's default.  The look itself cannot come along: a sculpt shader is a custom GPU shader
  (GLSL plus its own sampler textures) with no Blender equivalent, a per-volume slider someone
  moved is not readable from outside 3D-Coat (its Python API offers `SetShaderProperty` and no
  getter), and a shader that paints its colour from a texture ships an unused stored colour,
  which is deliberately left off the material.
* **3D-Coat's "Visible objects" export is 3D-Coat's own**, so what it covers is its decision (it can
  include hidden volumes).  Sending only the *visible* tree objects from 3D-Coat would need one
  of 3D-Coat's own commands (`Export Selected Objects`, or the decimate-and-export-all-visible
  action) and neither has been verified here, so nothing was guessed in.
* **A hidden parent excludes its descendants** in `Selected To Voxel`, and unreadable visibility or
  child lists are skipped conservatively - the status reports skipped branches rather than
  claiming an exact object count.
* **Try bringing 3D-Coat forward if a job is waiting.**  Background pause messages were observed
  while troubleshooting, but foreground-only polling is not established for every build.  The
  Send hint checks whether the process runs, not which window is active.
* **Windows-oriented installers.**  Both installers and the test scripts assume Windows paths
  (`cygpath`, `%APPDATA%`), and this release is Windows only: the exchange layout and both
  test suites assume it too, so nothing here claims another platform works.  The code that
  looks like it might (`xdg-open`, `~/AppLinks/…`) is untested and not supported.
* **The job file `import.txt` is shared with 3D-Coat's official Blender AppLink.**  Only one
  such file exists at the exchange root and 3D-Coat polls it there, so the official add-on
  queues its jobs in the same file (its own source writes the model path first).  Both can be
  enabled at once, but not send at the same instant: the last writer owns the queue.  CoatLink
  logs it when it replaces a job that was not its own, and it never imports or deletes a job
  that points outside its own `CoatLink` folder - earlier releases did, which could take
  the official add-on's queued model with it.
* **3D-Coat 2025.12 or newer.**  The two handovers that unparent an imported model - the
  `[pythonfile …]` line and the job's `import.py` - are both documented for 2025.12 and later
  (`[scriptfile]` stopped working in that release), so older builds do not get the unparenting
  step and may not import at all.  Nothing here has been run against 4.8.x/2024, whose user
  data folders are named differently again (`3D-CoatV48`, with the `Scripts` folder directly
  under it).
* **The tool buttons have no icon of their own, by choice.**  A button icon has to live in
  3D-Coat's program folder (`data/Textures/icons64`), which needs administrator rights, so the
  buttons use 3D-Coat's default icon and nothing outside 3D-Coat's user folder is ever written.
  That is also why the `.3dcpack` installs with no elevation prompt at all.
* **The `.3dcpack` needs one tick before it runs, and that is 3D-Coat's design, not ours.**  The
  package carries the scripts (into `UserPrefs/Scripts/cExtensions/CoatLink/…`), but:
  1. every `ExtraMenuItems` XML that exists (ours, LKS's, CoatMenu's, 3D-Coat's own template)
     carries an **absolute** script path, and a pack cannot know the absolute path of the machine
     it lands on: `%USERPROFILE%\…`, `%USERPROFILE%/…`, `~/…` and a path relative to the user
     folder (`Scripts/…`) were all tried in a live 3D-Coat and all failed with "file not found" -
     only the absolute path worked, and
  2. a pack cannot self-register either: a `cExtension` folder that is not listed in
     `cExtensions/startup.txt` is **not loaded**, and a pack can only replace that file, not add a
     line to it (which would drop the user's other extensions).
  The extension deals with the first one itself: on its first start it writes both XML files with
  **this** machine's paths, and moves an install of an older build out of the way at the same
  time.  The second is why 3D-Coat's Extensions panel has to be used once - and why the
  installation ends with "restart 3D-Coat".  After that, nothing runs by hand.
* **Subtree-scoped export** (only the current node plus its children instead of the whole sculpt
  tree) exists on the `parked/subtree-scoped-panel` branch and is **not** in the released code,
  because the grouping, positions and units of its output were never verified on a live round
  trip.  The `parked/ui-experiments-v1.16.5` branch holds UI variants that were tried and
  dropped.
