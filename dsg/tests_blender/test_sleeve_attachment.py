"""Cold Blender: positive volume, not tangency, is required at the sleeve."""
import sys
from pathlib import Path
root=Path(sys.argv[sys.argv.index('--')+1]);sys.path.insert(0,str(root))
import bpy
import numpy as np
from dsg.blender.sleeve_attachment import certify_sleeve_attachment

def cube(center=(0,0,0),size=2):
    bpy.ops.mesh.primitive_cube_add(size=size,location=center)
    obj=bpy.context.object;obj.data.calc_loop_triangles()
    return np.asarray([tuple(obj.matrix_world@v.co) for v in obj.data.vertices]),np.asarray([tuple(t.vertices) for t in obj.data.loop_triangles])

v,f=cube();w,g=cube((1.5,0,0));receipt=certify_sleeve_attachment(v,f,w,g)
assert receipt['positive_volume_overlap'] and receipt['common_interior_ball_radius_mm']>=.01
for center in ((2,0,0),(2.01,0,0)):
    w,g=cube(center)
    try:certify_sleeve_attachment(v,f,w,g)
    except ValueError:pass
    else:raise AssertionError('Touch or gap certified as attachment')
w,g=cube(size=.5)
assert certify_sleeve_attachment(v,f,w,g)['positive_volume_overlap']
assert certify_sleeve_attachment(v,f[:,::-1],w,g)['positive_volume_overlap']
try:certify_sleeve_attachment(v,f[:-1],w,g)
except ValueError:pass
else:raise AssertionError('Open mesh accepted')
print('SLEEVE_ATTACHMENT_PASS:overlap,containment,reversed,touch,gap,open')
