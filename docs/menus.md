# The two menus, entry by entry

Both halves are deliberate mirrors of each other: the same sections, in the same order, with
the same words.  Nothing is behind a fold-out on either side - a control you have to unfold is
the one you cannot find when it matters.  Tidiness comes from grouping instead: the remesh
settings sit in a box of their own because they are one idea, switches share a line with
switches, and anything with a droplist keeps a whole line so its text is not cut off.

| | Blender | 3D-Coat |
| --- | --- | --- |
| Where | one **CoatLink** button in the top bar - the bar holds nothing else | three buttons at the end of the room tool list (Voxels / Paint) |
| The menu | the popover inside that button | the panel opened from the tool strip |
| Actions | `Send`, `Pull` | `Send`, `Pull`, `To voxels` |
| Options | under **Send options**: `Scope`, `Import as` (voxel by default), `Remesh on send`, `Voxel size`, `Adaptivity` | the same scope droplist at the top, then reduction percentage and textures |
| Return / settings | under **Return**: `Auto receive`, `Without materials` | `Refresh info` readout (sizes, faces, voxel-or-surface, how much of the tree is still surface) |
| Below that | under **Setup**: `Axis`, `Scale (0 = auto)`, `Match scale`, `Modifiers`, `Skip dialogs`, `Detect`, `Open folder`, `Start 3D-Coat`, `Force re-read`, `Unlink selected`.  Under **Status**: the readout and `Copy details` | under **Setup**: `Detect`, `Open folder`, `Start Blender`, `Remove tool buttons`.  Then `Copy details` and the queue line |
| Source | `coatlink/` - Blender add-on, 8 files | `coat_side/CoatLinkLib.py` + three entry scripts + two XML files |

The tool-strip buttons keep their longer labels (`Send to Blender`, `Pull from Blender`)
because there they stand on their own, outside any menu; the panel's buttons say `Send` and
`Pull`, like Blender's.

The 3D-Coat panel is 3D-Coat's **own** dialog (`coat.dialog()...topRight()`), never a window
of ours and never Qt, and its controls are native too, using the layout 3D-Coat's shipped
Autoexport panel uses: `Name,[min,max]` is a number field, `Name,[#a|#b]` a droplist, `Name`
a checkbox.  Controls are labelled through 3D-Coat's own translation table, so the panel
reads `Scope`, `Reduction percent`, `Refresh info` rather than the identifiers the code uses.

## Blender menu, entry by entry

| Entry | Meaning |
| --- | --- |
| Scope | Selection (default) or every visible object |
| Import as | How 3D-Coat opens the mesh (`[vox]` by default, plus `[ppp]`, `[uv]`, `[autopo]`, …) |
| Remesh on send / Voxel size / Adaptivity | Voxel-remesh the export only; the scene is untouched |
| Send / Pull | Export the selection and queue it / take a returned model now |
| Auto receive | Watch the exchange folder every 2 s; off = manual **Pull** only |
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
| Scope | `Selected` = the node selected in the Sculpt Tree plus its children; `whole scene` = 3D-Coat's own export |
| Send / Pull | Hand a model to Blender / import the model Blender queued |
| To voxels | Convert every visible object in the tree to a voxel volume, using 3D-Coat's own S/V badge |
| Reduction percent | Removed, not kept; 0 hands the choice back to 3D-Coat's dialog |
| Refresh info | Read the current object's size, face count, voxel-or-surface state, and how much of the tree is still surface |
| Textures | Let 3D-Coat decide, force on, force off |
| Detect / Open folder / Start Blender | Exchange folder and Blender lookup |
| Remove tool buttons | Takes the runtime menu and tool entries back out |
| Copy details | Full status and paths to the clipboard (local clipboard only) |

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
