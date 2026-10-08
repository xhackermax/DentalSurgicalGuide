"""Undo cancels active modal RNA references and pending stage callbacks."""
import bpy,sys,os,tempfile,gc
from types import SimpleNamespace
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import dsg
dsg.register()
from dsg import workflow_history as h,lifecycle,guide_module as guide,dicom_module as dicom
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
    os.environ['DSG_HISTORY_ROOT']=td
    if not bpy.data.objects.get('Cube'):
        bpy.ops.mesh.primitive_cube_add();bpy.context.object.name='Cube'
    context=bpy.context;h.begin(context,'ICP baseline');token=context.scene[h.STATE_KEY]
    original=bpy.data.objects['Cube'].matrix_world.copy()
    calls=[]
    operator=SimpleNamespace(bl_idname='dicp.run_alignment',bl_label='ICP',as_pointer=lambda:12345,
        cancel=lambda context:calls.append('cancel'),_timer=None,_dsg_undo_epoch=h._UNDO_EPOCH)
    h._track_modal(operator,context,{'RUNNING_MODAL'},token)
    bpy.data.objects['Cube'].location.x+=4
    context.scene.dicp_props.alignment_running=True
    def _restore_timer():
        bpy.data.objects['Cube'].location.x=999
    _restore_timer.__module__=guide.__name__
    timer=lifecycle.register_timer(_restore_timer,first_interval=100)
    def dicom_refresh():return None
    dicom_refresh.__module__=dicom.__name__
    dicom_timer=lifecycle.register_timer(dicom_refresh,first_interval=100)
    guide.WORKFLOW_RESTORE_PENDING.add((context.scene.name,1))
    def modal(self,context,event):
        calls.append('unexpected stale modal execution');return {'RUNNING_MODAL'}
    wrapped=h._wrap_modal(modal)
    assert wrapped(operator,context,SimpleNamespace(type='Z',ctrl=True,value='PRESS'))=={'CANCELLED'}
    assert calls==['cancel'],calls
    assert bpy.data.objects['Cube'].matrix_world==original
    assert not bpy.context.scene.dicp_props.alignment_running
    assert not bpy.app.timers.is_registered(timer) and not guide.WORKFLOW_RESTORE_PENDING
    assert not bpy.app.timers.is_registered(dicom_timer)
    assert not dicom.RUNTIME.update_lock and not dicom.RUNTIME.undo_in_progress
    assert not h._ACTIVE_MODALS
    assert h.automation_suspended()
    assert not guide._schedule_zero_boundary_auto_advance(bpy.context.scene,bpy.data.objects['Cube'])
    assert wrapped(operator,bpy.context,SimpleNamespace(type='TIMER',ctrl=False,value='NOTHING'))=={'CANCELLED'}
    assert calls==['cancel']
    # A nested loader modal remains busy until its result is imported.
    h._DEPTH=1
    loader=SimpleNamespace(bl_idname='dicom_wizard_pro.next',bl_label='Load',as_pointer=lambda:12346,
        cancel=lambda context:calls.append('loader cancelled'),_timer=None)
    execute=h._wrap_execute(lambda self,context:{'RUNNING_MODAL'})
    assert execute(loader,bpy.context)=={'RUNNING_MODAL'} and h._busy()
    h._DEPTH=0
    h._before_undo()
    assert 'loader cancelled' in calls and not h._ACTIVE_MODALS
    dicom.RUNTIME.volume=None;dicom.RUNTIME.semantic_labels=None;dicom.RUNTIME.segmentations.clear();h._ARRAY_CACHE.clear();gc.collect()
os.environ.pop('DSG_HISTORY_ROOT',None)
print('MODAL_HISTORY_PASS',flush=True)
