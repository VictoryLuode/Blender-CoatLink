import pathlib, sys, tempfile
import bpy, addon_utils
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
addon_utils.enable('coatlink', default_set=True, persistent=False)
from coatlink import bridge, applink
with tempfile.TemporaryDirectory() as tmp:
    applink._documents_bases = lambda: [tmp]
    bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
    targets = []
    for name in ('Hull', 'Turret'):
        bpy.ops.mesh.primitive_cube_add()
        obj = bpy.context.object; obj.name = name
        obj['coatlink_source_name'] = name
        targets.append(obj)
    targets[0].name = 'HullRenamed'
    bpy.ops.mesh.primitive_cube_add()
    unrelated = bpy.context.object; unrelated.name = 'NewPart'
    path = pathlib.Path(tmp)/'bridge.obj'
    path.write_text('v 0 0 0\nv 1 0 0\nv 0 1 0\ng Turret\nf 1 2 3\ng Hull\nf 1 2 3\ng NewPart\nf 1 2 3\n')
    bridge.STATE['target'] = None
    names = bridge._import_and_link(bpy.context, str(path))
    assert all(len(o.data.polygons)==1 for o in targets), names
    assert targets[0].name == 'HullRenamed'
    assert len(unrelated.data.polygons)==6
    assert len(bpy.data.objects)==4
    print('PASS reversed return order maps each object; rename survives; unrelated collision preserved:', names)
addon_utils.disable('coatlink', default_set=True)
print("OBJECT NAME REGRESSION PASSED")
