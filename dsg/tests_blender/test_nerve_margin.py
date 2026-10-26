"""Independent canal buffer, full implant surface, hidden/bilateral and missing canal."""
import bpy,sys,json
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import dsg
dsg.register()
from dsg import guide_module as g,dicom_module as dicom
from dsg.blender import nerve_safety as nerve,safety_volume as safety
try:
    safety.unregister();nerve.register()
    for obj in list(bpy.context.scene.objects):bpy.data.objects.remove(obj,do_unlink=True)
    scene=bpy.context.scene;scene['DSG_active_arch']='MANDIBLE'
    bpy.ops.mesh.primitive_cube_add(size=2)
    implant=bpy.context.object;implant.name=g.IMPLANT_PREFIX+'NerveTest';implant['DSG_target_fdi']=36
    scene.dsg_props.implant_obj=implant
    scene.dsg_props.implant_tooth_clearance=.1
    bpy.ops.mesh.primitive_cube_add(size=2,location=(3.8,0,0))
    canal=bpy.context.object;canal.name=dicom.NAME_DICOM_MANDIBULAR_CANAL;canal.hide_set(True)
    bpy.context.view_layer.update()
    assert canal.name in nerve.failures(bpy.context,implant),'1.8 mm gap allowed through nerve margin'
    report=json.loads(implant['DSG_nerve_safety_report'])
    assert report[0]['margin_mm']==2 and report[0]['upper_mm']<2
    # Different from the dental margin: lowering it must not reduce nerve buffer.
    assert canal.name in safety.contacts(bpy.context,implant)
    canal.location=(4.5,0,0);bpy.context.view_layer.update()
    assert not nerve.failures(bpy.context,implant),'2.5 mm gap rejected at 2 mm margin'
    scene.dsg_nerve_margin_mm=3
    assert canal.name in nerve.failures(bpy.context,implant),'Increasing nerve margin did not take effect'
    scene.dsg_nerve_margin_mm=2
    canal.location=(3.8,3.8,0);bpy.context.view_layer.update()
    assert not nerve.failures(bpy.context,implant),'Diagonal Euclidean clearance was treated as a square/cylinder margin'
    canal.location=(0,0,-3.8);bpy.context.view_layer.update()
    assert canal.name in nerve.failures(bpy.context,implant),'Apical buffer was ignored'
    canal.location=(10,0,0);bpy.context.view_layer.update()
    bpy.ops.mesh.primitive_cube_add(size=2,location=(0,3.8,0))
    other=bpy.context.object;other.name=dicom.NAME_DICOM_MANDIBULAR_CANAL+'_Right';other.hide_set(True)
    bpy.context.view_layer.update()
    assert other.name in nerve.failures(bpy.context,implant),'Second hidden canal ignored'
    # A contained canal must not pass simply because surfaces do not intersect.
    other.location=(0,0,0);other.scale=(.1,.1,.1);bpy.context.view_layer.update()
    assert json.loads(implant.get(nerve.REPORT,'[]'))
    assert other.name in nerve.failures(bpy.context,implant)
    assert any(item['status']=='CONTACT' for item in json.loads(implant[nerve.REPORT]))
    # Non-watertight STL gets an outer conservative hull; original stays untouched.
    import bmesh
    bm=bmesh.new();bm.from_mesh(implant.data);bm.faces.ensure_lookup_table()
    bmesh.ops.delete(bm,geom=[bm.faces[0]],context='FACES');bm.to_mesh(implant.data);bm.free()
    safety._GEOMETRY.pop(implant.name,None)
    source_faces=len(implant.data.polygons)
    assert other.name in nerve.failures(bpy.context,implant)
    assert any(item.get('conservative_envelope') for item in json.loads(implant[nerve.REPORT]))
    assert len(implant.data.polygons)==source_faces
    bpy.data.objects.remove(other,do_unlink=True);bpy.data.objects.remove(canal,do_unlink=True)
    assert nerve.MISSING in nerve.failures(bpy.context,implant),'Missing nerve silently passed'
    implant['DSG_target_fdi']=16
    assert not nerve.failures(bpy.context,implant),'Upper implant incorrectly required lower canal'
    print('NERVE_MARGIN_PASS: independent 2mm buffer, adjustable larger margin, lateral/apical gaps, bilateral hidden canals, missing-canal block and upper-arch exclusion',flush=True)
finally:
    dsg.unregister()
