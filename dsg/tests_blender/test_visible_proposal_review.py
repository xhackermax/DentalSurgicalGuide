"""Visible reference proposal; discard restores original, accept commits fresh-checked model."""
import sys,time,tempfile
from pathlib import Path
import bpy
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import dsg
dsg.register()
from dsg import guide_module as g
from dsg.blender import implant_optimizer as opt,safety_volume as safety,implant_plane

def cube(name,size,location=(0,0,0)):
    bpy.ops.mesh.primitive_cube_add(size=size,location=location)
    obj=bpy.context.object;obj.name=name;return obj

def finish():
    deadline=time.monotonic()+60
    while opt.STATE['process'] is not None:
        if time.monotonic()>deadline:raise AssertionError('Worker timeout')
        time.sleep(.1);opt.poll()
    if bpy.app.timers.is_registered(opt.poll):bpy.app.timers.unregister(opt.poll)

try:
    assert g.deferred_post_register();safety.unregister()
    scene=bpy.context.scene
    for obj in list(scene.objects):bpy.data.objects.remove(obj,do_unlink=True)
    # A real sampled crest at z=0, rather than a platform buried 40 mm in
    # an all-solid box whose top lies outside the section map.
    bone=cube('Dental_DICOM_Mandible',80,(0,0,-40));cube('Dental_DICOM_MandibularCanal',2,(100,0,0))
    # Active DSG smoothing must survive immutable search and fresh APPLY snapshots.
    from dsg import cbct_dental_module as dental,surface_smoothing as smooth
    offsets=bone.data.attributes.new(smooth.OFFSET_ATTRIBUTE,'FLOAT_VECTOR','POINT')
    offsets.data.foreach_set('vector',[.025,0.,0.]*len(bone.data.vertices))
    modifier=bone.modifiers.new(dental.ALIGNMENT_VISUAL_SMOOTH_MODIFIER,'NODES')
    modifier.node_group=smooth._display_nodes(bpy)
    bone.data.update()
    mesh=g.make_embedded_implant_mesh('OriginalReference',4,10)
    implant=bpy.data.objects.new(g.IMPLANT_PREFIX+'PreviewTest',mesh);scene.collection.objects.link(implant)
    implant['DSG_target_fdi']=36;implant['DSG_implant_diameter']=4.;implant['DSG_implant_length']=10.
    control=bpy.data.objects.new('DSG_EmergenceTube_PreviewTest',None);scene.collection.objects.link(control)
    control['DSG_implant_emergence_controller']=True;implant.parent=control
    plane=bpy.data.objects.new(implant_plane.PREFIX+implant.name,None);scene.collection.objects.link(plane)
    constraint=plane.constraints.new('CHILD_OF');constraint.name='DSG_FollowImplant';constraint.target=implant
    implant.location.z=-5;scene.dsg_props.implant_obj=implant
    bpy.context.view_layer.objects.active=control;control.select_set(True);bpy.context.view_layer.update()
    scene.dsg_opt_reviewed=True # Synthetic case, not patient approval.
    scene.dsg_opt_library='BTI_COREX'
    scene.dsg_opt_shift_mm=0.;scene.dsg_opt_depth_mm=0. # Existing fixture: fixed-pose sizing; joint bounds have separate tests.
    # Isolate the existing preview lifecycle from the joint search stencil.
    fixed=opt.settings
    opt.settings=lambda scene:dict(fixed(scene),max_shift_mm=0.,max_depth_mm=.25)
    original_snapshot=opt.snapshot
    def section_snapshot(context,folder,mode):
        req=original_snapshot(context,folder,mode)
        req['section_site_paths']=[str(Path.home()/'AppData/Roaming/Blender Foundation/Blender/5.2/scripts/dsg_runtime/dsg_v910_blender52_py313/site-packages')]
        return req
    opt.snapshot=section_snapshot
    original=implant.matrix_world.copy();original_mesh=implant.data
    fingerprint_before=opt.fingerprint(bpy.context)
    offsets.data[0].vector.x=.03
    assert opt.fingerprint(bpy.context)!=fingerprint_before,'Edited smoothing did not invalidate the case fingerprint'
    offsets.data[0].vector.x=.025
    assert opt.fingerprint(bpy.context)==fingerprint_before
    opt.start(bpy.context,'SIZE');finish()
    if opt.STATE['result'] and opt.STATE['result']['status']!='NOMINAL_PROPOSAL':
        import json
        debug=opt.STATE['result'];row=debug.get('best') or debug.get('closest');print('PREVIEW_FIXTURE_DEBUG',json.dumps({'status':debug['status'],'metrics':row['evaluation'] if row else None,'section_summary':debug.get('section_summary',{}).get('grid_shape')},default=str),flush=True)
    assert opt.STATE['result'] and opt.STATE['result']['status']=='NOMINAL_PROPOSAL',opt.STATE['message']
    assert opt.STATE['result'].get('section_search'),'Section path silently fell back'
    best=opt.STATE['result']['best'];assert best['asset']['dimension_only']
    assert best['asset']['diameter_mm']==4.25 and best['asset']['length_mm']==13.
    preview=bpy.data.objects[opt.PREVIEW]
    assert preview.display_type=='SOLID' and not preview.hide_get() and preview.hide_select
    assert implant.hide_get() and control.hide_get()
    assert implant.matrix_world==original and implant.data==original_mesh
    assert constraint.target==preview,'MPR did not follow proposal'
    saved=Path(tempfile.mkdtemp(prefix='DSG_PREVIEW_RELOAD_TEST_'))/'proposal.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(saved),copy=True)
    old_layer=bpy.context.view_layer;other_layer=scene.view_layers.new('OtherReviewLayer')
    bpy.context.window.view_layer=other_layer
    assert opt.watch_preview() is None
    assert not implant.hide_get(view_layer=old_layer),'Original stayed hidden in its original view layer'
    assert constraint.target==implant,'MPR not restored on layer change'
    bpy.context.window.view_layer=old_layer
    opt.discard()
    assert bpy.data.objects.get(opt.PREVIEW) is None and not implant.hide_get() and not control.hide_get()
    assert implant.matrix_world==original and implant.data==original_mesh
    opt.start(bpy.context,'SIZE');finish()
    assert not scene.dsg_opt_profile_confirmed,'Preview must not auto-acknowledge a clinical review'
    scene.dsg_opt_profile_confirmed=True # Explicit acceptance in this synthetic case.
    # Exercise the foreground branch with Blender's real native undo system.
    class ForegroundApp:
        background=False
        def __getattr__(self,name):return getattr(bpy.app,name)
    class ForegroundBpy:
        app=ForegroundApp()
        def __getattr__(self,name):return getattr(bpy,name)
    opt.bpy=ForegroundBpy()
    assert bpy.ops.dsg.apply_implant_optimization()=={'FINISHED'}
    finish()
    opt.bpy=bpy
    assert 'aplicada' in opt.STATE['message'],opt.STATE['message']
    assert implant.data!=original_mesh and implant['DSG_implant_diameter']==4.25 and implant['DSG_implant_length']==13.
    assert implant['DSG_optimizer_family']=='BTI CORE-X'
    assert bpy.data.objects.get(opt.PREVIEW) is None and not implant.hide_get() and not control.hide_get()
    assert scene.dsg_opt_profile_confirmed
    bpy.ops.ed.undo()
    restored=bpy.data.objects[g.IMPLANT_PREFIX+'PreviewTest']
    assert restored['DSG_implant_diameter']==4. and not restored.hide_get()
    assert bpy.data.objects.get(opt.PREVIEW) is None,'Undo resurrected a preview with no accept/discard controls'
    assert implant_plane.plane_for(restored).constraints['DSG_FollowImplant'].target==restored
    bpy.ops.ed.redo()
    restored=bpy.data.objects[g.IMPLANT_PREFIX+'PreviewTest']
    assert restored['DSG_implant_diameter']==4.25 and not restored.hide_get()
    assert bpy.data.objects.get(opt.PREVIEW) is None
    bpy.ops.wm.open_mainfile(filepath=str(saved))
    implant=bpy.data.objects[g.IMPLANT_PREFIX+'PreviewTest']
    control=bpy.data.objects['DSG_EmergenceTube_PreviewTest']
    assert not implant.hide_get() and not control.hide_get(),'Saved preview left originals hidden'
    assert bpy.data.objects.get(opt.PREVIEW) is None and opt.STATE['result'] is None
    assert implant['DSG_implant_diameter']==4.,'Saved proposal was silently committed'
    assert implant_plane.plane_for(implant).constraints['DSG_FollowImplant'].target==implant
    print('REFERENCE_OPTIMIZER_PREVIEW_PASS:visible_solid,original_untouched,discard_restore,accept_reference,fresh_validation,no_auto_clinical_ack,mpr_follow,view_layer_restore,saved_preview_recovery',flush=True)
finally:opt.unregister();dsg.unregister()
