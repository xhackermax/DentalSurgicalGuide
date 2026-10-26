"""Measurements belong to a pose/proposal and must not survive its replacement."""
import sys
import bpy
from mathutils import Vector
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import dsg
dsg.register()
from dsg import guide_module as g
from dsg.blender import implant_optimizer as opt
scene=bpy.context.scene
bpy.ops.mesh.primitive_cube_add(size=2)
a=bpy.context.object;a.name=g.IMPLANT_PREFIX+'MeasureA'
bpy.ops.mesh.primitive_cube_add(size=2,location=(10,0,0))
b=bpy.context.object;b.name=g.IMPLANT_PREFIX+'MeasureB'
bpy.ops.mesh.primitive_plane_add(size=20)
plane=bpy.context.object;plane['DSG_inclination_plane_implant']=a.name
r1=g._create_dicom_measurement(bpy.context,a,0,Vector(),Vector((3,0,0)),plane.name)
r2=g._create_dicom_mpr_measurement(bpy.context,Vector(),Vector((3,4,0)),plane.name,plane.name)
r3=g._create_dicom_measurement(bpy.context,b,0,Vector((10,0,0)),Vector((12,0,0)),'')
old=[r1.name,r2.name]+[r.get(k) for r in (r1,r2) for k in ('DSG_measure_marker_a','DSG_measure_marker_b')]
keep=r3.name
g._update_all_dicom_measurements(scene)
assert all(scene.objects.get(n) for n in old),'Unchanged measurements were removed'
a.location.x+=1;bpy.context.view_layer.update();g._update_all_dicom_measurements(scene)
assert all(bpy.data.objects.get(n) is None for n in old),'Stale pose measurements/markers remain'
assert scene.objects.get(keep),'Other implant measurement removed'
# A new proposal expires a measurement even when its pose matches the source.
r=g._create_dicom_mpr_measurement(bpy.context,Vector(),Vector((3,4,0)),plane.name,plane.name);name=r.name
preview=bpy.data.objects.new(opt.PREVIEW,a.data.copy());scene.collection.objects.link(preview)
preview['DSG_optimizer_preview']=True;preview['DSG_optimizer_original']=a.name
preview['DSG_measure_context_id']='FIRST'
g._update_all_dicom_measurements(scene)
assert bpy.data.objects.get(name) is None,'Proposal retained measurements from original pose'
r=g._create_dicom_mpr_measurement(bpy.context,Vector(),Vector((3,4,0)),plane.name,plane.name);name=r.name
preview['DSG_measure_context_id']='SECOND'
g._update_all_dicom_measurements(scene)
assert bpy.data.objects.get(name) is None,'Replaced proposal retained measurements'
r=g._create_dicom_mpr_measurement(bpy.context,Vector(),Vector((3,4,0)),plane.name,plane.name);name=r.name
bpy.data.objects.remove(preview,do_unlink=True);g._update_all_dicom_measurements(scene)
assert bpy.data.objects.get(name) is None,'Discarded proposal retained measurements'
print('MEASUREMENT_POSE_PROPOSAL_EXPIRY_MARKERS_AND_OTHER_IMPLANT_PASS')
# Rotation of the measured MPR plane also expires its fixed anatomical points.
r=g._create_dicom_mpr_measurement(bpy.context,Vector(),Vector((3,4,0)),plane.name,plane.name);name=r.name
plane.rotation_euler.z=.2;bpy.context.view_layer.update();g._update_all_dicom_measurements(scene)
assert bpy.data.objects.get(name) is None,'Old cut measurement remained after rotating its plane'
# Legacy measurements with no creation context are removed rather than adopted.
r=g._create_dicom_measurement(bpy.context,b,0,Vector((10,0,0)),Vector((12,0,0)),'');name=r.name
r.pop('DSG_measure_context',None);r.pop('DSG_measure_context_signature',None)
g._update_all_dicom_measurements(scene)
assert bpy.data.objects.get(name) is None
assert scene.objects.get(keep),'Unchanged independent measurement was lost'
print('MEASUREMENT_CUT_ROTATION_AND_LEGACY_CLEANUP_PASS')
