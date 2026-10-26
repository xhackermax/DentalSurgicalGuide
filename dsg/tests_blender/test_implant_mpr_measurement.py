import sys
from unittest.mock import patch
import bpy
from mathutils import Vector
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import dsg
dsg.register()
from dsg import guide_module as g
from dsg.blender import implant_plane
scene=bpy.context.scene
scene.dsg_props.current_step=g.STEP_IMPLANT
bpy.ops.mesh.primitive_plane_add(size=20)
plane=bpy.context.object;plane.name=implant_plane.PREFIX+'TestImplant'
plane[implant_plane.ROLE]=True
assert plane in g._dicom_measurement_planes(bpy.context), 'Implant MPR plane omitted from measurement targets'
scene.dsg_props.current_step=g.STEP_IMPLANT
with patch.object(g,'STEP_IMPLANT',scene.dsg_props.current_step), patch.object(g,'_dicom_review_is_active',return_value=False):
 assert g.DSG_OT_MeasureDICOMTwoPoints.poll(bpy.context), 'Standalone implant MPR cannot measure'
 hit=g._nearest_visible_raycast(bpy.context,g._dicom_measurement_planes(bpy.context),Vector((0,0,10)),Vector((0,0,-1)))
 assert hit and hit[0]==plane
 root=g._create_dicom_mpr_measurement(bpy.context,Vector((0,0,0)),Vector((3,4,0)),plane.name,plane.name)
 assert abs(root['DSG_measure_distance_mm']-5)<1e-6
 plane.hide_set(True)
 assert plane not in g._dicom_measurement_planes(bpy.context)
 assert not g.DSG_OT_MeasureDICOMTwoPoints.poll(bpy.context)
print('IMPLANT_MPR_MEASUREMENT_PLANE_RAY_DISTANCE_VISIBILITY_PASS')


# Exercise both actual modal click paths against the real plane mesh.
import inspect
from types import SimpleNamespace
plane.hide_set(False)
def reporter():
 return SimpleNamespace(_point_a=None,_plane_a_name='',_implant_name='',_vertex_index=-1,report=lambda *a:None,_finish_cursor=lambda *a:None)
event=SimpleNamespace(type='LEFTMOUSE',value='PRESS')
with patch.object(g,'_dicom_review_is_active',return_value=False), patch.object(g,'_event_view_ray',side_effect=[(Vector((0,0,10)),Vector((0,0,-1))),(Vector((3,4,10)),Vector((0,0,-1)))]):
 op=reporter();modal=inspect.unwrap(g.DSG_OT_MeasureDICOMTwoPoints.modal)
 assert modal(op,bpy.context,event)=={'RUNNING_MODAL'}
 assert modal(op,bpy.context,event)=={'FINISHED'}
# Existing general DICOM planes remain valid targets too.
bpy.ops.mesh.primitive_plane_add(size=10)
legacy=bpy.context.object;legacy.name=g.DICOM_MEASURE_PLANE_NAMES[0]
assert legacy in g._dicom_measurement_planes(bpy.context)
print('IMPLANT_MPR_TWO_CLICK_MODAL_AND_LEGACY_PLANE_PASS')
