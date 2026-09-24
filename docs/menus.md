# The two menus, entry by entry

Both halves are deliberate mirrors of each other: the same sections, in the same order, with
the same words.  Both open with the two action buttons - whatever the panel was opened for,
the thing the add-on exists for is the first row - and the options that shape those buttons
follow under **Send options**, scope first.  Nothing is behind a fold-out on either side - a
control you have to unfold is the one you cannot find when it matters.  Tidiness comes from
grouping instead: the remesh settings sit in a box of their own because they are one idea,
switches share a line with switches, and anything with a droplist keeps a whole line so its
text is not cut off.

| | Blender | 3D-Coat |
| --- | --- | --- |
| Where | one **CoatLink** button in the top bar - the bar holds nothing else | three buttons at the end of the room tool list (Voxels / Paint) |
| The menu | the popover inside that button | the panel opened from the tool strip |
| Actions | the opening row: `Send`, `Pull` | the opening row: `Send`, `Pull`, then `To voxels` |
| Options | under **Send options**: `Scope`, `Import as` (voxel by default), `Send to origin`, `Remesh on send`, `Voxel size`, `Adaptivity` | the same scope droplist first, then reduction percentage and textures - nothing else, because this half hands out what the scene already holds, so where the model lands is the sending side's business |
| Return / settings | under **Return**: `Auto receive`, `Without materials`, `Replace in place`, `Shaders as materials` | nothing: no action on this side could use those switches, so the panel does not pretend otherwise.  The size / face-count / voxel-or-surface readouts are gathered for `Copy details` and the log rather than drawn as rows |
| Below that | under **Setup**: `Axis`, `Scale (0 = auto)`, `Match scale`, `Modifiers`, `Skip dialogs`, `Detect`, `Open folder`, `Start 3D-Coat`, `Force re-read`, `Unlink selected`.  Under **Status**: the readout and `Copy details` | under **Setup**: `Detect`, `Open folder`, `Start Blender`, `Remove tool buttons`.  Under **Status**: two status rows and `Copy details`, plus the queue line while something is waiting |
| Source | `coatlink/` - Blender add-on, 8 files | `coat_side/CoatLinkLib.py` + three entry scripts + two XML files |

The tool-strip buttons keep their longer labels (`Send to Blender`, `Pull from Blender`)
because there they stand on their own, outside any menu; the panel's buttons say `Send` and
`Pull`, like Blender's.

The 3D-Coat panel is 3D-Coat's **own** dialog (`coat.dialog()...topRight()`), never a window
of ours and never Qt, and its controls are native too, using the layout 3D-Coat's shipped
Autoexport panel uses: `Name,[min,max]` is a number field, `Name,[#a|#b]` a droplist, `Name`
a checkbox.  Controls are labelled through 3D-Coat's own translation table, so the panel
reads `Scope`, `Reduction percent`, `Textures` rather than the identifiers the code uses.

The panel draws the controls and one status line; the readouts it used to add - model size,
face count, voxel-or-surface state, how much of the tree is still surface - are kept in
`Copy details` and the log.  They are diagnostics, and a diagnostics dump on screen made the
two halves read differently when what they do is the same.

The Blender menu groups those same sections as **fold-out headers** (Blender's own popovers
do it this way): a small header per section, and the body drawn only while it is open.
`Send options`, `Return` and `Status` start open and `Setup` starts folded - folding is for
putting a long tail away, never for the readout an error has to stay visible in. 3D-Coat's
panel format has no fold, so that side stays one page with the same headings in the same
order; folding is not what makes them the same, the words and the order are.

## Blender menu, entry by entry

| Entry | Meaning |
| --- | --- |
| Send / Pull | The opening row: export the selection and queue it / take a returned model now |
| Scope | Selection (default) or every visible object |
| Import as | How 3D-Coat opens the mesh (`[vox]` by default, plus `[ppp]`, `[uv]`, `[autopo]`, …) |
| Send to origin | Off by default: send the model to 3D-Coat's world origin instead of from where it sits here.  The active object's own origin becomes `0,0,0`, the rest of the selection keeps its offset from it, and a model that comes back still lands where it was sent from |
| Remesh on send / Voxel size / Adaptivity | Voxel-remesh the export only; the scene is untouched |
| Auto receive | Watch the exchange folder every 2 s; off = manual **Pull** only |
| Replace in place | On by default: a return takes the place of the object the send came from - same name, materials and position, new geometry.  Off, it arrives as an object of its own and nothing already in the scene is written over |
| Shaders as materials | On by default: give each returning object a material named after the 3D-Coat shader it was sent with, filled in from that shader preset's own stored values.  The look cannot come with it - a sculpt shader is 3D-Coat's display shading - and a material you made yourself is never written over |
| Without materials | A pulled model arrives as bare geometry |
| Axis / Scale | Read from 3D-Coat, or forced |
| Match scale | Keep the recorded size when a pulled model comes back at another size |
| Modifiers | Export evaluated meshes |
| Skip dialogs | Let 3D-Coat import and export with its current settings |
| Detect / Open folder | Find the exchange folder and prepare the AppLink folder / open it |
| Start 3D-Coat | Launch 3D-Coat so it picks up the queued import |
| Force re-read | Pull the last return model again, ignoring the pull record |
| Unlink selected | Stop tracking, so the next pull becomes a new object |
| Copy details | Put the full status and the diagnostic paths on the clipboard (local clipboard only) |

## 3D-Coat panel, entry by entry

| Entry | Meaning |
| --- | --- |
| Send / Pull | The opening row: hand a model to Blender / import the model Blender queued |
| Scope | `Selected` = the nodes selected in the Sculpt Tree plus their children; `whole scene` = 3D-Coat's own export |
| To voxels | Convert every visible object in the tree to a voxel volume, using 3D-Coat's own S/V badge |
| Reduction percent | Removed, not kept; 0 hands the choice back to 3D-Coat's dialog |
| Textures | Off out of the box, so the texture files stay out of the exchange folder; `textures on` lets it write them |
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
