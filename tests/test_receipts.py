import importlib.util
from pathlib import Path
import tempfile
spec = importlib.util.spec_from_file_location('receipts', Path(__file__).resolve().parents[1] / 'coat_bridge' / 'receipts.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
with tempfile.TemporaryDirectory() as tmp:
    path = str(Path(tmp) / 'bridge.obj')
    Path(path).write_text('first')
    version = m.fingerprint(path)
    assert m.received(path, 'blender') is None
    assert not m.acknowledge(path, 'blender', version, [])
    assert m.acknowledge(path, 'blender', version, ['Hull', 'Turret'])
    assert m.received(path, 'blender')['objects'] == ['Hull', 'Turret']
    assert m.received(path, '3dcoat') is None
    Path(path).write_text('second')
    assert m.received(path, 'blender') is None
    assert not m.acknowledge(path, 'blender', version, ['Hull'])
print('PASS receipt requires successful objects, correct receiver and unchanged model version')
