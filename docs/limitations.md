# Known limitations, in full

Stated plainly, because a bridge that silently does half the job is worse than one that says
so.  The short version is on the [README](../README.md).

## Verified incompletely or not at all

* **No live round trip has been run on this release.**  The 3D-Coat side is covered by tests
  against a stand-in `coat` module and the Blender side by headless runs against throwaway
  folders.  `tests/live_roundtrip.sh` runs the real thing (both applications open) and records
  the add-on version and the exact `import.txt` it wrote - the evidence earlier attempts were
  missing.  Until someone runs it, "works on a live pair" is an expectation, not a fact.
* **The `[vox]` import mode is asked for, not guaranteed.**  The mode line is written and
  3D-Coat's own log shows it being read, but on the build this was developed against the model
  still arrives in *surface* mode (`S` in the Sculpt Tree, `Volume.isSurface()` against
  `isVoxelized()`).  Two suspects, neither confirmed: the `[SkipImport]` / `[SkipExport]` lines
  that make the trip silent (3D-Coat documents `[SkipImport]` as "skip the import dialog,
  default options will be used", and the official Blender AppLink never adds it), and the
  `[pythonfile …]` line.  **`To voxels` in the panel is the reliable route** - see below.
* **`[pythonfile …]` execution is not confirmed.**  It is what unparents the imported objects
  and what the optional voxel conversion of an import rides on.  The panel's detail lines now
  report it as evidence: a dated, microsecond-resolution record means 3D-Coat ran the helper,
  while a missing, unreadable, undated or old record only means **not confirmed** - never proof
  that it did not run.  A record also does not say the conversion succeeded.
* **The selected-node export has not been through a live round trip.**  The API calls are the
  documented ones (`Scene.current()`, `fromVolume`, `fromReducedVolume`, `Mesh.Write`), the OBJ
  it produces is validated line by line, and everything that could go wrong has a test - but
  grouping, positions and units after a real send still have to be confirmed.
* **The reduction percentage is not verified end to end.**  The panel writes the same slider
  3D-Coat's own scripts write, and that field belongs to the "decimate to Retopo" flow in
  3D-Coat's sources; whether every AppLink export path honours it is untested.  The panel calls
  its number an estimate.
* **`To voxels` accepts the conversion dialog's defaults**, because it presses that dialog's OK
  itself (otherwise every object would need a click).  Consequence: a single object cannot be
  skipped mid-run - switch it off in the tree first, and it will be left alone.
* **The face count in 3D-Coat's sculpt tree was reported to climb while the panel was open.**
  The panel's redraw path is proven side-effect free (500 idle redraws touch no host API, no
  state file and no queue file) and its statistics are manual, but the live cause was never
  reproduced.  If you see it, close the panel; nothing else in the bridge depends on it.

## Deliberately narrow

* **Models only.**  No baking, no texture nodes, no scene surgery.  Textures can travel only
  through 3D-Coat's own whole-scene export.
* **3D-Coat's "whole scene" export is 3D-Coat's own**, so what it covers is its decision (it can
  include hidden volumes).  Sending only the *visible* tree objects from 3D-Coat would need one
  of 3D-Coat's own commands (`Export Selected Objects`, or the decimate-and-export-all-visible
  action) and neither has been verified here, so nothing was guessed in.
* **A hidden parent excludes its descendants** in `To voxels`, and unreadable visibility or
  child lists are skipped conservatively - the status reports skipped branches rather than
  claiming an exact object count.
* **Try bringing 3D-Coat forward if a job is waiting.**  Background pause messages were observed
  while troubleshooting, but foreground-only polling is not established for every build.  The
  Send hint checks whether the process runs, not which window is active.
* **Windows-oriented installers.**  Both installers and the test scripts assume Windows paths
  (`cygpath`, `%APPDATA%`).  The Blender add-on itself is OS-independent; the 3D-Coat half is
  plain Python and only its installer is Windows-specific.
* **Button icons need an elevated run** when 3D-Coat lives under `C:\Program Files`; they are
  skipped and reported otherwise, and the buttons use their default icons.
* **No `.3dcpack` is shipped, and that is measured, not assumed.**  A pack is a zip whose
  entries land relative to 3D-Coat's user folder, so it *could* carry the scripts - but nothing
  in it can create a working menu entry, and the experiment that showed this was:
  1. every `ExtraMenuItems` XML that exists (ours, LKS's, CoatMenu's, 3D-Coat's own template)
     carries an **absolute** script path, and
  2. a pack cannot know the absolute path of the machine it lands on: `%USERPROFILE%\…`,
     `%USERPROFILE%/…`, `~/…` and a path relative to the user folder (`Scripts/…`) were all
     tried in a live 3D-Coat and all failed with "file not found" - only the absolute path
     worked, and
  3. a pack cannot self-register either: a `cExtension` folder that is not listed in
     `cExtensions/startup.txt` is **not loaded**, and a pack can only replace that file, not add
     a line to it (which would drop the user's other extensions).
  So a pack would still end with "and now run this script once" - one step more than
  `CoatLink-Setup.cmd`, which is verified working.  The extension-pack door stays closed until
  one of those three facts changes.
* **Subtree-scoped export** (only the current node plus its children instead of the whole sculpt
  tree) exists on the `parked/subtree-scoped-panel` branch and is **not** in the released code,
  because the grouping, positions and units of its output were never verified on a live round
  trip.  The `parked/ui-experiments-v1.16.5` branch holds UI variants that were tried and
  dropped.
