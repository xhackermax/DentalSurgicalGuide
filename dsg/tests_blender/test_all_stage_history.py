"""Coverage audit and full-state round trips across all three workflow modules."""
import sys,os,tempfile,json,gc
from pathlib import Path
import bpy,numpy as np
from mathutils import Matrix
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import dsg
dsg.register()
from dsg import workflow_history as h,dicom_module as dicom,guide_module as guide

required=('dsg_suite.load_patient_cbct','dsg_suite.toggle_antagonist',
 'dicom_wizard_pro.select_file','dicom_wizard_pro.select_target',
 'dsg.reset_current_step','dsg.use_selected_ios_model','dsg.prepare_aligned_model',
 'dsg.add_sleeve','dsg.create_apply_sleeves','dsg.apply_sleeves','dsg.confirm_sleeve',
 'dsg.add_drill_channel','dsg.prepare_and_create_drill_channels','dsg.continue_to_name_export')
operators={c.bl_idname:c for m in (dsg.core,*dsg._MODULES) for c in getattr(m,'CLASSES',())
           if isinstance(c,type) and issubclass(c,bpy.types.Operator)}
missing=[name for name in required if 'UNDO' not in getattr(operators[name],'bl_options',()) or not getattr(operators[name],'_dsg_history_wrapped',False)]
assert not missing,('Untracked workflow operations',missing)

with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
    os.environ['DSG_HISTORY_ROOT']=td
    for obj in list(bpy.context.scene.objects):bpy.data.objects.remove(obj,do_unlink=True)
    mesh=bpy.data.meshes.new('IOS mesh');mesh.from_pydata([(0,0,0),(2,0,0),(0,2,0),(0,0,2)],[],[(0,2,1),(0,1,3),(1,2,3),(2,0,3)])
    ios=bpy.data.objects.new('IOS reference',mesh);bpy.context.scene.collection.objects.link(ios)
    tooth=ios.copy();tooth.data=mesh.copy();tooth.name='CBCT tooth 11';bpy.context.scene.collection.objects.link(tooth)
    tooth['DSG_fdi']=11
    guide_obj=ios.copy();guide_obj.data=mesh.copy();guide_obj.name='DSG_TestGuide';bpy.context.scene.collection.objects.link(guide_obj)
    material=bpy.data.materials.new('Stage material');guide_obj.data.materials.append(material)
    mod=guide_obj.modifiers.new('Stage settings','SOLIDIFY')
    bpy.context.scene.dicp_props.icp_source_obj=ios;bpy.context.scene.dicp_props.icp_target_obj=tooth
    bpy.context.scene.dsg_props.model_obj=ios;bpy.context.scene.dsg_props.guide_obj=guide_obj
    dicom.RUNTIME.volume=np.zeros((7,7,7),np.int16);dicom.RUNTIME.dims_zyx=(7,7,7)
    dicom.RUNTIME.semantic_labels=np.ones((7,7,7),np.uint8)
    dicom.RUNTIME.segmentations={'TEETH':{'positive':{1},'negative':{2},'mask':np.ones((3,3,3),bool),'origin_zyx':(1,1,1)}}
    stages=[('DICOM','CBCT_READY',0),('DICOM','SIMPLE_DENSITY',0),('DICOM','SIMPLE_REVIEW',0),
            ('DICOM','IMMEDIATE_FDI_REVIEW',0),('DICOM','IMMEDIATE_SELECT_TEETH',0),('DICOM','IMMEDIATE_ARCH_REVIEW',0),
            ('ALIGNMENT','ALIGNMENT',0),('ALIGNMENT','ALIGNMENT',1),('ALIGNMENT','ALIGNMENT',2),('ALIGNMENT','ALIGNMENT',3)]
    stages += [('DSG','ALIGNMENT',n) for n in range(guide.STEP_MODEL,guide.STEP_NAME+1)]
    paths=[]
    for n,(suite,route,step) in enumerate(stages):
        scene=bpy.context.scene;scene['DSG_suite_stage']=suite;scene['DSG_route_step']=route
        # Fixture stores completed stages without running clinical confirmation gates.
        scene.dsg_props['current_step']=step;scene.dicp_props['current_step']=min(step,3)
        ios.matrix_world=Matrix.Translation((n,.1*n,.2*n))
        guide_obj.data.vertices[0].co.x=n;mod.thickness=.01*(n+1)
        material.diffuse_color=(n/len(stages),.2,.3,1)
        scene.dsg_props.engrave_patient_text='Stage '+str(n)
        scene.dicp_props.source_point_count=min(n,3)
        tooth['DSG_fdi']=11+n;tooth.hide_set(n%2==1)
        dicom.RUNTIME.semantic_labels[0,0,0]=n+1
        dicom.RUNTIME.segmentations['TEETH']['positive']={n}
        guide._IMPLANT_STEP_RETURN_STATE[scene.name]={'armed':bool(n%2),'active_implant_name':'implant '+str(n)}
        h.commit(bpy.context,'Stage '+str(n));paths.append(scene[h.STATE_KEY])
        bpy.ops.ed.undo_push(message='Stage '+str(n))
    def check(n):
        scene=bpy.context.scene;ios=bpy.data.objects['IOS reference'];obj=bpy.data.objects['DSG_TestGuide']
        assert scene['DSG_suite_stage']==stages[n][0] and scene['DSG_route_step']==stages[n][1]
        assert scene.dsg_props.current_step==stages[n][2],(n,scene.dsg_props.current_step)
        assert abs(ios.matrix_world.translation.x-n)<1e-6
        assert scene.dicp_props.icp_source_obj==ios and scene.dsg_props.guide_obj==obj
        assert abs(obj.data.vertices[0].co.x-n)<1e-6
        assert abs(obj.modifiers[0].thickness-.01*(n+1))<1e-6
        assert abs(obj.data.materials[0].diffuse_color[0]-n/len(stages))<1e-6
        assert bpy.data.objects['CBCT tooth 11']['DSG_fdi']==11+n
        assert bpy.data.objects['CBCT tooth 11'].hide_get()==bool(n%2)
        assert scene.dsg_props.engrave_patient_text=='Stage '+str(n)
        assert dicom.RUNTIME.semantic_labels[0,0,0]==n+1
        assert dicom.RUNTIME.segmentations['TEETH']['positive']=={n}
        assert guide._IMPLANT_STEP_RETURN_STATE[scene.name]['active_implant_name']=='implant '+str(n)
        # Legacy repair must not regenerate/rewrite a captured workflow stage.
        token=scene[h.STATE_KEY]
        dsg.core.reconcile_workflow_after_undo(scene)
        guide._dsg_restore_implant_step_after_undo()
        assert scene.dsg_props.current_step==stages[n][2] and scene[h.STATE_KEY]==token
        assert not guide.WORKFLOW_RESTORE_PENDING
    for n in range(len(stages)-2,-1,-1):bpy.ops.ed.undo();check(n)
    for n in range(len(stages)-1,-1,-1):h.restore_checkpoint(bpy.context,paths[n]);check(n)
    assert len(stages)==20,len(stages)
    # Real operator: clearing alignment points is recoverable with their input references.
    props=bpy.context.scene.dicp_props;props.source_point_count=3;props.target_point_count=3
    h.commit(bpy.context,'Landmarks ready');bpy.ops.ed.undo_push(message='Landmarks ready')
    assert bpy.ops.dicp.clear_landmarks()=={'FINISHED'}
    bpy.ops.ed.undo_push(message='Clear points frontend')
    assert bpy.context.scene.dicp_props.source_point_count==0
    assert h.undo_previous(bpy.context)=={'FINISHED'}
    assert bpy.context.scene.dicp_props.source_point_count==3 and bpy.context.scene.dicp_props.target_point_count==3
    dicom.RUNTIME.volume=None;dicom.RUNTIME.semantic_labels=None;dicom.RUNTIME.segmentations.clear();h._ARRAY_CACHE.clear();gc.collect()
os.environ.pop('DSG_HISTORY_ROOT',None)
print('ALL_STAGE_HISTORY_PASS',len(stages),'completed stages; native and archived; operator coverage',flush=True)
