"""Run inside 3D-Coat. Read current subtree; write only a temp export/report.
Does not alter selection, geometry, user settings or bridge signals.
"""
import json
import os
import sys
import tempfile
import traceback
import coat
sys.path.insert(0, r'D:\home\Documents\Blender\BlenderCoatBridge\coat_side')
from CoatBridgeScopedExport import export_subtree
folder = tempfile.mkdtemp(prefix='coat_subtree_probe_')
path = os.path.join(folder, 'subtree.obj')
report = {'export': path, 'scope': 'current node + descendants', 'reduction': 0}
try:
    current = coat.Scene.current()
    report['selected_name'] = current.name()
    report['scene_units'] = str(coat.Scene.GetSceneUnits())
    report['scene_scale'] = float(coat.Scene.GetSceneScale())
    names, faces = export_subtree(coat, path, 0)
    report['objects'] = names
    report['faces_api'] = faces
    report['groups'] = []
    low = [float('inf')] * 3
    high = [float('-inf')] * 3
    vertices = faces_file = 0
    with open(path, encoding='utf-8', errors='replace') as stream:
        for line in stream:
            if line.startswith(('o ', 'g ')):
                report['groups'].append(line.strip())
            elif line.startswith('v '):
                values = list(map(float, line.split()[1:4]))
                for i in range(3):
                    low[i] = min(low[i], values[i])
                    high[i] = max(high[i], values[i])
                vertices += 1
            elif line.startswith('f '):
                faces_file += 1
    report.update(vertices=vertices, faces_file=faces_file,
                  bounds_min=low, bounds_max=high, success=True)
except Exception:
    report.update(success=False, traceback=traceback.format_exc())
report_path = os.path.join(os.environ.get('LOCALAPPDATA', tempfile.gettempdir()), 'Temp', 'CoatBridge-subtree-probe.json')
os.makedirs(os.path.dirname(report_path), exist_ok=True)
with open(report_path, 'w', encoding='utf-8') as stream:
    json.dump(report, stream, indent=2, ensure_ascii=False)
print(json.dumps(report, indent=2, ensure_ascii=False))
print('Report:', report_path)
