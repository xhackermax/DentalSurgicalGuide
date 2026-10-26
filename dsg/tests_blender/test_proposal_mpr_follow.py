"""Creating/rebuilding an MPR after a proposal must follow the preview pose."""
import sys
from unittest.mock import patch
import bpy
from mathutils import Vector
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import dsg
dsg.register()
from dsg import guide_module as g
from dsg.blender import implant_plane as p,implant_optimizer as opt,safety_volume
safety_volume.unregister();p.register()
bpy.ops.mesh.primitive_cube_add(size=2)
implant=bpy.context.object;implant.name=g.IMPLANT_PREFIX+'MPRFollowTest'
original=implant.matrix_world.copy()
preview=bpy.data.objects.new(opt.PREVIEW,implant.data.copy());bpy.context.scene.collection.objects.link(preview)
preview['DSG_optimizer_preview']=True;preview['DSG_optimizer_original']=implant.name
preview.location=(4,2,3);preview.rotation_euler=(.1,.2,.3)
bpy.context.view_layer.update()
sampled=[]
def reslice(context,plane):
 sampled.append(tuple(plane.matrix_world.translation));p.STATE['poses'][plane.name]=p._pose_key(plane);return True
with patch.object(p,'refresh',side_effect=reslice):
 plane=p.create(bpy.context,implant)
 assert plane.constraints['DSG_FollowImplant'].target==preview,'MPR created after proposal follows original implant'
 bpy.context.view_layer.update()
 assert (plane.matrix_world.translation-preview.matrix_world.translation).length<1e-5
 p.STATE['poses'][plane.name]=p._pose_key(plane)
 preview.location.x+=2;bpy.context.view_layer.update();p._follow(bpy.context.scene)
 assert plane.name in p.STATE['pending'],'Moved proposal did not queue image reslice'
 p._refresh_pending()
 assert (Vector(sampled[-1])-preview.matrix_world.translation).length<1e-5,'Image resliced at original pose'
 assert implant.matrix_world==original,'MPR moved original implant'
 opt.restore_followers(preview)
 bpy.data.objects.remove(preview,do_unlink=True)
 bpy.context.view_layer.update();p._follow(bpy.context.scene);bpy.context.view_layer.update()
 assert plane.constraints['DSG_FollowImplant'].target==implant,'Discard did not restore source follow'
 assert (plane.matrix_world.translation-implant.matrix_world.translation).length<1e-5
print('PROPOSED_IMPLANT_MPR_CREATE_MOVE_RESLICE_DISCARD_PASS')

