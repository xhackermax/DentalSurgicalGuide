"""Synthetic Blender end-to-end: worker, preview, stale rejection and manual apply."""
import sys,time,json,tempfile
from pathlib import Path
import bpy,numpy as np
from mathutils import Matrix
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import dsg
dsg.register()
from dsg import guide_module as g
from dsg.blender import implant_optimizer as opt,safety_volume as safety,implant_plane,mpr_view
from dsg.blender.safety_volume import _mesh_arrays

def cube(name,size=2,location=(0,0,0)):
    bpy.ops.mesh.primitive_cube_add(size=size,location=location)
    obj=bpy.context.object;obj.name=name
    return obj

def finish():
    deadline=time.monotonic()+45
    while opt.STATE['process'] is not None:
        if time.monotonic()>deadline:raise AssertionError('Worker timeout')
        time.sleep(.1);opt.poll()
    if bpy.app.timers.is_registered(opt.poll):bpy.app.timers.unregister(opt.poll)

try:
    assert g.deferred_post_register()
    safety.unregister();opt.register();implant_plane.register()
    for obj in list(bpy.context.scene.objects):bpy.data.objects.remove(obj,do_unlink=True)
    scene=bpy.context.scene;props=scene.dsg_props
    bone=cube('Dental_DICOM_Mandible',3,(.8,0,0))
    canal=cube('Dental_DICOM_MandibularCanal',2,(20,0,0));canal.hide_set(True)
    implant=cube(g.IMPLANT_PREFIX+'Optimizer',2);implant['DSG_target_fdi']=36
    implant['DSG_implant_diameter']=2.;implant['DSG_implant_length']=2.
    control=bpy.data.objects.new('DSG_EmergenceTube_Optimizer',None);scene.collection.objects.link(control)
    control['DSG_implant_emergence_controller']=True;implant.parent=control
    props.implant_obj=implant
    for o in bpy.context.selected_objects:o.select_set(False)
    control.select_set(True);bpy.context.view_layer.objects.active=control
    scene.dsg_opt_reviewed=True # Synthetic geometry only; never accept a patient CBCT programmatically.
    scene.dsg_opt_shift_mm=1.;scene.dsg_opt_tilt_deg=0.;scene.dsg_opt_reserve_mm=.1;scene.dsg_opt_coverage=20.
    bpy.context.view_layer.update();original=implant.matrix_world.copy();mesh=implant.data
    other_scene=bpy.data.scenes.new('ForeignCase')
    for obj,label in ((bone,'hueso'),(canal,'nervio')):
        original_collections=tuple(obj.users_collection)
        other_scene.collection.objects.link(obj)
        for collection in original_collections:collection.objects.unlink(obj)
        assert any(label in message for message in opt.readiness(bpy.context,'POSITION')),'Foreign case anatomy accepted'
        for collection in original_collections:collection.objects.link(obj)
        other_scene.collection.objects.unlink(obj)
    assert not opt.readiness(bpy.context,'POSITION')
    opt.start(bpy.context,'POSITION');finish()
    assert opt.STATE['result'] and opt.STATE['result']['status']=='PROPOSAL',opt.STATE['message']
    assert implant.matrix_world==original and implant.data==mesh,'Search mutated original'
    preview=bpy.data.objects[opt.PREVIEW];assert preview.hide_select and preview.hide_render and mpr_view._keep(preview,g)
    before=opt.fingerprint(bpy.context);scene.dsg_opt_profile_confirmed=True
    assert opt.fingerprint(bpy.context)==before,'Final review invalidates its own proposal'
    opt.start(bpy.context,'POSITION',purpose='APPLY');finish()
    assert 'aplicada' in opt.STATE['message'],opt.STATE['message']
    assert implant.matrix_world!=original and implant.data==mesh
    assert bpy.data.objects.get(opt.PREVIEW) is None
    # A worker snapshot becomes invalid when source pose changes.
    opt.start(bpy.context,'POSITION');control.location.x+=.1;bpy.context.view_layer.update();finish()
    assert opt.STATE['result'] is None and 'cambiados' in opt.STATE['message'],opt.STATE['message']
    # Exact catalogue meshes, immutable copies, unchanged axis/platform, no virtual scaling.
    bone.scale=(10,10,10);bpy.context.view_layer.update()
    folder=Path(tempfile.mkdtemp(prefix='DSG_SYNTHETIC_CATALOGUE_'));v,f,_=_mesh_arrays(mesh)
    rows=[]
    for name,size in [('small',1),('large',2)]:
        np.save(folder/(name+'_v.npy'),v*size/2);np.save(folder/(name+'_f.npy'),f)
        rows.append({'id':name,'diameter_mm':size,'length_mm':size,'platform_local_mm':[0,0,size/2],
            'vertices_path':name+'_v.npy','faces_path':name+'_f.npy','reference':'SYNTHETIC TEST ONLY'})
    file=folder/'catalogue.json';file.write_text(json.dumps({'schema_version':1,'units':'mm','family':'TEST','implants':rows}),'utf-8')
    scene.dsg_opt_library='CUSTOM'
    scene.dsg_opt_family='TEST';scene.dsg_opt_catalogue=str(file)
    platform=g.get_implant_platform_center_world(props,implant).copy();axis=g.get_implant_axis_world(props,implant).copy()
    opt.start(bpy.context,'SIZE');finish()
    assert opt.STATE['result'] and opt.STATE['result']['status']=='COMPARISON',opt.STATE['message']
    asset=opt.STATE['result']['best']['asset'];assert Path(asset['vertices_path']).parent!=folder
    # Changing catalogue bytes must invalidate proposal even if its pathname is unchanged.
    scene.dsg_opt_profile_confirmed=True
    prior=opt.fingerprint(bpy.context);np.save(folder/'large_v.npy',v*1.01)
    assert prior!=opt.fingerprint(bpy.context)
    try:opt.start(bpy.context,'SIZE',purpose='APPLY');raise AssertionError('Stale catalogue accepted')
    except ValueError:pass
    np.save(folder/'large_v.npy',v)
    scene.dsg_opt_profile_confirmed=True
    opt.start(bpy.context,'SIZE',purpose='APPLY');finish()
    assert 'aplicada' in opt.STATE['message'],opt.STATE['message']
    assert (g.get_implant_platform_center_world(props,implant)-platform).length<1e-5
    assert (g.get_implant_axis_world(props,implant)-axis).length<1e-5
    assert implant['DSG_catalogue_asset_id']=='large' and implant.data!=mesh
    pose=implant.matrix_world.copy();opt.start(bpy.context,'POSITION');opt.discard()
    assert opt.STATE['process'] is None and opt.STATE['result'] is None and implant.matrix_world==pose
    print('IMPLANT_OPTIMIZER_LIFECYCLE_PASS',flush=True)
finally:
    opt.unregister();dsg.unregister()
