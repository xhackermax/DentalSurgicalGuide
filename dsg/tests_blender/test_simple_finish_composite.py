import sys
import numpy as np
import bpy
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import dsg
dsg.register()
from dsg.blender import segmentation_finish as finish
from dsg import cbct_post_smoothing as post,alignment_module as alignment
scene=bpy.context.scene
arches=[]
for i in range(2):
 bpy.ops.mesh.primitive_uv_sphere_add(segments=12,ring_count=8,location=(i*4,0,0))
 arches.append(bpy.context.object)
bpy.ops.mesh.primitive_cube_add()
composite=bpy.context.object
raw=composite.data
before=post.mesh_hash(raw)
scene['DSG_simple_upper_object']=arches[0].name
scene['DSG_simple_lower_object']=arches[1].name
scene['DSG_simple_alignment_object']=composite.name
matrix=composite.matrix_world.copy()
assert finish.sync_simple_composite(scene)
assert composite.data!=raw
assert post.source_mesh(composite)==raw
assert post.mesh_hash(raw)==before
assert composite.matrix_world==matrix
v,f=post.mesh_arrays(composite.data)
expected=np.concatenate([np.array([composite.matrix_world.inverted() @ o.matrix_world @ p.co for p in o.data.vertices]) for o in arches])
np.testing.assert_allclose(v,expected,atol=1e-6)
assert composite.data.polygons[0].use_smooth
same=composite.data
assert not finish.sync_simple_composite(scene)
assert composite.data==same
print('SIMPLE_COMPOSITE_GEOMETRY_REFERENCE_TRANSFORM_IDEMPOTENCE_PASS')
