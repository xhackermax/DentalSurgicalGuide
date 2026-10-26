import bpy,sys
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import dsg
dsg.register()
from dsg import guide_module as g
from dsg.blender import upper_cavity_safety as u,safety_volume as s
try:
    s.unregister();u.register()
    for o in list(bpy.context.scene.objects):bpy.data.objects.remove(o,do_unlink=True)
    bpy.ops.mesh.primitive_cube_add(size=2)
    implant=bpy.context.object;implant.name=g.IMPLANT_PREFIX+'FaceCrossing';implant['DSG_target_fdi']=15
    bpy.ops.mesh.primitive_cube_add(size=2)
    zone=bpy.context.object;zone.name='NasalSlab';zone[u.KIND]='nasal_cavity_left';zone.scale=(.1,2,2);zone.hide_set(True)
    bpy.context.view_layer.update()
    assert zone.name in u.failures(bpy.context,implant),'Full-face crossing without inside vertices silently passed'
    assert u.report(implant)[0]['status']=='BLOCK'
    zone.location=(10,0,0);bpy.context.view_layer.update()
    assert not u.failures(bpy.context,implant)
    print('UPPER_FULL_SURFACE_CONTACT_PASS',flush=True)
finally:dsg.unregister()
