# The two menus, entry by entry

Both halves are deliberate mirrors of each other: the same sections, in the same order, with
the same words.  Both open with the two action buttons - whatever the panel was opened for,
the thing the add-on exists for is the first row - and the options that shape those buttons
follow under **Export options**, export range first.  Nothing is behind a fold-out on either side - a
control you have to unfold is the one you cannot find when it matters.  Tidiness comes from
grouping instead: the remesh settings sit in a box of their own because they are one idea,
switches share a line with switches, and anything with a droplist keeps a whole line so its
text is not cut off.

| | Blender | 3D-Coat |
| --- | --- | --- |
| Where | one **CoatLink** button in the top bar - the bar holds nothing else | three buttons at the end of the room tool list (Voxels / Paint) |
| The menu | the popover inside that button | the panel opened from the tool strip |
| Actions | the opening row: `Export`, `Import` | the opening row: `Export`, `Import` |
| Options | under **Export options**: `Export range`, `Import as` (voxel by default), `Send to origin`, `Remesh on send`, `Voxel size`, `Adaptivity` | the same export-range droplist first, then the reduction percentage - nothing else, because this half hands out what the scene already holds, so where the model lands is the sending side's business |
| Import | under **Import options**: `Auto receive`, `Without materials`, `Replace in place`, `Shaders as materials` | under **Import options**: `Selected To Voxel`.  Shaders as materials?  Nothing of the sort exists here - what came back is what this action is about: it converts the volumes you selected (and their children) to voxels, which is the one thing 3D-Coat does to a model after Blender hands it over |
| Below that | under **Setup**: `Axis`, `Scale (0 = auto)`, `Match scale`, `Modifiers`, `Skip dialogs`, `Detect`, `Open folder`, `Start 3D-Coat`, `Force re-read`, `Unlink selected`.  Under **Status**: the readout and `Copy details` | under **Setup**: `Detect`, `Open folder`, `Start Blender`, `Remove tool buttons`.  Under **Status**: everything about the objects (size, face count, voxel-or-surface, how much of the tree is still surface), then the last action, `Copy details`, and the queue line while something is waiting |
| Source | `coatlink/` - Blender add-on, 8 files | `coat_side/CoatLinkLib.py` + three entry scripts + two XML files |

The tool-strip buttons keep their longer labels (`Export to Blender`, `Import from Blender`)
because there they stand on their own, outside any menu; the panel's buttons say `Export` and
`Import`, like Blender's.

The 3D-Coat panel is 3D-Coat's **own** dialog (`coat.dialog()...topRight()`), never a window
of ours and never Qt, and its controls are native too, using the layout 3D-Coat's shipped
Autoexport panel uses: `Name,[min,max]` is a number field, `Name,[#a|#b]` a droplist, `Name`
a checkbox.  Controls are labelled through 3D-Coat's own translation table, so the panel
reads `Export range`, `Reduction percent` rather than the identifiers the code uses.

Nothing on the panel explains a control in fine print: the labels say what they do, and the
words and the order of the sections are what make the two halves read as one product.  What
this side has to say about the objects themselves - size, face count, voxel-or-surface, how
much of the tree is still surface - is drawn in **Status**, next to the last action, and
`Copy details` carries all of it plus the paths.

The Blender menu groups those same sections as **fold-out headers** (Blender's own popovers
do it this way): a small header per section, and the body drawn only while it is open.
`Export options`, `Import options` and `Status` start open and `Setup` starts folded - folding is for
putting a long tail away, never for the readout an error has to stay visible in. 3D-Coat's
panel format has no fold, so that side stays one page with the same headings in the same
order; folding is not what makes them the same, the words and the order are.

## Blender menu, entry by entry

| Entry | Meaning |
| --- | --- |
| Export / Import | The opening row: export the selection and queue it / take a returned model now |
| Export range | `Selected objects` (default) or `Visible objects` |
| Import as | How 3D-Coat opens the mesh (`[vox]` by default, plus `[ppp]`, `[uv]`, `[autopo]`, …) |
| Send to origin | Off by default: send the model to 3D-Coat's world origin instead of from where it sits here.  The active object's own origin becomes `0,0,0`, the rest of the selection keeps its offset from it, and a model that comes back still lands where it was sent from |
| Remesh on send / Voxel size / Adaptivity | Voxel-remesh the export only; the scene is untouched |
| Auto receive | Watch the exchange folder every 2 s; off = manual **Import** only |
| Replace in place | On by default: a return takes the place of the object the send came from - same name, materials and position, new geometry.  Off, it arrives as an object of its own and nothing already in the scene is written over |
| Shaders as materials | On by default: give each returning object a material named after the 3D-Coat shader it was sent with, filled in from that shader preset's own stored values.  The look cannot come with it - a sculpt shader is 3D-Coat's display shading - and a material you made yourself is never written over |
| Without materials | A pulled model arrives as bare geometry |
| Axis / Scale | Read from 3D-Coat, or forced |
| Match scale | Keep the recorded size when a pulled model comes back at another size |
| Modifiers | Export evaluated meshes |
| Skip dialogs | Let 3D-Coat import and export with its current settings |
| Detect / Open folder | Find the exchange folder and prepare the AppLink folder / open it |
| Start 3D-Coat | Launch 3D-Coat so it picks up the queued import |
| Force re-read | Import the last return model again, ignoring the pull record |
| Unlink selected | Stop tracking, so the next pull becomes a new object |
| Copy details | Put the full status and the diagnostic paths on the clipboard (local clipboard only) |

## 3D-Coat panel, entry by entry

| Entry | Meaning |
| --- | --- |
| Export / Import | The opening row: hand a model to Blender / import the model Blender queued |
| Export range | `Selected objects` = the nodes selected in the Sculpt Tree plus their children; `Visible objects` = 3D-Coat's own export |
| Selected To Voxel | Convert the selected volumes (and their children) to voxels, using 3D-Coat's own S/V badge.  With nothing selected the current node stands in and the status line says so |
| Reduction percent | Removed, not kept; 0 hands the choice back to 3D-Coat's dialog |
| Textures | Removed.  The sculpt export has no UVs for a texture to land on and nothing on the Blender side read the files, so the switch only made the exchange folder heavier.  Every export now answers 3D-Coat's own dialog explicitly (no textures), so the folder no longer depends on what that dialog was left at |
| Detect / Open folder / Start Blender | Exchange folder and Blender lookup |
| Remove tool buttons | Takes the runtime menu and tool entries back out |
| Copy details | Full status, the size / face-count / voxel-or-surface readouts and the paths to the clipboard (local clipboard only) |

## Where the 3D-Coat panel can live (and where it cannot)

| Spot | Works | How |
| --- | --- | --- |
| Viewport top-right, non-modal panel | yes | `coat.dialog().noModal().topRight().width()` |
| Room tool panel (a real button in a panel, with icon) | yes | `ui.insertInToolset(room, section, toolID)`, or the shipped XML |
| Main menus (24 places: File, Edit, View, Windows, Scripts, Voxels, Retopo, Bake, Layers, Textures, …) | yes | `ui.insertInMenu()` or `ExtraMenuItems/*.xml` |
| Room RMB panel | yes | `coat.start_rmb_panel()` / the room's `RMBMenu.py` |
| Whole custom workspace | yes | `Documents/3DCoat/UserPrefs/Rooms/CustomRooms/<ID>/` |
| Space-panel buttons | no | `show_space_panel("*Subset")` only takes built-in subsets |
| **Right-hand dock column (VoxTree / Layers / Multires / …)** | **no** | those are built-in window ids in each room's `Layout.xml`; the Python API has no call to register a window, `ui.enableWindow()` only toggles built-ins, and the Qt manager only undocks built-ins |
