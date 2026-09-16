"""Real Blender: restarting Blender must not reimport what it already imported.

The return file keeps sitting in the exchange folder after a successful pull (only
the signal is removed), so an in-memory record alone means the next session sees a
fresh-looking export and imports the same model a second time.
"""
import pathlib
import sys
import tempfile
import bpy
import addon_utils
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
addon_utils.enable('coat_bridge', default_set=True, persistent=False)
from coat_bridge import bridge, applink
with tempfile.TemporaryDirectory(prefix='bridge_history_') as tmp:
    root = pathlib.Path(tmp)
    folder = root / 'BlenderBridge'
    folder.mkdir()
    model = folder / 'bridge.obj'
    signal = folder / 'export.txt'
    applink._documents_bases = lambda: [tmp]
    applink.exchange_roots = lambda *args: [tmp]
    model.write_text('o bridge\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n')
    calls = []
    original = bridge._import_and_link

    def counted(*args):
        calls.append(args[1])
        return original(*args)

    bridge._import_and_link = counted
    prefs = bridge.prefs(bpy.context)

    signal.write_text(str(model) + '\n')
    bridge.pull(bpy.context)
    assert len(calls) == 1, calls
    history = folder / bridge.HISTORY_NAME
    assert history.is_file(), 'no pull record was written'
    print('PASS first pull imports and records the file version')

    # a new session: same process, but every in-memory trace dropped
    for key in ('seen', 'imported_versions'):
        bridge.STATE[key].clear()
    bridge._HISTORY_LOADED[0] = False
    signal.write_text(str(model) + '\n')
    bridge.load_history(prefs)
    assert bridge.STATE['imported_versions'], 'the record did not come back'
    bridge.pull(bpy.context)
    assert len(calls) == 1, 'a restart reimported the same file: %r' % (calls,)
    print('PASS a fresh session does not reimport the unchanged return file')

    # a real new export must still come through
    model.write_text(model.read_text() + '# updated in 3D-Coat\n')
    signal.write_text(str(model) + '\n')
    bridge.pull(bpy.context)
    assert len(calls) == 2, calls
    print('PASS a newer version of the file is imported')

    # and the manual pull still overrides the record
    signal.write_text(str(model) + '\n')
    bridge.pull(bpy.context, force=True)
    assert len(calls) == 3, calls
    print('PASS an explicit pull can reimport the same version on purpose')

    # a damaged record must not stop a pull
    history.write_text('{ not json')
    for key in ('seen', 'imported_versions'):
        bridge.STATE[key].clear()
    bridge._HISTORY_LOADED[0] = False
    signal.write_text(str(model) + '\n')
    bridge.pull(bpy.context)
    assert len(calls) == 4, calls
    print('PASS a damaged record falls back to importing normally')
    bridge._import_and_link = original
addon_utils.disable('coat_bridge', default_set=True)
print('PULL HISTORY REGRESSION PASSED')
