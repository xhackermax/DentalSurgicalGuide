"""Radial wall/gap measurements on native bone, independent from hazard limits."""
import sys
import bpy,numpy as np
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
from dsg.blender.implant_optimizer_geometry import Solid,measure_surrounding_bone
from dsg.blender.safety_volume import _mesh_arrays

def cube(size,offset=(0,0,0)):
    bpy.ops.mesh.primitive_cube_add(size=size);obj=bpy.context.object
    v,f,_=_mesh_arrays(obj.data);bpy.data.objects.remove(obj,do_unlink=True)
    return v+np.asarray(offset),f

bone=Solid(*cube(10),'Native cube')
measurement=measure_surrounding_bone(bone,np.eye(4),[0,0,2],4.,4.,levels=4,directions=4)
assert measurement['direct_bone_fraction']==1.
assert abs(measurement['minimum_direct_wall_mm']-3.)<.001,measurement
assert measurement['missing_rays']==0 and measurement['maximum_gap_mm']==0.
pose=np.eye(4);pose[0,3]=6.
outside=measure_surrounding_bone(bone,pose,[0,0,2],4.,4.,levels=4,directions=4)
assert 0<outside['direct_bone_fraction']<1. and outside['missing_rays']>0,outside
assert outside['maximum_gap_mm']==0.,outside
assert np.array_equal(pose[:3,3],[6,0,0]),'Measurement moved the implant'
pose[0,3]=10.
gap=measure_surrounding_bone(bone,pose,[0,0,2],4.,4.,levels=4,directions=4)
assert abs(gap['maximum_gap_mm']-3.)<.001 and gap['direct_bone_fraction']==0.,gap
print('SURROUNDING_BONE_MEASUREMENT_PASS:wall3mm,gap3mm,missing_bone,immutable_pose',flush=True)
# A large CBCT-scale bounding box must not misclassify interior radial origins.
large=Solid(*cube(80,(0,0,-40)),'CBCT-scale native box')
pose=np.eye(4);pose[2,3]=-6.5
measured=measure_surrounding_bone(large,pose,[0,0,6.5],4.25,13.)
assert measured['direct_bone_fraction']==1. and measured['missing_rays']==0
print('SURROUNDING_BONE_LARGE_COORDINATE_PARITY_PASS')
