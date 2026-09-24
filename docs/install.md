# The installation doors, installing by hand, and explicit paths

The 3D-Coat half is installed by 3D-Coat itself, from its own package format; the Blender half is
installed by Blender.  Both also have a command-line door, for when that is easier:

| Door | What the user does | Needs |
| --- | --- | --- |
| `CoatLink-<version>.3dcpack` | **Scripts > Install Extension** in 3D-Coat, then tick **CoatLink** once under **Windows > Panels > Extensions** and restart | 3D-Coat alone: nothing to unzip, no shell, no elevation |
| `install.cmd` | double-clicks it, in a checkout or GitHub's source archive | Windows |
| `install.sh` / `install.ps1` | runs it in a shell (PowerShell does both halves) | bash, or Windows PowerShell |

**Why the pack needs that one tick:** a pack installs files relative to 3D-Coat's user folder, but
every `ExtraMenuItems` XML needs an **absolute** script path - `%USERPROFILE%\…`, `~/…` and even
`Scripts/…` relative to the user folder all fail in a live 3D-Coat - and a pack cannot register an
extension either: a `cExtension` folder that is not listed in `cExtensions/startup.txt` is not
loaded, and a pack can only replace that file, never add a line to it.  So the extension writes
its own two XML files the first time 3D-Coat starts it, and the tick in the Extensions panel is the
one step no package can do on your behalf.  Every door ends in the same folder, so switching
between them changes nothing.

The rest of this page is for the case where you would rather place the files yourself, or where
automatic detection needs help.

## The five destinations

`<ver>` is your Blender version folder, and `<Documents>` is Windows' own Documents folder - not
always `%USERPROFILE%\Documents`: redirect Documents to OneDrive and 3D-Coat (data, and the Python
it ships) moves with it.

| What | From | To |
| --- | --- | --- |
| Blender add-on | `coatlink\` (8 `.py` files) | `%APPDATA%\Blender Foundation\Blender\<ver>\scripts\addons\coatlink\` |
| 3D-Coat extension | `coat_side\CoatLink.py`, `CoatLinkLib.py`, `CoatLinkMenu.py`, `CoatLinkReceipts.py`, `CoatLinkScopedExport.py` and the three entry scripts (8 files - exactly what `SCRIPT_FILES` lists, and what the `.3dcpack` carries) | `<Documents>\3DCoat\UserPrefs\Scripts\cExtensions\CoatLink\` |
| The startup line | - | `…\Scripts\cExtensions\startup.txt`, one added line: `CoatLink` (a copy of the original is kept as `startup.txt.bak`) |
| Menu entry and tool buttons | - | the entry is inserted into 3D-Coat's own menu list; `…\Scripts\ExtraMenuItems\CoatLinkTools.xml` (tool buttons), written by the extension itself on its first start: the `Command` entries carry absolute paths, so they cannot be shipped |

An earlier build called everything `CoatBridge` / `coat_bridge`: the add-on folder, the 3D-Coat
scripts folder (now `Scripts\CoatLink`), the exchange folder (now `<exchange>\CoatLink`), the
shared log and state file (now `CoatLink.log` / `CoatLink.json`) and the tool and menu ids (now
`CoatLink_*`).  Both installers clear the old name away: `install.sh` / `install.ps1` move the
old `coat_bridge` add-on folder to `<scripts>\coat_bridge.removed-<timestamp>`, and the 3D-Coat
installer moves `Scripts\CoatBridge` to `Scripts\CoatBridge.removed` and deletes the old
`CoatBridge.xml` / `CoatBridgeTools.xml` — that deletion is what takes the old tool buttons
away.  Installing the add-on by hand from the zip instead?  Delete the `coat_bridge` folder
yourself, so Blender's list shows one CoatLink and not two.

`CoatLink.xml`, verbatim, with the same forward-slash path:

```xml
<ClassArray.ExtraMenuItem>
	<ExtraMenuItem>
		<MenuPath>Scripts</MenuPath>
		<MenuItem>CoatLink</MenuItem>
		<inRoom></inRoom>
		<inSection></inSection>
		<Command>script:C:/Users/you/Documents/3DCoat/UserPrefs/Scripts/CoatLink/CoatLink_Setup.py</Command>
	</ExtraMenuItem>
</ClassArray.ExtraMenuItem>
```

Then start Blender, enable **CoatLink** and press **Detect**.

The two XML files are the fiddly part - every path in them has to be yours - so
`python coat_side/CoatLinkInstall.py` will write both for you once the scripts are in place.

## Explicit paths

When detection is not enough:

* PowerShell: `-BlenderAddons`, `-CoatScripts`, `-CoatDir`, plus `-BlenderOnly` / `-CoatOnly`
  for one half
* bash: the same three in that order, or `BLENDER_ADDON_DIR`, `COAT_SCRIPTS_DIR`, `COAT_DIR`
* Python: `--scripts`, `--coat`, `--uninstall`

### When the folders are somewhere else

Nothing is hardcoded.  The program folder comes from the uninstall entries Windows keeps (so an
install in a folder of your own, on any drive, is found), the Program Files folders this system
actually spells are read from the environment, every drive is looked at, and per-user `AppData`
installs are covered.  The user folder follows Windows' own Documents folder, and the folder
name under it is matched rather than assumed - 3D-Coat names it after the version on recent
builds (`3DCoat2025`, `3DCoat2026`) and carried a hyphen in the 4.x line (`3D-CoatV48`).  The
same matching is used for the Python 3D-Coat ships, so a versioned data folder does not hide
it.  Only folders that really hold 3D-Coat data count (`UserPrefs` or `Scripts` inside), which
is what keeps a Documents folder that merely contains a `3DCoat` folder - one this bridge
wrote its own log into - from being mistaken for 3D-Coat's.

A `python.exe` on `PATH` may be the Windows Store stub, which opens the Store and runs
nothing; the doors refuse that path and any candidate that cannot actually run, instead of
quietly doing nothing.

For what is left, four environment variables - and the `.cmd` doors read them too, so a
double-click needs no arguments:

* `COATLINK_DOCS` - the Documents folder, when Windows' answer is not where 3D-Coat's data is
* `COATLINK_PYTHON` - the Python to run the installer with, when 3D-Coat's own is not found
* `COATLINK_COAT_DIR` (or `COAT_DIR`) - the 3D-Coat program folder, for the button icons
* `COATLINK_PREFS` - the user folder outright, e.g. `D:\3DCoat-User\3DCoat\UserPrefs`

## Uninstalling

`install.cmd --uninstall`, `.\install.ps1 -Uninstall`, `./install.sh --uninstall` or
`python coat_side/CoatLinkInstall.py --uninstall` (the one double-click downloader only
installs; use one of these to take it out again).

It removes its own scripts, its two XML files and the icons it added, clears the launcher
record it wrote into 3D-Coat's `CoatLink.json` (leaving your panel settings in that file
alone), and deletes nothing else.  Files another extension or you put in the same folders are
left untouched - a test asserts exactly that.
