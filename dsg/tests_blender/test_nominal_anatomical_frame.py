import bpy,sys,tempfile,numpy as np
from pathlib import Path
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import dsg;dsg.register()
from dsg import guide_module as g
from dsg.blender import implant_optimizer as opt
from dsg.implant_search_frames import search_frames
from mathutils import Matrix
scene=bpy.context.scene
for o in list(scene.objects):bpy.data.objects.remove(o,do_unlink=True)
mesh=g.make_embedded_implant_mesh('Reference',4.,10.)
implant=bpy.data.objects.new(g.IMPLANT_PREFIX+'AxisTest',mesh);scene.collection.objects.link(implant)
control=bpy.data.objects.new('DSG_EmergenceTube_AxisTest',None);scene.collection.objects.link(control)
control['DSG_implant_emergence_controller']=True;implant.parent=control
implant.location.z=-5;implant['DSG_implant_diameter']=4.;implant['DSG_implant_length']=10.
scene.dsg_props.implant_obj=implant;bpy.context.view_layer.objects.active=control
bpy.context.view_layer.update()
with tempfile.TemporaryDirectory() as td:
 root=Path(td);a=np.radians(8);rot=np.array([[np.cos(a),0,np.sin(a)],[0,1,0],[-np.sin(a),0,np.cos(a)]])
 vertices=np.array([[x,y,z] for z in (-7,7) for x in (-1,1) for y in (-1,1)])@rot.T
 np.save(root/'root_v.npy',vertices)
 request={'implant':{'matrix':[list(r) for r in implant.matrix_world]},'platform':list(g.get_implant_platform_center_world(scene.dsg_props,implant)),
          'target_fdi':15,'sockets':[{'name':'Tooth15','fdi':15,'vertices_path':str(root/'root_v.npy'),'matrix':np.eye(4).tolist()}],
          'settings':opt.settings(scene)}
 opt.STATE.update(target=implant.name,request=request)
 seed=search_frames(request)[1];matrix=np.asarray(seed['matrix']);matrix[:3,3]=np.asarray(request['platform'])-matrix[:3,:3]@np.array([0,0,6])
 row={'matrix':matrix.tolist(),'parameters':[0,0,0,0,0],'axis_reference':seed['id'],
      'asset':{'id':'TEST4.1x12','family':'TEST','diameter_mm':4.1,'length_mm':12.,'platform_local_mm':[0,0,6],'dimension_only':True}}
 opt._commit_nominal(bpy.context,row)
 assert opt._matches(implant.matrix_world,Matrix(row['matrix'])),'Controller did not apply validated anatomical frame'
 assert implant['DSG_implant_length']==12.
 old=implant.matrix_world.copy();old_mesh=implant.data
 row['axis_reference']='UNAUTHORIZED'
 try:opt._commit_nominal(bpy.context,row);raise AssertionError('Unauthorized axis applied')
 except ValueError:pass
 assert implant.matrix_world==old and implant.data==old_mesh,'Rejected frame changed original'
print('NOMINAL_ANATOMICAL_FRAME_PASS:parent_rotation,validated_platform,unauthorized_axis_rollback')
