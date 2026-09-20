# The installation doors, installing by hand, and explicit paths

Every door runs the same installer; they differ only in what they fetch and how they start:

| Door | What the user does | Needs |
| --- | --- | --- |
| `CoatLink-Setup.cmd` | downloads it, double-clicks | Windows, `curl` (built in since Windows 10) |
| `install.cmd` | unzips the release, double-clicks | Windows |
| `CoatLink-Setup.py` | downloads it, pastes one line into **Scripts > Show Python console** | nothing else - 3D-Coat's own Python runs it |
| one console line | pastes the URL line from the [README](../README.md) | an internet connection |
| `install.sh` / `install.ps1` | runs it in a shell (PowerShell does both halves) | bash, or Windows PowerShell |

**Why there is no `.3dcpack`:** 3D-Coat's own extension packs are the neatest idea, and they were
measured rather than guessed at.  A pack installs files relative to 3D-Coat's user folder, but
every `ExtraMenuItems` XML needs an **absolute** script path - `%USERPROFILE%\…`, `~/…` and even
`Scripts/…` relative to the user folder all fail in a live 3D-Coat - and a pack cannot register an
extension either, because a `cExtension` folder that is not listed in
`cExtensions/startup.txt` is not loaded, and a pack can only replace that file.  A pack would
therefore end with "now run this script once": one step *more* than `CoatLink-Setup.cmd`.

The rest of this page is for the case where you would rather place the files yourself, or where
automatic detection needs help.

## The five destinations

`<ver>` is your Blender version folder.

| What | From | To |
| --- | --- | --- |
| Blender add-on | `coat_bridge\` (8 `.py` files) | `%APPDATA%\Blender Foundation\Blender\<ver>\scripts\addons\coat_bridge\` |
| 3D-Coat scripts | `coat_side\CoatBridge*.py` (6 files: the library, the receipts helper, the scoped-export helper and the three entries) | `%USERPROFILE%\Documents\3DCoat\UserPrefs\Scripts\CoatBridge\` |
| Tool buttons | `coat_side\tools\CoatBridgeTools.xml.in` | `…\Scripts\ExtraMenuItems\CoatBridgeTools.xml`, with every `__SCRIPT_DIR__` replaced by the `CoatBridge` folder above, forward slashes (`C:/Users/…/CoatBridge`) |
| Scripts menu entry | the block below | `…\Scripts\ExtraMenuItems\CoatBridge.xml` |
| Button icons (optional) | `coat_side\icon\*.png` (4 files) | `<3D-Coat program folder>\data\Textures\icons64\` |

`CoatBridge.xml`, verbatim, with the same forward-slash path:

```xml
<ClassArray.ExtraMenuItem>
	<ExtraMenuItem>
		<MenuPath>Scripts</MenuPath>
		<MenuItem>CoatBridge</MenuItem>
		<inRoom></inRoom>
		<inSection></inSection>
		<Command>script:C:/Users/you/Documents/3DCoat/UserPrefs/Scripts/CoatBridge/CoatBridge_Setup.py</Command>
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

## Uninstalling

`install.cmd --uninstall`, `.\install.ps1 -Uninstall`, `./install.sh --uninstall` or
`python coat_side/CoatLinkInstall.py --uninstall` (the one double-click downloader only
installs; use one of these to take it out again).

It removes its own scripts, its two XML files and the icons it added, clears the launcher
record it wrote into 3D-Coat's `CoatBridge.json` (leaving your panel settings in that file
alone), and deletes nothing else.  Files another extension or you put in the same folders are
left untouched - a test asserts exactly that.
