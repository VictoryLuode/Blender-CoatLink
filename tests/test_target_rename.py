"""Real Blender: the AppLink target was renamed, and the old name has to let go.

3D-Coat lists a folder in File > Export To because of the run.txt marker inside it,
not because of the folder's name (measured: a folder renamed to *.removed while
keeping its marker is still listed).  So the rename has two halves, and both need a
test: the new name is what gets published, and the old one stops being published -
without stranding a model 3D-Coat handed back before the rename, or the record that
says it was imported already.
"""
import json
import os
import pathlib
import sys
import tempfile
import bpy
import addon_utils
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
addon_utils.enable('coatlink', default_set=True, persistent=False)
from coatlink import bridge, applink

with tempfile.TemporaryDirectory(prefix='bridge_rename_') as tmp:
    old_name = applink.LEGACY_APP_FOLDERS[0]
    legacy = pathlib.Path(tmp) / old_name
    legacy.mkdir()
    (legacy / 'run.txt').write_text('')          # what makes 3D-Coat list the name
    model = legacy / 'bridge.obj'
    model.write_text('o bridge\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n')
    signal = legacy / 'export.txt'
    signal.write_text(str(model) + '\n')

    applink._documents_bases = lambda: [tmp]
    applink.exchange_roots = lambda *args: [tmp]
    prefs = bridge.prefs(bpy.context)

    folder = pathlib.Path(applink.ensure_app_folder(tmp))
    assert folder.name == applink.APP_FOLDER, folder
    assert (folder / 'run.txt').is_file(), 'the new target is not published'
    print('PASS the target 3D-Coat lists is named', applink.APP_FOLDER)

    assert not (legacy / 'run.txt').is_file(), 'the old target is still published'
    assert legacy.is_dir() and model.is_file(), 'retiring the name took files with it'
    print('PASS the old name is retired, the folder and its files stay')

    assert applink.is_our_folder(str(model), [tmp]), 'a model in the old folder is refused'
    assert str(signal) in applink.signal_files([tmp]), 'the old signal is not watched'
    print('PASS a return announced under the old name is still ours')

    # The record from before the rename must come along: it is what stops the same
    # returned file being imported a second time now that the folders changed.
    stat = os.stat(model)
    key = os.path.normcase(os.path.realpath(model))
    (legacy / bridge.HISTORY_NAME).write_text(json.dumps(
        {'seen': {str(signal): 1.0},
         'imported_versions': {key: [stat.st_mtime_ns, stat.st_size]}}))
    history = pathlib.Path(bridge._history_path(prefs))
    assert history.parent.name == applink.APP_FOLDER, history
    assert history.is_file(), 'the pull record was left behind'
    assert not (legacy / bridge.HISTORY_NAME).is_file(), 'the record was copied, not moved'
    print('PASS the pull record moved to the new folder')

    calls = []
    original = bridge._import_and_link
    bridge._import_and_link = lambda *args: calls.append(args[1]) or original(*args)
    bridge.pull(bpy.context)
    assert calls == [], 'the carried record did not stop the import: %r' % (calls,)
    print('PASS the moved record still knows that file')

    # a genuinely new version of the same file is imported normally
    model.write_text(model.read_text() + '# updated in 3D-Coat\n')
    signal.write_text(str(model) + '\n')
    bridge.pull(bpy.context)
    assert calls == [str(model)], calls
    bridge._import_and_link = original
    print('PASS a newer version still comes through')

    # and the name that stays on disk is the new one only
    assert not (folder / 'CoatLink').exists()
    assert not (pathlib.Path(tmp) / applink.APP_FOLDER / old_name).exists()
addon_utils.disable('coatlink', default_set=True)
print('TARGET RENAME REGRESSION PASSED')
