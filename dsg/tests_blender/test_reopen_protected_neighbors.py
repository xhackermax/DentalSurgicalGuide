import bpy,sys
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
from dsg import guide_module as g
from dsg.blender import protected_neighbors as n
class Scene(dict):
    dsg_props=object()
scene=Scene();context=SimpleNamespace(scene=scene)
with patch.object(g,'count_implants',return_value=1):
    assert n.confirmed(scene),'Legacy scenes with implants must still bypass the initial selection gate'
    scene[n.KEPT]='[14,16]'
    n.DSG_OT_ReopenProtectedNeighbors.execute(None,context)
    assert not n.confirmed(scene),'Existing implant silently closes the requested editor'
    assert scene[n.EDITOR] and scene[n.KEPT]=='[14,16]'
    class Layout:
        def __init__(self):self.ops=[]
        def row(self,**kw):return self
        def box(self):return self
        def label(self,**kw):pass
        def operator(self,key,**kw):self.ops.append(key);return SimpleNamespace()
    layout=Layout()
    with patch.object(n,'_toggles',side_effect=lambda box,s:box.operator('dsg.toggle_protected_neighbor')),patch.object(n,'_nerve'),patch.object(n,'request_sync'):
        assert n.draw_step(layout,context) is False
    assert 'dsg.toggle_protected_neighbor' in layout.ops and 'dsg.confirm_protected_neighbors' in layout.ops
    with patch.object(n,'sync'):
        n.DSG_OT_ConfirmProtectedNeighbors.execute(None,context)
    assert n.confirmed(scene) and not scene[n.EDITOR] and scene[n.KEPT]=='[14,16]'
print('REOPEN_NEIGHBORS_PASS:existing_implant,visible_editor,preserved_selection,reconfirm,legacy_scene')
