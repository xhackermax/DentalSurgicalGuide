import sys,bpy
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import dsg
dsg.register()
from dsg import guide_module as g
from dsg.blender import emergence_reference as refs
bpy.ops.mesh.primitive_cube_add(size=2)
o=bpy.context.object;o.name=g.IMPLANT_PREFIX+'ReferenceTest'
o.rotation_euler=(.1,.2,.3);bpy.context.view_layer.update()
before=o.matrix_world.copy();parent=o.parent
for step in (g.STEP_CONTOUR,g.STEP_FRAME):
 refs.sync(bpy.context,step=step)
 found=[r for r in bpy.context.scene.objects if r.get(refs.FLAG)]
 assert len(found)==1
 assert not o.hide_get() and not o.hide_viewport and o.hide_select
 assert found[0].visible_get() and found[0].hide_select and found[0].hide_render
 assert not found[0].get('DSG_implant_emergence_controller')
 assert o.matrix_world==before and o.parent==parent
 assert g.get_all_implant_objects(bpy.context.scene.dsg_props)==[o]
refs.sync(bpy.context,step=g.STEP_SLEEVE)
assert found[0].hide_get()
refs.sync(bpy.context,step=g.STEP_CONTOUR)
assert len([r for r in bpy.context.scene.objects if r.get(refs.FLAG)])==1
print('FRAME_EMERGENCE_REFERENCE_VISIBILITY_IDEMPOTENCE_POSE_SCOPE_PASS')
