"""Real Blender regression: recover without rewriting export.txt."""
import pathlib
import sys
import tempfile
import bpy
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import coat_bridge
import addon_utils
addon_utils.enable('coat_bridge', default_set=True, persistent=False)
from coat_bridge import bridge, applink
with tempfile.TemporaryDirectory(prefix='bridge_retry_') as tmp:
    root = pathlib.Path(tmp)
    folder = root / 'BlenderBridge'
    folder.mkdir()
    model = folder / 'bridge.obj'
    signal = folder / 'export.txt'
    applink._documents_bases = lambda: [tmp]
    applink.exchange_roots = lambda *args: [tmp]
    signal.write_text(str(model) + '\n')
    stamp = signal.stat().st_mtime_ns
    bridge.STATE['target'] = None
    result = bridge.pull(bpy.context)
    assert any('missing' in msg for msg in result), result
    assert signal.exists()
    assert str(signal) not in bridge.STATE['seen']
    model.write_text('o incoming\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n')
    assert signal.stat().st_mtime_ns == stamp
    result = bridge.pull(bpy.context)
    assert any('Pulled' in msg for msg in result), result
    assert not signal.exists()
    print('PASS missing model arrives later: automatic pull recovers with unchanged signal')
    signal.write_text(str(model) + '\n')
    original = bridge._import_and_link
    def fail(*args):
        raise RuntimeError('simulated temporary file access failure')
    bridge._import_and_link = fail
    result = bridge.pull(bpy.context)
    assert any('import failed' in msg for msg in result)
    assert signal.exists()
    bridge._import_and_link = original
    result = bridge.pull(bpy.context)
    assert any('Pulled' in msg for msg in result), result
    assert not signal.exists()
    print('PASS transient import failure retries successfully without new export')
addon_utils.disable('coat_bridge', default_set=True)
print('RETRY REGRESSION PASSED')
