"""Cold Blender test: real manual collars reused by automatic curved bars."""
import sys
from pathlib import Path
import bpy
root=Path(sys.argv[sys.argv.index('--')+1]);sys.path.insert(0,str(root))
for site in sys.argv[sys.argv.index('--')+2:]:sys.path.append(site)
import dsg
from dsg import segmentation_engines
for site in segmentation_engines.active_site_paths():
    if site not in sys.path:sys.path.append(site)
dsg.register()
from dsg.blender.organic_reinforcement import build_bar
from dsg.guide_export.mesh_checks import manifold_report
from dsg.blender.generative_frame import _export_mesh,case_geometry_fingerprint
from dsg.organic_reinforcement import fair_open_path
from dsg import guide_module as g
import numpy as np
supports=[]
for x in (0,12):
    bpy.ops.mesh.primitive_cube_add(size=2,location=(x,0,0));supports.append(bpy.context.object)
before=[case_geometry_fingerprint(o) for o in supports]
pts,info=fair_open_path([[0,0,0],[3,.2,0],[6,.3,0],[9,.2,0],[12,0,0]],.4)
piece={'points_mm':pts.tolist(),'radius_mm':.4,'route_id':'test'}
meshes_before={m.name for m in bpy.data.meshes}
obj=build_bar(bpy.context,'OrganicTest',piece,supports[0],supports[1])
assert obj.get('DSG_organic_collar_count')==2
assert obj.get('DSG_organic_blend')=='BOUNDED_TANGENT_COONS_HERMITE'
v,f=_export_mesh(bpy.context,obj);report=manifold_report(v,f)
assert not report.blocking,report.as_dict()
assert [case_geometry_fingerprint(o) for o in supports]==before
assert obj.get('DSG_organic_footprint_radius_ratio')==1.2
assert not obj.get('DSG_organic_internal_caps',True)
assert {m.name for m in bpy.data.meshes}-meshes_before=={obj.data.name},'Owned temporary mesh leaked'
from dsg.blender.organic_quality import validate_body_radius
from dsg.organic_reinforcement import transport_frames
u,w,t=transport_frames(pts)
quality=validate_body_radius(v,f,pts[12:-12],u[12:-12],w[12:-12],.4)
assert quality['valid']
try:validate_body_radius(v,f,pts[12:-12],u[12:-12],w[12:-12],.8)
except ValueError as exc:assert 'EXCESSIVE_SHRINK' in str(exc)
else:raise AssertionError('Undersized final body accepted')
print('ORGANIC_REINFORCEMENT_REVIEW_PASS',report.as_dict())
