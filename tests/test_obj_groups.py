import pathlib
import sys
import tempfile
import bpy
import addon_utils
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
addon_utils.enable('coatlink', default_set=True, persistent=False)
from coatlink import bridge, applink
with tempfile.TemporaryDirectory(prefix='bridge_groups_') as tmp:
    applink._documents_bases = lambda: [tmp]
    path = pathlib.Path(tmp) / 'bridge.obj'
    path.write_text('v 0 0 0\nv 1 0 0\nv 0 1 0\nv 3 0 0\nv 4 0 0\nv 3 1 0\ng Hull\nf 1 2 3\ng Turret\nf 4 5 6\n')
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    bridge.STATE['target'] = None
    names = bridge._import_and_link(bpy.context, str(path))
    meshes = [o for o in bpy.data.objects if o.type == 'MESH']
    assert len(meshes) == 2, names
    assert sorted(len(o.data.polygons) for o in meshes) == [1, 1]
    print('PASS distinct OBJ groups imported as separate objects:', names)
addon_utils.disable('coatlink', default_set=True)
print('OBJ GROUP REGRESSION PASSED')
