# Changelog

## v1.17.1

* **The installer finds 3D-Coat wherever it is, and 3D-Coat does not have to be in
  `C:\Program Files`.**  The program folder is read from the uninstall entries Windows keeps (so
  an install in a folder of your own, on any drive, is found), then the Program Files folders this
  system actually spells - taken from the environment instead of assuming `C:` and `D:` - then
  every drive it has, then the per-user `AppData` locations as before.  A folder that is not an
  install (no `data\`) is never mistaken for one.
* **The user folder and the Python 3D-Coat ships follow Windows' own Documents folder**, instead
  of assuming `%USERPROFILE%\Documents` - which is where they are *not* once Documents is
  redirected to OneDrive, a setup where every door used to say "No Python found" next to a working
  install.  `COATLINK_DOCS`, `COATLINK_PYTHON` and `COATLINK_COAT_DIR` name any of them outright
  when even that is not enough; both `.cmd` doors and `install.ps1` carry the same detection, and
  a test runs the real door against a redirected Documents folder and checks which Python it
  picked from its own output.
* **The one-click installer now gets the button icons too.**  `CoatLink-Setup.cmd` runs the
  installer, and if the result says the icon folder could not be written (3D-Coat under
  `C:\Program Files`), it asks Windows for elevation once and runs the installer again - so a
  single double-click is a complete install: scripts, menu entries and icons.  Without that it
  was scripts and menu entries first, then "run it again as administrator" by hand.
  `COATLINK_NO_ELEVATE=1` skips the retry when you would rather not see a UAC prompt.

Blender 1.17.1, 3D-Coat side 1.17.1.


## v1.17.0

**One version number.**  From this release the Blender add-on, the 3D-Coat scripts and the
release itself carry the same version.  Before, a release was `v1.16.37` while Blender's add-on
list said `1.10.29` and the panel said `1.4.5` - so "which build are you running?" had three
answers.  They move together from here.

**Installing the 3D-Coat half is now one download and one double-click.**
`CoatLink-Setup.cmd` fetches the single-file installer from the latest release, runs it with the
Python 3D-Coat ships, and keeps the window open so the result can be read - no unzip, no console,
no path to edit.  It is 40 lines and installs nothing itself: it runs the same
`coat_side/CoatLinkInstall.py` every other door runs, and a test asserts it stays a thin wrapper
that ships no absolute path.  (Verified by running it for real: it downloaded, installed and
reported `ok`.)  For anyone who prefers the console, the README now carries a one-line URL paste
as well - **Scripts > Show Python console**, paste, done.

The rest of the behaviour is identical to `v1.16.37`; the only other difference in the code is
the version strings.  The entries below are the history of how the line got here: the audit round that
fixed modifier ownership, the `Modifiers` switch, hidden-branch conversion and the
after-import diagnostics; `To voxels` pressing 3D-Coat's own S/V badge and accepting its
dialog; remesh-on-send with voxel size and adaptivity; the panel's queue line and mode
summary; one installer behind four doors; and the documentation split with real screenshots.

Tests: Blender 196/196 plus every regression script and both installer smoke tests;
3D-Coat 160/160 plus tools, installer, tree report, API stub check, idle redraw and probe dry
run.  No live round trip has been run on this build.


## v1.16.37

3D-Coat side 1.4.5 (Blender side unchanged at 1.10.29).

* **Uninstalling now forgets the launcher entries it registered.**  Those entries only
  live for one 3D-Coat session, but the record saying they were registered stays in
  `Documents/3DCoat/CoatBridge.json` - so uninstalling and installing again made the
  next run believe the entries were already there and skip inserting them.  The Windows
  menu entry is the one that is only ever added at run time, so a reinstall came back
  without it.  Uninstalling clears that record and keeps the user's own settings in the
  same file; a missing or unreadable file is not an error.
* **The panel can say how much of the tree is still in surface mode.**  `Refresh info`
  now also reports `N of M visible objects in surface mode - press To voxels`, so after
  an import it is obvious whether there is anything left to convert, without clicking the
  objects one by one.  Drawn as its own bounded row; still nothing is read from the host
  or the disk during a redraw.
* **The live round-trip script was brought up to date**: it sends in `vox` mode with
  remesh off (a remeshed export would hide whether the import itself was right), records
  the add-on version and the exact `import.txt` it wrote - the evidence that was missing
  from every previous live attempt - and refuses to start when 3D-Coat is not running.
  It still has to be run with both applications open; nothing here was verified against a
  live round trip.

Tests: 3D-Coat 160/160, including the new launcher-record checks (cleared, settings kept,
corrupt file tolerated, missing file tolerated) and the mode-summary checks (counted over
visible leaves only, cleared after conversion, silent on an empty tree), plus tools,
installer, tree report, API stub check, idle redraw and probe dry run.

## v1.16.36

Blender 1.10.29, 3D-Coat side 1.4.4.  A bug-fix and feedback round: nothing here changes
the exchange format, the object linking, or the two menus' wording.


* 3D-Coat `To voxels` now presses the host's own conversion rather than only calling the
  API: every tree row has an S/V badge (`$VoxTreeBranch.VoxSurf.<object>`) whose tooltip
  is "Press this button to transform surface to voxel representation" - the conversion the
  user does by hand and reports as more accurate than `Volume.toVoxels()`. The badged
  conversion is verified by reading the volume back after a few frames; if the press did
  nothing (an object 3D-Coat does not offer it on) the code falls back to the API, so the
  button can never silently do nothing. Status reports how many came via the tree button.
* That conversion raises a dialog per object; the panel now accepts it itself
  (`$DialogButton#1` handed to 3D-Coat as the press's callback, which it calls every
  frame the dialog is up), so a whole scene converts from one click instead of one
  confirmation per object. It accepts the dialog's defaults, so cancelling for a single
  object mid-run is no longer possible.
* Blender menu divisions made uniform: exactly one divider before each section heading
  (`Send options`, `Return`, `Setup`, `Status`) and none inside a section, so the
  stray divider between the remesh group and the Send/Pull row is gone. Status is now a
  section like the others instead of the only boxed one - the remesh group stays the
  single framed sub-block. Tests assert the divider count, that every divider introduces
  a heading, that no heading is inside a box, and that only one box exists.
* 3D-Coat native panel: fixed-height wrapped status/detail/statistics rows, a full-width
  Status section, and Copy details (Windows clipboard, explicit click only). Copying
  preserves the original diagnostic readout; clipboard errors are reported in-panel.
  Rename Refresh sizes to Refresh info; keep all model queries out of idle redraws.
* 3D-Coat panel reports the queue: `Queue: <file> waiting - press Pull` or
  `Queue: nothing waiting from Blender`, so the next step after a Blender Send is
  obvious. The queue file is read by explicit actions and by opening the panel only -
  a test drives 500 redraws and asserts no queue read, no state-file access and no host
  API call.
* Blender feedback: a fixed four-line wrapped Status box replaces clipped technical
  path labels. Copy details provides the complete status and diagnostic paths on demand
  via the local clipboard, with an explicit local-path warning. No new window or upload.
* Keep Send/Pull errors and empty manual Pull results in the status readout; disabled
  Send/Pull tooltips explain that Object Mode is required. All settings remain expanded.
* Fix PowerShell auto-detection selecting an old Blender installation: compare numeric
  version directories rather than identical `addons` leaf names. Cover multiple
  installed versions, 5.10 versus 5.9, and non-version backup folders.
* Preserve same-named user modifiers; remove temporary remesh instances by ownership.
* Honor the Modifiers switch explicitly, including remesh-only exports; restore user
  modifier visibility on failure.
* Skip hidden parent branches and unknown visibility during manual To voxels.
* After-import evidence is dated and read from a bounded log tail; missing evidence is
  reported as unconfirmed, never as proof the script did not run. Prior foreground-only and ignored-script
  claims below were diagnostic hypotheses, not verified host behavior.
* Regression coverage uses isolated Blender exports and a simulated 3D-Coat tree.
  Automatic S-to-V import behavior has not been validated on the live host.

## v1.16.35

* **The 3D-Coat readout says voxel or surface.**  `Refresh sizes` now prints
  `Snapshot: 1234 faces · voxel volume` or `· surface mode`, read from the same
  `Volume.isVoxelized()` / `isSurface()` the Sculpt Tree draws as V / S.  After an import
  that is the first question, and answering it in the panel saves hunting for the object.
* **Whether the after-import step ran is now visible.**  The helper writes a line to the
  shared log on every run, including a run with nothing to do, and the Blender menu's
  detail lines compare its stamp with the last send: `After-import step: 3D-Coat ran it`
  or `not run by 3D-Coat - use To voxels in its panel`.  On this build the `[pythonfile
  ...]` line appears to be ignored, so "3D-Coat did not run it" is a normal, useful
  answer rather than a mystery.
* **The Send message says which of the two it is.**  `start 3D-Coat to pick it up` when it
  is not running, `bring 3D-Coat to the front to pick it up` when it is - 3D-Coat only
  reads the exchange folder while it is the active window.
* Blender 1.10.28.  3D-Coat side 1.4.3.

Tests: Blender 172/172 (a helper line newer than our send counts, one from before it does
not, a log without one says it was not run, nothing sent says nothing, and the detail
lines carry the answer) and 3D-Coat 137/137 (the readout says `voxel volume` /
`surface mode`, adds nothing when the volume answers neither, survives an object whose
volume cannot be read, and the helper leaves its line with the right counts on an empty
tree and after real work) - plus tools, installer, tree report, API stub check, idle
redraw, probe dry run, install smoke, every Blender regression script and both installer
smoke tests.

## v1.16.34

* **Tidied the Blender menu.**  Nothing was hidden and nothing was removed - the menu had
  simply grown, so it was grouped instead: the remesh settings (`Remesh on send`,
  `Voxel size`, `Adaptivity`) now sit in a box of their own, because they are one idea
  rather than three unrelated rows; `Auto receive` and `Without materials` share a line,
  as do the operator pairs (Detect / Open folder, Start 3D-Coat / Force re-read) and the
  switches (`Modifiers` / `Skip dialogs`, `Scale` / `Match scale`).  `Axis` keeps a whole
  line to itself on purpose: a droplist in half a line has its text cut off.
  `Force re-read return signal` is now `Force re-read` - the tooltip says the rest.
* Blender 1.10.27.  3D-Coat side unchanged (1.4.2); the two menus still read in the same
  order with the same words.

Tests: Blender 167/167 - the menu still draws the three headings, the boxes are drawn, and
every control is still there and still reachable (the assertions that previously checked
each advanced control one by one now also check the new grouping) - plus every regression
script and both installer smoke tests.

## v1.16.33

* **`Adaptivity` for the remesh.**  A third control next to `Remesh on send` and `Voxel
  size`: 0..1 passed straight to the Remesh modifier's adaptive option, which drops
  polygons where the surface is flat - so a big flat panel does not cost a uniform grid
  of triangles.  It never adds faces, an out-of-range value is clamped rather than passed
  on, and a build without the option still remeshes.  Like the voxel size, the field is
  always drawn and greys out when the checkbox is off.
* Blender 1.10.26.  3D-Coat side unchanged (1.4.2).

Tests: Blender 166/166 - the modifier receives the voxel size and the adaptivity that
were set (0.02 and 0.7 reach the object), an absurd 4.0 is clamped to 1.0, a remeshed
export with adaptivity never carries more vertices than one without, and the earlier
remesh checks (scene untouched, only our modifier removed, coarse coarser than fine,
off means the plain mesh) still hold - plus every regression script and both installer
smoke tests.

## v1.16.32

* **`Remesh on send`.**  A Send now voxel-remeshes what it exports.  It is done with a
  temporary Remesh modifier on each object going out, an export with modifiers applied,
  and the modifier removed in a `finally` - the scene's meshes are never modified, object
  names are never touched, and your own modifiers survive (only the one named `CoatLink
  Remesh` is taken off).
* **`Voxel size` next to it.**  A distance; `0` lets the add-on pick about 64 voxels
  across the object's largest dimension, which keeps a metre-scale model in the hundreds
  of thousands of faces rather than millions.  Both controls sit in the menu under
  *Send options* and are always drawn: the voxel-size field stays visible and greys out
  when the checkbox is off.  Remesh is on by default; switch it off and the export is
  exactly the mesh you have.
* The status line and the shared log say `remeshed N` when it happened, so a send is
  never ambiguous about what went out.
* Blender 1.10.25.  3D-Coat side unchanged (1.4.2).

Tests: Blender 162/162 - a remeshed export has far more vertices than the 8 of the cube
while the cube in the scene still has 8; no `CoatLink Remesh` is left behind; a modifier
the user added is still there afterwards; a coarse voxel size exports fewer vertices than
a fine one; with remesh off the export is byte-for-byte the plain mesh; and the axis and
scale sections state that they compare coordinates exactly, which is why they run with
remesh off - plus every regression script and both installer smoke tests.

## v1.16.31

* **`To voxels` now covers the whole tree, not the selection.**  It converts every
  object the Sculpt Tree is showing - the point being that after an import you want the
  scene ready, not one object at a time.  Leaves only: a node with children is the
  packaging group around an import, so it is walked into rather than converted.  Objects
  switched off in the tree are counted and left alone (`N hidden, left alone`), the ones
  already voxelized are counted too, and a build whose `SceneElement` cannot answer
  `visible()` converts rather than skips - one object too many is easier to undo than
  silently skipping the one you wanted.  The sculpt root itself is never treated as an
  object, so an empty tree says `Nothing in the Sculpt Tree to convert` instead of
  reading the root's volume.
* 3D-Coat side 1.4.2.  Blender side unchanged (1.10.24).

Tests: 3D-Coat 133/133 - over a tree with a packaging group, a plain visible object, one
switched off and one already voxel, it converts exactly the two visible surface objects,
reports `2 to voxels, 1 already voxel, 1 hidden, left alone`, is idempotent on a second
press, reports an object whose volume cannot be read, says so on an empty tree, and
converts rather than skips when `visible()` is missing - plus tools, installer, tree
report, API stub check, idle redraw, probe dry run and install smoke.

## v1.16.30

* **A voxel import now asks to be voxelized.**  Models have been arriving in 3D-Coat in
  surface mode even though the job file says `[vox]`, and the after-import script that
  unparents the imported group was already riding along in that same job file.  It now
  also converts the group's objects with `Volume.toVoxels()` - but only when the job
  asked for a voxel import: the Blender side writes the copy that goes into the exchange
  folder with `VOXELIZE = True`, and the file in the add-on stays neutral, so nothing
  changes for the other modes.  The packaging node is not converted (no stray volume),
  objects already voxelized are skipped, and a failure is written to the shared log
  instead of interrupting the import.
* The README records a 3D-Coat behaviour worth knowing: **it only polls the exchange
  folder while it is the active window** (`SetSystemPause: 1` when it loses focus), so a
  Send made from behind another window waits until you bring 3D-Coat forward.
* Blender 1.10.24.

Honest state of this one: the voxelizing half can only run if 3D-Coat executes the
`[pythonfile ...]` line, which has not been observed on the build this was written
against (the sibling unparenting never logged anything either).  It is harmless when it
does not run, and the panel's `To voxels` button remains the guaranteed path.

Tests: Blender 150/150 (the helper that goes into the job file is the add-on's own file
with only the voxel flag flipped, the flag is off for every other mode, and the helper
stays byte for byte identical then) plus every regression script and both installer
smoke tests.  3D-Coat suite green (the helper converts a group's surface objects, skips
what is already voxel, is idempotent, ignores other people's groups, and ships with the
flag off) plus tools, installer, tree report, API stub check, idle redraw, probe dry run
and install smoke.

## v1.16.29

* **`To voxels` in the 3D-Coat panel.**  Models sent from Blender have been arriving in
  3D-Coat in *surface* mode (`S` in the Sculpt Tree) even though the job file asks for
  `[vox]`, and getting them where the sculpting tools want them meant doing it by hand.
  The panel now has the one click: it voxelizes the object selected in the Sculpt Tree
  and everything under it, walks into a packaging node instead of converting it (no
  empty wrapper volume), leaves objects that are already voxelized alone, reports
  `N to voxels, M already voxel`, and turns any failure into a sentence rather than an
  exception.  It also refreshes the size readout afterwards.
* 3D-Coat side 1.4.1.  Blender side unchanged (1.10.23).

Tests: 3D-Coat 130/130 - the conversion runs over a group without touching the wrapper,
skips what is already voxel, is idempotent on a second press, reports an object whose
volume cannot be read, and says what to do when nothing is selected - plus tools 29/29,
installer 32/32, tree report 11/11, API stub check, idle redraw, probe dry run, install
smoke.

## v1.16.28

* **The 3D-Coat panel stopped showing code names.**  3D-Coat labels a panel control by
  the name in the script unless that name is translated, so the panel read
  `SendScope`, `ReductionPercent`, `Textures`, `RefreshStats`, `OpenFolder`,
  `StartBlender`, `RemoveLauncher`.  All of them are translated now - `Scope`,
  `Reduction percent`, `Refresh sizes`, `Open folder`, `Start Blender`, `Remove tool
  buttons` - with the wording borrowed from the Blender menu wherever the two mean the
  same thing.
* Send and Pull share one row in the 3D-Coat panel, the way the Blender menu draws
  them, instead of being two full-width bars.
* Both menus are grouped under the same headings - **Send options**, **Return**,
  **Setup** - and every action in the Blender menu carries an icon (Detect, Open
  folder, Start 3D-Coat, Force re-read, Unlink), with Send / Pull given a taller row
  because they are the point of the add-on.  Nothing is hidden: the headings group,
  they do not fold.
* Blender 1.10.23.

Tests: Blender 147/147 (the headings are drawn in order, ahead of what they head) plus
every regression script and both installer smoke tests.  3D-Coat 122/122 (every panel
control has a readable label, Send and Pull share a row, the headings are there) plus
tools 29/29, installer 32/32, tree report 11/11, API stub check, idle redraw, probe dry
run, install smoke.

## v1.16.27

* **The import mode is an option, not a setting.**  `Import as` now sits at the top of
  the Blender menu next to `Scope` - the two choices you make before pressing Send,
  both visible, instead of one up top and one below the buttons.  Voxel is still the
  default.
* **Nothing is collapsed any more.**  The `Advanced` fold-out is gone from both sides:
  every control is drawn straight away, in the Blender menu and in the 3D-Coat panel.
  A fold-out hides exactly the switch you need when something misbehaves - `Skip
  dialogs` is in that group - and "it is one click away" is no help if you cannot see
  it.
* Blender 1.10.22.

Tests: Blender 143/143 (the menu draws scope, then `Import as`, then Send / Pull; no
fold flag exists on the preferences any more; every advanced control is drawn without
unfolding) plus every regression script and both installer smoke tests.  3D-Coat
113/113 (the panel draws its advanced buttons without unfolding, and keeps no fold
state) plus tools 29/29, installer 32/32, tree report 11/11, API stub check, idle
redraw, probe dry run, install smoke.

## v1.16.26

* **One button on the Blender top bar, and the two menus now match.**  The bar used
  to carry four widgets (`CoatLink` menu, a `Whole scene` toggle, `Send`, `Pull`);
  now it is the `CoatLink` button alone, and everything lives inside it: `Scope`,
  then `Send` / `Pull`, then the settings, then *Advanced*.
* The scope is a droplist on both sides with the same two entries - **Selected** /
  **Whole scene** - instead of a toggle in Blender and a droplist in 3D-Coat.
* The 3D-Coat panel's own buttons are translated to `Send` / `Pull`, matching the
  Blender menu; the tool-strip buttons keep `Send to Blender` / `Pull from Blender`
  because they stand on their own outside any menu.
* `Folder` is now `Open folder` on both sides.
* Blender 1.10.21.

Tests: Blender 130/130 (the bar holds only the menu button; the menu draws scope,
Send, Pull in that order; the scope preference replaces the old toggle, with the
selection/whole-scene behaviour checked as before) plus every regression script and
both installer smoke tests.  3D-Coat 112/112 (the panel's buttons are translated to
Send / Pull, the tool buttons keep their labels, and the droplist wording matches the
Blender menu), tools 29/29, installer 32/32, API stub check, idle redraw, probe dry
run, install smoke.

## v1.16.25

* **The 3D-Coat panel now says what its `Send scope` actually sends.**  The
  droplist sits at the very top, directly above `Send to Blender`, and a line under
  it reports the current choice: "selected node + its children" or "3D-Coat's own
  export (all volumes, its own rules)".  The two are not the same thing - the
  selection is extracted by the bridge, the scene goes through 3D-Coat's own export
  - and a control that hides that difference is worse than no control.
* Not shipped, but looked up: 3D-Coat's own `Export Selected Objects` ("selected
  Sculpt Tree layers") and its decimate-and-export-all-visible-volumes action are
  the routes to a visible-objects-only scene send from 3D-Coat.  Neither is verified,
  so neither is in this build; the README says so under Known limitations.

Tests: 3D-Coat logic 108/108 (the scope hint follows the droplist, and the layout
checks were adjusted for the two new lines), tools 29/29, installer 32/32, API stub
check, idle redraw, probe dry run, install smoke.  Blender side unchanged (129/129).

## v1.16.24

* **A `Whole scene` toggle, left of `Send` on the Blender top bar.**  Off (the
  default) a send exports the selection, as before; on, it exports every visible
  object in the scene.  Hidden objects stay out, the status line names the scope it
  used (`(selection)` / `(whole scene)`), and the log line records it with the object
  count.  The 3D-Coat panel already had the matching control (`Send scope`,
  `selected node` / `whole scene`) directly above its `Send to Blender` button.
* Blender 1.10.20.

Tests: Blender 129/129 (eight new checks: the toggle is drawn left of Send, it is off
by default, a send with it off exports only the selection, with it on exports both
visible objects, a hidden object stays out, switching back restores the selection,
and the status says which scope was used) plus every regression script and both
installer smoke tests.  3D-Coat side unchanged and green (106/106, 29/29, 32/32,
API stubs, idle redraw, probe, install smoke).

## v1.16.23

* **An imported model no longer arrives under a `bridge` parent in 3D-Coat.**
  3D-Coat wraps an imported file in a node named after it, so Blender's Hull and
  Turret came in as `bridge > Hull, Turret`.  The job file now ends with
  `[pythonfile CoatLink_AfterImport.py]` (documented for 3D-Coat 2025.12+), which
  makes 3D-Coat run `coat_bridge/after_import.py` right after the import: it moves
  the objects up to the sculpt root and deletes the now empty wrapper.  A Pull from
  the panel does the same in code (`flatten_imported_group`), so both import paths
  end up with a tree that matches the Blender outliner.
  Guarded on purpose: only a group that carries this model's name is touched, only
  its children are moved (never deleted), a group that is not ours is left alone,
  a tree without a wrapper is a no-op, and every failure is logged and swallowed so
  the import itself can never break.
* Blender 1.10.19.

Tests: 3D-Coat 106/106 logic plus new `test_import_unparent.py` (13 checks: the
helper against a simulated tree, our Pull path, someone else's group, an already
flat import, and a model whose stem no longer matches), tools 29/29, installer
32/32, API stub check, idle redraw, probe dry run, install smoke.  Blender side:
the job file's last line, the helper being byte-identical to the add-on's copy,
carrying no machine-specific path, and compiling.

## v1.16.22

Two behaviour changes the user asked for.  Everything else is unchanged.

* **3D-Coat sends the node selected in the sculpt tree**, plus its children, instead
  of the whole scene.  The panel gained one droplist for it (`selected node` /
  `whole scene`), defaulting to the selection.  The extraction goes through
  3D-Coat's own `Scene.current()` + `Mesh().fromVolume(volume, with_subtree=True,
  all_selected=False)`, and a reduction percentage is applied with
  `fromReducedVolume` - the parameter is named `reduction_percent` there, which is
  also the wording the panel uses.  There is deliberately **no fallback to the
  whole-scene export**: with nothing selected the button says so and sends nothing,
  and a result that loses its object groups is refused rather than merged.
  The whole-scene route (3D-Coat's own export dialog, textures included) is still
  there - as an explicit choice, not as a silent default.
* **Blender opens models in 3D-Coat as a voxel sculpt object by default** (`Import
  as` now starts on `Sculpt Object (voxel)` and that entry is listed first).

Also fixed: `check_coat_api.py` looked for 3D-Coat's type stubs at a hardcoded
`D:\Program Files\3DCoat-2026`, so the API check quietly stopped checking when
3D-Coat moved to another drive and version folder.  It now searches, newest wins,
with `COAT_API` as an override.

Notes from the live install: with 3D-Coat in `C:\Program Files` the icon folder needs
administrator rights, so the installer skips the four icons and says so - the buttons
and the panel work regardless, and running it as administrator once copies them.

Tests: 3D-Coat logic 106/106 (the send path has its own file, `test_scoped_send.py`,
19 checks - scope, subtree flag, reduction, empty selection, missing geometry and a
merge that loses groups), tools 29/29, installer 32/32, API stub check (now really
running), idle redraw, probe dry run, install smoke.  Blender: see v1.16.19's suite.

## v1.16.21

Installing the 3D-Coat half is now one step instead of three, and the plugin code
itself is unchanged from v1.16.19 (Blender 1.10.17).

* **One installer, four doors.** `coat_side/CoatLinkInstall.py` holds the install
  logic; `install.cmd` (double-click on Windows), `install.sh`, `install.ps1` and
  the single-file `CoatLink-Setup.py` all run it.  The shell and PowerShell
  installers used to carry their own copies of the logic, which is exactly how two
  installers drift apart - now a test installs with each and compares the trees
  byte for byte after normalising the generated paths.
* **Double-click path.** Unzip, double-click `install.cmd`: it finds 3D-Coat's own
  bundled Python, writes the scripts and both menu XMLs with this machine's paths,
  copies the button icons when that folder is writable and says so when it is not.
  No admin rights, no PATH edits, nothing to configure.
* **Single-file path.** `dist/CoatLink-Setup.py` is the same installer with the
  files embedded: download one file and paste one line into 3D-Coat's Python
  console.  `package.sh` builds it, and it is published as its own release asset.
* **Uninstall.** `--uninstall` / `-Uninstall` removes exactly what was installed
  (scripts, the two menu XMLs, the icons) and leaves every other file alone.
* The scoped-export module is no longer installed: nothing calls it.

Tests: 3D-Coat installer **29/29** (new), plus the existing suites unchanged -
Blender 113/113 and its regression scripts, 3D-Coat logic 103/103, tools 29/29,
API stub check, idle-redraw check, probe dry run, both installer smoke tests.

## v1.16.20

Release prep - the bridge code itself is unchanged from v1.16.19 (Blender 1.10.17).

* **Installers for both halves.** `install.ps1` does the whole job on Windows with
  nothing but PowerShell (no bash, no git); `install.sh` is the same for bash,
  MSYS and WSL. Both find Blender's add-on folder, 3D-Coat's script folder and its
  program folder on their own, take explicit paths or `-BlenderOnly` / `-CoatOnly`,
  and can be run twice.
* `tests/test_install_ps1.sh` proves the PowerShell installer and the bash
  installer land byte-identical files, XML included.
* `package.sh` builds the two release archives: `coat_bridge.zip` for Blender's
  *Install from Disk*, and the full source archive.
* GPL-3.0-or-later LICENSE, `.gitattributes` so the repo and every checkout use one
  line ending, and a README rewritten for people who did not write the thing:
  three install routes (easiest first), the actual current UI, and an honest
  "known limitations" section.
* The test scripts now locate the newest Blender build, 3D-Coat's bundled Python,
  the 3D-Coat program folder and the script folders themselves - every hard-coded
  author path is gone (`tests/find_tools.sh`), and the install smoke tests are part
  of the suite.

## v1.16.19

* Persist the pull record in the exchange folder (pull-history.json), so restarting
  Blender no longer reimports the return file that is still sitting there. A model
  whose version changed is imported normally, an explicit pull still overrides the
  record, and a damaged record falls back to importing instead of blocking.
* tests/run_tests.sh now runs every standalone regression script (seven of them were
  never wired into the suite) in its own isolated Blender session.
* Blender 1.10.17. Tests: main suite 113/113 plus receipts, retry, delayed signal,
  OBJ groups, object names, target identity, pull history; 3D-Coat logic 103/103,
  tools 29/29, API stub check, idle redraw, probe dry run, install smoke.

## v1.16.17

* Stabilize installed panel: no scene queries or filesystem reads during idle redraw; control changes persist only when edited. Disable process callback and automatic receipt display on Coat panel pending host issue verification. Manual stats only.
* Block foreign return adoption without prior send; do not mask later pull status with earlier send receipt.
* Pending subtree implementation backed up, not installed.
* Blender 1.10.15; 113 regression checks and 1000 simulated idle cycles passed. Live face-count growth remains unverified.

## v1.16.16

* Persist export aliases on Blender objects; map multi-object returns independently, preserving Blender-side renamed targets and avoiding unrelated same-name objects. New return groups stay separate.
* Single-object legacy return retains last-sent-target fallback. Coat-side renames without retained aliases cannot be reliably mapped.
* Real Blender reversed-order / rename / collision regression passed; existing suite 113/113. Blender add-on 1.10.14.

## v1.16.15

* Receiver-generated file-version receipts after successful Python imports; native AppLink imports bypassing these hooks remain unconfirmed. Hash cache avoids rehashing unchanged models every draw.
* Filter model discovery by extension so receipt sidecars are never imported.
* Correct reduction wording to removed percentage based on official auto_export.cpp. Selected-volume remaining-face estimate explicitly unverified for AppLink export.
* Read-only Coat diagnostic supplied; live Coat verification blocked because application was not running.
* Blender 1.10.13; tests 113/113, Coat simulated 101/101 + 29/29, receipt tests and installation smoke passed.

## v1.16.14

* Compact native panels: advanced/maintenance settings hidden by default; Blender keeps transfer shortcuts on top bar instead of duplicating them.
* Normal Pull respects deduplication; force re-read is advanced-only. Empty receive offers an action; send notification says queued. Successful pull includes object count.
* No receipt handshake or estimated polygon counts claimed; those remain unverified.
* Blender 1.10.12; regression 113/113; Coat logic 101/101, tools 29/29 and install smoke passed.

## v1.16.13

* Remove TargetSize and ApplySize controls from the native 3D-Coat panel; retain read-only size display. No export or unit changes.
* 3D-Coat logic 100/100, tools 29/29, installation smoke test passed. Installed library byte-verified.

## v1.16.12

* Enable OBJ group splitting on return: 3D-Coat exports object boundaries as g records. Distinct groups become separate Blender Objects.
* Real Blender regression: Hull and Turret become two meshes. Existing suite 113/113.
* Blender add-on 1.10.11.

## v1.16.11

* Auto pull deduplicates successful file versions across delayed mirror signals (canonical path, nanosecond mtime and size). Modified exports still import; explicit manual pull can repeat. Session cache bounded to 128 paths.
* Real Blender delayed-signal and retry regressions pass; existing suite 113/113.
* Blender add-on 1.10.10. No UI or unit changes.

## v1.16.10

* Failed or missing returned models no longer permanently acknowledge their signal. Automatic pull retries without requiring a new export.txt.
* Real Blender regression covers delayed model creation and transient import failure. Existing 113 checks pass.
* Blender add-on 1.10.9; no UI or unit-setting changes.

## v1.16.9

* Fix first return / deleted target: resolve replacement targets only among objects existing before import. Never delete an arriving object as its own temporary source.
* Real Blender regression covers first import and repeated import with absent/stale target names.
* Blender add-on 1.10.8. UI and 3D-Coat settings unchanged.

## v1.16.8 - 2026-09-13

"StructRNA of type Object has been removed" on pull - the real one this time.

* Cause: removing the temporary imported object pushes an undo step, and Blender
  invalidates **every** Python reference when that happens - including the target
  we were working on.  With `Import without materials` on, the target was used
  again immediately after that removal, and the whole pull failed there.  (v1.16.3
  re-resolved the objects once at the start; it had to happen *after* the removal
  too.)
* The target is now re-resolved by name after every step that can kill a
  reference, and `_match_scale` re-resolves its own object as well, so a reference
  that dies mid-flight is "the object went away" instead of a failed pull.
* A failed import now writes the **traceback** and the context (target name, object
  count) into the shared log - the message alone could not say which line failed.
* Regression test: a target that is invalidated mid-import is survived and the
  geometry still lands on the re-created object.
* Blender add-on 1.10.7.  Suite 113 checks.

## v1.16.7 - 2026-09-13

"the model never arrives" - the return can come from 3D-Coat's own pool.

* Reported, and visible in the status line as
  `Ignored export.txt outside BlenderBridge: 3DC015.fbx`: 3D-Coat had exported
  into its **own** AppLink folder (`Documents/3DC2Blender/ApplinkObjects`) rather
  than our `BlenderBridge` one, and the bridge only accepted files inside
  `BlenderBridge` - so the trip completed and Blender quietly ignored it.
* A signal pointing outside `BlenderBridge` is now accepted when the file it
  lists was written **after our last send** (that is this trip's model); older
  ones are still ignored, and the official AppLink's own signal is still never
  deleted - only read.
* Second, the unit conversion is applied to **OBJ only**: an FBX declares its own
  units and axes, and converting those again would put the model 100x off (or
  rotated) twice.
* Third, a pull now records its outcome in the shared log (`pull: ...`) and a pull
  that arrives while another is running says so instead of returning silently -
  the silence is what made this one hard to see.
* Blender add-on 1.10.6.  Suite 111 checks.

## v1.16.6 - 2026-09-13

Units are matched automatically - that is why models arrived small.

* Measured from the real exchange folder: Blender sent a 2.20 m cube and 3D-Coat
  kept it ~100x smaller.  3D-Coat reports `scene_units: CENTIMETERS` with
  `scene_scale: 1.0`, so the mismatch was never the scene scale (the number the
  v1.14 attempt used, and it is 1.0 on this machine, which is why nothing
  changed): Blender writes **metres**, 3D-Coat's scene is in **centimetres**.
* The bridge now converts by unit: `Scene.GetSceneUnits()` is read from 3D-Coat's
  state file and the factor is 100 (centimetres), 1000 (millimetres), 1 (metres),
  39.37 (inches) or 3.28 (feet), times the scene scale times Blender's own scene
  unit scale.  Nothing to type; `3D-Coat scale` overrides it if ever needed.
* The same conversion is undone on the way home, so the returned model lands at
  the size it was sent at - and the size "correction" now only ever fixes a unit
  factor: a difference that is *not* one of those is the model itself (a sculpt, a
  reduction) and is left alone and reported, instead of stretching someone's work.
* Tests are isolated from the real 3D-Coat state file from the start now (they
  used to read this machine's settings partway through, which is why the numbers
  moved between runs).  Suite 103 checks.
* Blender add-on 1.10.5.

## v1.16.3 - 2026-09-13

"StructRNA of type Object has been removed" on pull.

* The import pushes an undo step, and Blender invalidates the Python references
  to objects when it does - so the object `import_model()` handed back could
  already be dead, and touching it failed the whole pull.  Reproduced in a test
  (the failure message came out identical to the one on screen).
* The pull now takes the arriving objects' **names** from the scene instead of
  from those references (strings cannot go stale), and resolves the target and
  the temp object by name through `_object()`, which treats a dead struct as
  "gone" rather than as an error.
* A pull can no longer run twice at once: the watcher's timer and a click used to
  be able to overlap on the same model.  A second call while one is running is
  skipped.
* Blender add-on 1.10.3.  Suite 97 checks.

## v1.16.2 - 2026-09-13

A pull imports one model, not one per signal.

* Reported: the same model sometimes landed in Blender twice.  Cause found and
  reproduced in a test: 3D-Coat leaves a signal in **both** exchange roots (and
  can write the model into both), and the pull imported once per signal - same
  path twice, two "Pulled" lines, two passes over the same mesh.
* The pull now reads every signal first and then imports exactly **one** model,
  the newest, marking all the signals as seen and consuming the ones that list
  nothing foreign.  A deliberate re-pull (the button) still works, and a signal
  the official AppLink owns is still left alone.
* Regression checks: a signal in both roots imports exactly once, leaves no extra
  object behind, consumes both signals, and reports it once.
* Blender add-on 1.10.2.  Blender suite 94 checks.

## v1.16.1 - 2026-09-13

Cleanup after the audit, and the version rule.

* Deleted the parked Qt panel and its tests (no Qt, no extra window - it had no
  business staying in the tree), the stale `CoatBridgeDialog.py` (also removed
  from an installed 3D-Coat and from `install.sh`'s stale list), and the
  decision mock-up in `docs/`.
* Removed a dead helper and made every action log 3D-Coat's scale/units/axis once
  instead of twice.
* README brought back in line with reality: what each side looks like now, what
  the bridge handles quietly (scale, axis, reduction, textures, size), the real
  sizes of both halves.
* From here the version only ever moves in the last place (`v1.16.1`, `v1.16.2`,
  ...); the first two numbers are the user's to allow.  Blender add-on 1.10.1.

## v1.16.0 - 2026-09-13

A size block in 3D-Coat's panel.

* The panel now reads the current object's size out of 3D-Coat itself
  (`Scene.current().Volume().calcWorldSpaceAABB()`), shows it live, and has a
  target-size field: type the size you want and `ApplySize` scales the object in
  place (`mat4.ScalingAt(centre, factor)` + `transform_single`, so it grows about
  its own centre and does not wander).  Nothing is exported, re-imported or
  round-tripped to change a size.
* Refusals are explicit rather than silent: a zero or non-numeric target, a
  degenerate object, and "nothing selected" each say what happened; the factor
  goes into the log.
* Still no Qt and no extra window: the panel is 3D-Coat's own dialog and the
  controls are native (`Name,[min,max]` number fields, droplists, buttons).
* 3D-Coat suite 102 checks; the test harness no longer dies when a check passes
  a tuple as its detail.

## v1.15.0 - 2026-09-13

One format, one axis rule, both directions.

* Measured from a real round trip: the model Blender sent was 0.12 m across and
  the file 3D-Coat returned (FBX) was **empty**, and the two directions used
  different formats - OBJ out, FBX back.  An FBX declares its own up-axis while
  an OBJ does not, so the two directions could never be made to agree on
  orientation.
* 3D-Coat now hands the model back as **OBJ too**, so the axis rule (the `Axis`
  setting, fed by 3D-Coat's own swap-Y/Z option) applies to the export and the
  import identically.  This is what was meant to keep the two from drifting.
* Blender still reads an FBX return (any older or hand-made file), but no longer
  overrides the axes of a format that carries its own - that is how a model ends
  up rotated twice.
* Blender addon 1.10.0.  Suites: Blender 90 checks; 3D-Coat 88 + 29 + 24.

## v1.14.0 - 2026-09-13

Size and axis: detected on the 3D-Coat side, matched on the Blender side.

* **Scale.** 3D-Coat's `ApplyMeasurementScale` exports in natural units, which
  means an incoming model is divided by its scene scale and arrives small by
  exactly that factor.  The 3D-Coat side now writes its own numbers
  (`Scene.GetSceneScale()`, `GetSceneUnits()`, and the `SwapYZ` option) into its
  state file on every action, and Blender reads that file and sends the model
  multiplied by the scene scale - so a 2 m cube is 2 scene units in 3D-Coat.
  `3D-Coat scale` in the menu overrides it (0 = use 3D-Coat's own number).
* **Axis.** `SwapYZ` - 3D-Coat's "swap the Y and Z scene axes" option for Z-up
  applications - is picked up the same way.  The OBJ exporter/importer is given
  the matching `forward_axis`/`up_axis` pair (`NEGATIVE_Z`/`Y` normally,
  `Y`/`Z` when 3D-Coat swaps), so the model keeps its orientation.  `Axis` in the
  menu can force either convention.
* Verified through Blender's real exporter, not by inspection: the tests parse
  the OBJ Blender wrote and check the coordinates are 100x bigger and that Y/Z
  are exchanged, plus the manual override and the "no data from 3D-Coat" default.
* Blender addon 1.9.0.  Suites: Blender 90 checks; 3D-Coat 88 + 29 tool + 24 Qt.

## v1.13.0 - 2026-09-13

Send and Pull on the bar itself.

* The top bar now carries three entries in one row: the `Coat Bridge` settings
  menu, then **Send** (EXPORT icon) and **Pull** (IMPORT icon) to its right, so a
  round trip is one click instead of two.  The menu keeps the same two buttons
  plus every setting.
* The menu icon moved to COLLAPSEMENU so it no longer looks like Send.
* Blender addon 1.8.0.  Suite: 81 checks - the drawer really builds the three
  entries in that order, and still draws nothing on the left-hand side.

## v1.12.0 - 2026-09-13

A number field in 3D-Coat's panel - typed, not captured.

* The reduction percentage is now a **native number field in the panel**
  (`ReductionPercent,[0,100]`), and textures a native droplist (3D-Coat decides
  / on / off) - both in 3D-Coat's own dialog, still no Qt and no extra window.
  The layout syntax comes from 3D-Coat's shipped Autoexport example panel:
  `Name,[min,max]` is a number field bound to that attribute, `Name,[#a|#b]` a
  droplist, `Name,group1` a radio group, `Name,folder` / `Name,save:*.fbx` file
  pickers.  (`coat.dialog()` itself only documents buttons, which is why the
  earlier version had to capture the value from 3D-Coat's dialog instead of
  typing it - that capture still runs when the field is left at 0.)
* Typing a number stores it (`panel.process()` persists every frame), and every
  export pushes it into 3D-Coat's own decimation slider and presses OK, so the
  export dialog is never seen.  0 hands the choice back to 3D-Coat's dialog.
* 3D-Coat side suite: 81 checks (the panel really carries the two controls, the
  number field starts at the stored value, typing stores it, the droplist
  tri-state round-trips, and the export path still fills 3D-Coat's dialog in).

## v1.11.0 - 2026-09-13

The export settings live in 3D-Coat, where the export happens.

* The "3D-Coat export" block added in v1.10.0 is **gone from Blender** - the
  job file is back to three lines plus the skip flags.  Export settings belong
  on the side that exports.
* 3D-Coat side, same idea as the bridge always had: the first export reads the
  percentage out of 3D-Coat's own dialog and remembers it
  (`CoatBridge.json`), and every export after that pushes it into 3D-Coat's own
  decimation slider (`CMD.SetSliderValue("$DecimationParams::ReductionPercent")`,
  the id `Scripts/mm_export.as` and `CoreAPI/Templates/CoreAPI_Export/
  auto_export.cpp` both use) and presses OK, so the dialog is never seen again.
* Same mechanism for textures: `Textures: 3D-Coat decides / on / off` cycles in
  the panel and drives `CMD.SetBoolField("$ExportOpt::ExportTextures")`.
* The panel itself is 3D-Coat's own dialog (`coat.dialog()...topRight()`), opened
  by the tool-strip button.  **No Qt, no extra window** - the parked
  `CoatBridgeQt.py` is not installed and nothing imports it.
* Blender addon 1.7.0.  Suites: Blender 77 checks; 3D-Coat 81 + 29 tool + 24 Qt
  (parked module, kept honest).

## v1.10.0 - 2026-09-13

3D-Coat's export dialog, moved into the settings.

* New "3D-Coat export" block in the Blender menu.  The values are written into
  the job file (import.txt) with 3D-Coat's documented syntax, so its export runs
  without stopping at a dialog:
  `[ExportResolution=LOW-POLY|MID-POLY]`, `[CoarseMesh=0|1]`,
  `[ExportTextures=0|1]`, and `[field $ExportOpt::DesiredPolycount = N]`
  (the export dialog's own polycount field, written first because a `[field ...]`
  command replaces earlier option commands).
* Defaults stay neutral: no resolution, no polycount, textures on, coarse off -
  the two always-written lines then simply restate 3D-Coat's current behaviour.
* Nothing is set twice: the 3D-Coat side only consumes the job file, so the
  Blender menu is the single place these live, and they apply to the model
  coming back in both directions.
* Blender addon 1.6.0.  Suite: 86 checks (the job file carries the settings in
  the right order, the dialog stays skipped, the status line and the shared log
  report what was asked for).

## v1.9.0 - 2026-09-13

`Import without materials`.

* New toggle in the Blender menu (`No materials`, off by default): a pulled model
  comes back as bare geometry.  The mesh's own slots are dropped, and the material
  datablocks the returned file brought are removed too - but only when nothing
  else uses them, so the user's own materials are never touched.
* Ordering matters and is handled explicitly: the file's materials are collected
  and cleared before the mesh swap, and the datablocks are only collected after
  the temporary imported object is gone (otherwise it still references them).
* Blender addon 1.5.0.  Tests: 77 checks - the returned mesh has zero material
  slots, the file's material is gone, the user's own material survives, and the
  status line says `no materials`.

## v1.8.0 - 2026-09-13

One format instead of a menu of them.

* Sending is always OBJ: it carries geometry, UVs and materials without unit
  ambiguity.  STL and PLY cannot carry UVs or materials, so they were useless for
  this workflow, and FBX is what 3D-Coat hands back anyway.
* What 3D-Coat returns is read by its file extension, so there is nothing to
  configure on the way back either (the scale match covers the FBX unit factor).
* The `Format` row is gone from the Blender menu and from the 3D-Coat panel, and
  the 3D-Coat `format` setting is no longer stored.
* Blender addon 1.4.0.  Tests: Blender 74 checks (incl. an FBX return imported
  with no format setting), 3D-Coat 52 + 29 + 24.

## v1.7.0 - 2026-09-13

Scale and units: a returned model now comes back at the size it left.

* Cause: 3D-Coat exports with its own scene scale - `Scene.GetSceneScale()` is
  documented as "the length of 1 scene unit when you export the scene" - so a
  round trip can come home at a fixed multiple (x100 with FBX is the classic).
* Blender side: `send` records the model's world-space bounding-box diagonal and
  each pulled model is measured against it.  A difference bigger than 2% is scaled
  away (about the world origin, geometry only) and reported in the status as
  `scale x0.01`; the new `Match scale` toggle (on by default) can switch it off.
  Sane-guarded: factors beyond x1000 are reported but left alone.
* Both sides write the numbers to one shared log,
  `Documents/3DCoat/CoatBridge.log`: the Blender side logs the sent size and the
  correction, the 3D-Coat side logs its own `units=... scale=...` on every action,
  so a future mismatch can be read off instead of guessed.
* Tests: Blender suite 73 checks (a return that is 1.6x too big is asserted to be
  rescaled back to exactly the sent size; a same-size return is left alone; the
  toggle is exercised), 3D-Coat suite 52 + 29 + 26.

## v1.6.0 - 2026-09-13

No window at all: the bridge is now three buttons in 3D-Coat's own tool panel.

* `CoatBridge_Send.py`, `CoatBridge_Pull.py`, `CoatBridge_Setup.py`: plain scripts
  that act directly (export, import, find the folder) and report with 3D-Coat's
  own floating message.  Nothing opens: no dialog, no window, no second process.
* `tools/CoatBridgeTools.xml.in` -> `ExtraMenuItems/CoatBridgeTools.xml`: an entry
  with an empty `MenuPath` plus `inRoom`/`inSection` lands in that room's tool
  panel, so the buttons are declared by file (they survive a restart) instead of
  being injected by a run-once API call.  Voxels and Paint for now.
* Icons: `CoatBridge_Send.png` (arrow leaving a wall), `CoatBridge_Pull.png`
  (arrow arriving), `CoatBridge_Setup.png` (magnifier) in `data/Textures/icons64/`,
  grey glyphs like the shipped tool icons.
* The in-process Qt window is no longer installed (code and its 26 tests stay in
  the repo as an optional reference).  The `Scripts > Coat Bridge` entry now
  opens 3D-Coat's own native dialog, which is optional.
* Labels: 3D-Coat shows the raw id until a translation exists, so every button
  calls `addTranslation` when it runs; if the labels still read as ids, switch to
  `insertInToolset`, which labels them at injection time.
* Tests: `coat_side/tests/run_tests.sh` now also runs the tool-button suite
  (23 checks) - it runs each button headless, verifies the message, the signal
  file, the queue handling and the log, and validates the XML (ids, rooms,
  script paths).

## v1.5.0 - 2026-09-13

The 3D-Coat panel is now a Qt window inside 3D-Coat's process.

* `coat_side/CoatBridgeQt.py`: a PySide6 `QMainWindow` built the way 3D-Coat's own
  Python panels (Python Terminal, Data Tree, AI Assistant) are built.  No
  cExtension and no event loop of our own are needed: 3D-Coat's shipped `QT`
  extension already calls `app.processEvents()` every frame
  (`cModules/QT/QT.py`), so a plain script can own a live window, in the same
  process, with direct access to the `coat` API.
* The window mirrors the Blender menu: `Send to Blender`, `Pull from Blender`,
  `Format [FBX|OBJ]`, `Detect`, `Folder`, `Start Blender`, `Remove launcher`,
  plus a status/detail/hint block.  It remembers its position, starts next to the
  right-hand panel column, refreshes the status twice a second, and a second
  `Scripts > Coat Bridge` just raises the open window.
* `CoatBridge.py` was split into logic + actions and only runs when 3D-Coat runs
  it (`runpy` -> `__name__ == "<run_path>"`), so the Qt panel can import it.
  If Qt is missing, the panel falls back to the native dialog.
* Corrected an earlier claim: the dock/tab row (Layers / FPS-monitor /
  Extensions / Object Inspector) is built into 3D-Coat and cannot be extended by
  third parties - 3D-Coat's own Python panels are windows too, not tabs.
* Tests without 3D-Coat: `coat_side/tests/run_tests.sh` runs the API check, 52
  logic checks and 27 Qt checks - the Qt suite builds the real window offscreen
  on 3D-Coat's own Python and clicks every button.
* Blender side unchanged (65 checks).

## v1.4.0 - 2026-09-13

Where the 3D-Coat launcher can live, after checking every option the host offers.

* Research result, with evidence: 3D-Coat's right-hand dock column (VoxTree,
  Layers, Multires, ...) is a closed set.  `Layout.xml` names those windows and
  the Python API has no way to register another one - `ui.enableWindow()` only
  toggles built-ins, and the Qt window manager only undocks built-ins.  The
  embeddable spots are the room tool panels, the menus, the RMB panel, and
  custom rooms.
* `insertInToolset(room, "", "CoatBridge")` puts a button at the end of a room's
  tool list, with the icon `data/Textures/icons64/CoatBridge.png` (grey glyph,
  same style as the shipped tool icons) and the label from `addTranslation`.
  `TOOL_ROOMS` starts with `Voxels` so the result can be judged before adding
  more rooms.
* The panel gained `RemoveLauncher`: it calls `removeCommandFromMenu` and clears
  the record, so the injected menu entries and tool button can always be removed
  again.
* `install.sh` installs the icon too and reports when the folder is not writable.
* 3D-Coat side tests: 51 checks (`check_coat_api.py` still proves every call
  exists in the shipped stubs).  Blender side unchanged at 65 checks.

## v1.3.0 - 2026-09-13