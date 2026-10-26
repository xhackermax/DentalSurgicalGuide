"""Cold hidden objects must fingerprint consistently and retain edit detection."""
import sys,tempfile
from pathlib import Path
import bpy

root=Path(sys.argv[sys.argv.index('--')+1]);sys.path.insert(0,str(root))
from dsg.blender.generative_frame import evaluated_geometry_fingerprint

bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
bpy.ops.mesh.primitive_cube_add(location=(3,4,5),rotation=(.1,.2,.3))
obj=bpy.context.object;obj.name='ColdHiddenFingerprint';obj.hide_viewport=True
with tempfile.TemporaryDirectory(prefix='DSG_hidden_hash_') as folder:
    path=Path(folder)/'hidden.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(path));bpy.ops.wm.open_mainfile(filepath=str(path))
    obj=bpy.data.objects['ColdHiddenFingerprint']
    hashes=[evaluated_geometry_fingerprint(bpy.context,obj) for _ in range(3)]
    assert len(set(hashes))==1,hashes
    assert obj.hide_viewport and not obj.hide_get()
    obj.data.vertices[0].co.x+=.25
    assert evaluated_geometry_fingerprint(bpy.context,obj)!=hashes[0]
    changed=evaluated_geometry_fingerprint(bpy.context,obj)
    obj.location.x+=1
    assert evaluated_geometry_fingerprint(bpy.context,obj)!=changed
print('HIDDEN_GEOMETRY_FINGERPRINT_PASS')
