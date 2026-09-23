"""Run with Blender --background --factory-startup --python this_file."""
import pathlib
import sys
import tempfile
import bpy

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import coatlink
coatlink.register()
from coatlink import bridge, applink

with tempfile.TemporaryDirectory(prefix='bridge_identity_') as tmp:
    applink._documents_bases = lambda: [tmp]
    path = pathlib.Path(tmp) / 'bridge.obj'
    path.write_text('o bridge\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n')
    for missing in (None, 'deleted_target'):
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        bridge.STATE['target'] = {'object': missing}
        names = bridge._import_and_link(bpy.context, str(path))
        assert names == ['bridge'], names
        assert len(bpy.data.objects['bridge'].data.vertices) == 3
        original = bpy.data.objects['bridge'].as_pointer()
        names = bridge._import_and_link(bpy.context, str(path))
        assert bpy.data.objects['bridge'].as_pointer() == original
        assert len(bpy.data.objects) == 1
        print('PASS missing target', missing, ': first import survives; repeat preserves identity')
coatlink.unregister()
print('TARGET IDENTITY REGRESSION PASSED')
