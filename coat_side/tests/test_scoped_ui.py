"""Native panel layout contract; fake host, not visual verification."""
import pathlib, sys, tempfile, importlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import fake_coat
with tempfile.TemporaryDirectory() as tmp:
    fake_coat.make_exchange_tree(tmp)
    host, cmd = fake_coat.build_environment(tmp)
    lib = importlib.import_module('CoatBridgeLib')
    panel = lib.CoatBridgePanel()
    items = panel.ui()
    assert any('Export scope: selected node + descendants' in s for s in items)
    assert not any(s.startswith('Textures,') for s in items)
    assert 'RemoveLauncher' not in items
    assert not any(lib.REOPEN_HINT in s for s in items)
    assert any('geometry only' in s for s in items)
    panel.Advanced = True
    items = panel.ui()
    assert 'RemoveLauncher' in items
    assert any(lib.REOPEN_HINT in s for s in items)
print('PASS native layout: explicit subtree scope, no unsupported texture control, maintenance hidden by default')
