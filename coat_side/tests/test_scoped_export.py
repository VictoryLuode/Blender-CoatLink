import pathlib, sys, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from CoatBridgeScopedExport import export_subtree
from types import SimpleNamespace
calls=[]
class Mesh:
    def fromVolume(self, volume, subtree, selected): calls.append((volume,subtree,selected))
    def fromReducedVolume(self, volume, reduction, subtree, selected): calls.append((volume,reduction,subtree,selected))
    def valid(self): return True
    def facesCount(self): return 2
    def getObjectsCount(self): return 2
    def getObjectName(self,i): return ['Parent','Child'][i]
    def Write(self,path):
        pathlib.Path(path).write_text('o Parent\no Child\n')
        return True
coat=SimpleNamespace(Mesh=Mesh,Scene=SimpleNamespace(current=lambda:SimpleNamespace(Volume=lambda:'selected volume')))
with tempfile.TemporaryDirectory() as tmp:
    path=str(pathlib.Path(tmp)/'bridge.obj')
    assert export_subtree(coat,path)==(['Parent','Child'],2)
    assert calls[-1]==('selected volume',True,False)
    export_subtree(coat,path,25)
    assert calls[-1]==('selected volume',25.0,True,False)
    coat.Scene.current=lambda:None
    try: export_subtree(coat,path)
    except RuntimeError: pass
    else: raise AssertionError('missing selection accepted')
print('PASS explicit subtree scope, selected-only flag false, names retained, missing selection rejected (simulated API)')
