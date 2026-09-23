"""Run inside 3D-Coat Python console using exec(open(path).read()).
Read-only: does not export, reduce, select, transform or confirm any dialog.
"""
import json
import os
import coat
report = {'purpose': 'read-only reduction diagnostics', 'export_verified': False}
try:
    report['current_room'] = coat.ui.currentRoom()
    report['selected_polygons'] = coat.Scene.current().Volume().getPolycount()
except Exception as exc:
    report['selection_error'] = str(exc)
field = '$DecimationParams::ReductionPercent'
try:
    report['reduction_control_present'] = bool(coat.ui.presentInUI(field))
    if report['reduction_control_present']:
        report['reduction_value'] = coat.ui.getSliderValue(field)
except Exception as exc:
    report['control_error'] = str(exc)
path = os.path.join(os.path.expanduser('~'), 'Documents', '3DCoat', 'CoatLink-reduction-diagnostic.json')
with open(path, 'w', encoding='utf-8') as stream:
    json.dump(report, stream, ensure_ascii=False, indent=2)
print(json.dumps(report, ensure_ascii=False, indent=2))
print(path)
