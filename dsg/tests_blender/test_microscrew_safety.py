"""Real microscrew asset, 2mm ring, hidden shaft and confirmation protection."""
import sys
import bpy
from mathutils import Vector

sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import dsg
dsg.register()
from dsg import guide_module as g,cbct_dental_module as dental,dicom_module as dicom
from dsg.blender import microscrew_safety as safety, safety_volume as implant_safety

try:
    implant_safety.unregister()
    scene = bpy.context.scene
    scene.dsg_suite_settings.workflow_route = 'SIMPLE'
    scene['DSG_active_arch'] = 'MANDIBLE'
    for obj in list(scene.objects):
        bpy.data.objects.remove(obj,do_unlink=True)
    record = {'axis':[0,0,1],'sleeve_top':[0,0,0],'x_hint':[1,0,0],'diameter':2.,'length':8.}
    screw = g.build_static_microscrew_visual(bpy.context,record,g.MICROSCREW_VISUAL_PREVIEW_NAME,preview=True)
    hidden = safety.sync(bpy.context,screw)
    visible = bpy.data.objects['DSG_MicroSafety_'+screw.name]
    assert visible['height_mm'] == 2 and not visible.hide_get()
    assert hidden['height_mm'] > 8 and hidden.hide_get() and hidden.hide_render
    assert hidden.parent == screw
    # Lower planning now requires an actual canal even before a nerve collision.
    bpy.ops.mesh.primitive_cube_add(size=.2,location=(100,100,100))
    distant_canal=bpy.context.object;distant_canal.name=dicom.NAME_DICOM_MANDIBULAR_CANAL+'_Baseline'
    point = hidden.matrix_world @ Vector((float(hidden['radius_mm'])*.7,0,-float(hidden['height_mm'])*.25))
    bpy.ops.mesh.primitive_cube_add(size=.2,location=point)
    tooth = bpy.context.object
    tooth.name = dental.TOOTH_OBJECT_PREFIX+'35'
    tooth['DSG_tooth_instance'],tooth['DSG_fdi_number'] = True,35
    bpy.context.view_layer.update()
    assert tooth.name in safety.contacts(bpy.context,screw)
    assert safety.validate(bpy.context,screw)
    bpy.ops.mesh.primitive_cube_add(size=1,location=(20,20,20))
    preview = bpy.context.object
    preview['DSG_microscrew_preview'] = True
    scene.dsg_props.microscrew_preview_obj = preview
    saved_name = preview.name
    obj,index,error = g.confirm_pending_microscrew_object(bpy.context,scene.dsg_props)
    assert obj is None and error and preview.name == saved_name
    assert scene.dsg_props.microscrew_preview_obj == preview, 'Rejected confirmation consumed the preview'
    tooth.location = (30,0,0)
    bpy.ops.mesh.primitive_cube_add(size=.2,location=point)
    nerve = bpy.context.object
    nerve.name = dicom.NAME_DICOM_MANDIBULAR_CANAL
    bpy.context.view_layer.update()
    assert nerve.name in safety.contacts(bpy.context,screw)
    nerve.location = (30,0,0)
    bpy.ops.mesh.primitive_cube_add(size=.2,location=point)
    implant = bpy.context.object
    implant.name = g.IMPLANT_PREFIX+'SafetyFixture'
    bpy.context.view_layer.update()
    assert implant.name in safety.contacts(bpy.context,screw)
    implant.location = (30,0,0)
    other = g.build_static_microscrew_visual(bpy.context,record,'DSG_MicroscrewOther',index=1,preview=False)
    bpy.context.view_layer.update()
    assert other.name in safety.contacts(bpy.context,screw)
    bpy.data.objects.remove(other,do_unlink=True)
    bpy.context.view_layer.update()
    assert safety.validate(bpy.context,screw) is None
    screw.rotation_euler.y = .6
    bpy.context.view_layer.update()
    changed = safety.sync(bpy.context,screw)
    assert changed.parent == screw and changed['height_mm'] == hidden['height_mm']
    assert (changed.matrix_world.to_3x3() @ Vector((0,0,1))).normalized().dot(
        (screw.matrix_world.to_3x3() @ Vector((0,0,1))).normalized()) > .9999
    safety.refresh(bpy.context)
    assert not any(o.get('DSG_microscrew_safety') and o.get('DSG_microscrew_visual_name') == 'DSG_MicroscrewOther' for o in bpy.data.objects)
    print('MICROSCREW_SAFETY_PASS: real asset, 2mm ring, full shaft, tooth/nerve/implant/screw contacts, confirmation gate, rotation, cleanup',flush=True)
finally:
    dsg.unregister()
