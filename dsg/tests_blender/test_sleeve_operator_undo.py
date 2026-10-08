"""Real sleeve geometry generation and exact undo, with a synthetic gate fixture."""
import bpy,sys,os,tempfile,gc
from unittest.mock import patch
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import dsg
dsg.register()
from dsg import workflow_history as h,guide_module as guide,dicom_module as dicom
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
    os.environ['DSG_HISTORY_ROOT']=td
    if not bpy.data.objects.get('Cube'):
        bpy.ops.mesh.primitive_cube_add();bpy.context.object.name='Cube'
    context=bpy.context;scene=context.scene;props=scene.dsg_props
    frame=bpy.data.objects['Cube'];frame.name=guide.FRAME_NAME
    props.frame_obj=frame
    implant=frame.copy();implant.data=frame.data.copy();implant.name=guide.IMPLANT_PREFIX+'_01'
    scene.collection.objects.link(implant);props.implant_obj=implant
    scene['DSG_suite_stage']='DSG';props['current_step']=guide.STEP_SLEEVE
    h.begin(context,'Synthetic frame and implant');baseline=scene[h.STATE_KEY]
    expected=set(scene.objects.keys());matrix=implant.matrix_world.copy()
    # Only prerequisite certification is mocked; generation, wrappers, archive,
    # transforms, meshes, native undo and restoration all execute in Blender.
    with patch.object(guide,'_require_workflow_stage',return_value=True):
        assert bpy.ops.dsg.add_sleeve()=={'FINISHED'}
    previews=guide.get_sleeve_preview_objects()
    assert len(previews)==1 and len(previews[0].data.vertices)>100
    assert bpy.data.objects[implant.name].matrix_world==matrix
    completed=scene[h.STATE_KEY];assert completed!=baseline
    bpy.ops.ed.undo_push(message='Sleeve UI completion')
    assert h.undo_previous(bpy.context)=={'FINISHED'}
    assert set(bpy.context.scene.objects.keys())==expected and not guide.get_sleeve_preview_objects()
    assert bpy.context.scene.dsg_props.frame_obj==bpy.data.objects[guide.FRAME_NAME]
    h.restore_checkpoint(bpy.context,completed)
    assert len(guide.get_sleeve_preview_objects())==1
    h.restore_checkpoint(bpy.context,baseline)
    assert set(bpy.context.scene.objects.keys())==expected and not guide.get_sleeve_preview_objects()
    dicom.RUNTIME.volume=None;dicom.RUNTIME.semantic_labels=None;dicom.RUNTIME.segmentations.clear();h._ARRAY_CACHE.clear();gc.collect()
os.environ.pop('DSG_HISTORY_ROOT',None)
print('SLEEVE_OPERATOR_UNDO_PASS',flush=True)
