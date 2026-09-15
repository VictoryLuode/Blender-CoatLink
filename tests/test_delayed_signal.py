"""Real Blender: delayed mirrored signals do not reimport unchanged geometry."""
import pathlib
import sys
import tempfile
import bpy
import addon_utils
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
addon_utils.enable('coat_bridge', default_set=True, persistent=False)
from coat_bridge import bridge, applink
with tempfile.TemporaryDirectory(prefix='bridge_delayed_') as tmp:
    root = pathlib.Path(tmp)
    folder = root / 'BlenderBridge'
    folder.mkdir()
    model = folder / 'bridge.obj'
    signal = folder / 'export.txt'
    mirror = root / 'export.txt'
    applink._documents_bases = lambda: [tmp]
    applink.exchange_roots = lambda *args: [tmp]
    model.write_text('o bridge\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n')
    calls = []
    original = bridge._import_and_link
    def counted(*args):
        calls.append(args[1])
        return original(*args)
    bridge._import_and_link = counted
    signal.write_text(str(model) + '\n')
    bridge.pull(bpy.context)
    assert len(calls) == 1
    mirror.write_text(str(model) + '\n')
    bridge.pull(bpy.context)
    assert len(calls) == 1 and not mirror.exists()
    print('PASS delayed mirror does not import twice')
    model.write_text(model.read_text() + '# updated export\n')
    mirror.write_text(str(model) + '\n')
    bridge.pull(bpy.context)
    assert len(calls) == 2 and not mirror.exists()
    print('PASS updated fixed-name model imports normally')
    mirror.write_text(str(model) + '\n')
    bridge.pull(bpy.context, force=True)
    assert len(calls) == 3
    print('PASS explicit manual pull can reimport unchanged model')
    bridge._import_and_link = original
addon_utils.disable('coat_bridge', default_set=True)
print('DELAYED SIGNAL REGRESSION PASSED')
