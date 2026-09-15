# Changelog

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