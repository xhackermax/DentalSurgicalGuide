import sys,json
from pathlib import Path
import bpy,numpy as np
root,case,out=map(Path,sys.argv[sys.argv.index('--')+1:]);sys.path.insert(0,str(root))
import dsg;dsg.register();bpy.ops.wm.open_mainfile(filepath=str(case),load_ui=False)
from dsg.blender import generative_frame as gf
before=gf.case_fingerprint(bpy.context);visibility={o.name:(o.hide_viewport,o.hide_get()) for o in bpy.data.objects}
request=gf.snapshot_frame_case(bpy.context,out)
assert before==gf.case_fingerprint(bpy.context)
assert visibility=={o.name:(o.hide_viewport,o.hide_get()) for o in bpy.data.objects}
frame=bpy.data.objects[request['frame_name']];vertices,faces=gf._export_mesh(bpy.context,frame)
for row in request['supports']:
 if row.get('origin_source')=='PRESERVED_UPPER_FRAME_MESH':
  np.testing.assert_allclose(vertices[row['frame_vertex_index']],row['original_mm'],atol=1e-6)
assert 2<=len(request['supports'])<=24
assert all(row['upper_frame_surface'] for row in request['supports'])
assert request['reinforcement_envelope']['frame_origins']=='UPPER_SURFACE_ONLY'
policy=request['coverage_policy'];assert policy['require_lattice']
assert len(policy['targets'])==2
assert {p['opening_target'] for p in request['ports'] if p.get('opening_target')}=={t['id'] for t in policy['targets']}
for port in request['ports']:
 if not port.get('opening_target'):continue
 target=next(t for t in policy['targets'] if t['id']==port['opening_target'])
 local=np.linalg.inv(np.asarray(target['matrix_world']))@np.r_[port['original_mm'],1.]
 assert target['height_mm']*.5-abs(local[2])>=port['required_end_clearance_mm']-1e-6
 assert abs(np.linalg.norm(local[:2])-target['radius_mm'])<1e-6
from mathutils import Vector
from mathutils.bvhtree import BVHTree
frame_obj=bpy.data.objects[request['frame_name']]
frame_v,frame_f=engine._export_mesh(context,frame_obj) if 'engine' in globals() else gf._export_mesh(bpy.context,frame_obj)
entry=np.asarray(request['reinforcement_envelope']['frame_entry_axis'])
frame_tree=BVHTree.FromPolygons(frame_v.tolist(),frame_f.tolist(),all_triangles=True)
for origin in request['supports']:
    hit=frame_tree.find_nearest(Vector(origin['original_mm']))
    assert hit and hit[0] is not None and hit[3]<1.e-5 and np.asarray(hit[1])@entry>.099
lower=np.load(request['frame_lower_surface_file'],allow_pickle=False)
tri=lower['vertices'][lower['triangles']];normals=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])
assert np.all(normals@entry < -.019*np.linalg.norm(normals,axis=1))
assert request['required_zones_complete']
print('FAR_FRAME_COVERAGE_SNAPSHOT_PASS',json.dumps({'schema':request['schema_version'],'real_origins':len(request['supports']),'flanks':len(policy['targets']),'case_preserved':True,'functional_keepouts':len(request['obstacles'])}))
