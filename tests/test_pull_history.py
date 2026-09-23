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
addon_utils.enable('coatlink', default_set=True, persistent=False)
from coatlink import bridge, applink, receipts as receipts_module

original_acknowledge = receipts_module.acknowledge


def broken_receipt(*args, **kwargs):
    """A folder that cannot hold the receipt: read-only, or held by a sync client."""
    raise PermissionError('this folder cannot be written')
with tempfile.TemporaryDirectory(prefix='bridge_history_') as tmp:
    root = pathlib.Path(tmp)
    folder = root / 'CoatLink'
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

    # The receipt is a note to 3D-Coat, nothing more.  A folder that cannot hold it
    # must not make the same model look new again: the watcher ticks every two
    # seconds, and the pull would import the same file on every tick.
    model.write_text(model.read_text() + '# the receipt will fail for this one\n')
    signal.write_text(str(model) + '\n')
    receipts_module.acknowledge = broken_receipt
    bridge.pull(bpy.context)
    assert len(calls) == 5, 'the changed model was not imported: %r' % (calls,)
    signal.write_text(str(model) + '\n')
    bridge.pull(bpy.context)
    assert len(calls) == 5, 'a receipt that cannot be written reimports the model: %r' % (calls,)
    receipts_module.acknowledge = original_acknowledge
    print('PASS a receipt that cannot be written does not import the model twice')

    bridge._import_and_link = original
addon_utils.disable('coatlink', default_set=True)
print('PULL HISTORY REGRESSION PASSED')
