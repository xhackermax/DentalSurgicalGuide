import sys,bpy,json
from unittest.mock import patch
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import dsg;dsg.register()
from dsg import workflow_history as history,guide_module as guide
from dsg.blender import implant_optimizer as opt
bpy.ops.mesh.primitive_cube_add();original=bpy.context.object;original.name='DSG_Implant_UndoFreeze'
original.hide_set(True)
bpy.ops.mesh.primitive_cube_add();preview=bpy.context.object;preview.name=opt.PREVIEW
preview['DSG_optimizer_preview']=True;preview['DSG_optimizer_original']=original.name
preview['DSG_optimizer_visibility_backup']=json.dumps({original.name:{'scene':bpy.context.scene.name,'view_layer':bpy.context.view_layer.name,'hidden':False,'disabled':False}})
opt.STATE.update(scene=bpy.context.scene,preview_view_layer=bpy.context.view_layer,result={'best':{}},target=original.name)
bpy.app.timers.register(opt.poll,first_interval=20)
bpy.app.timers.register(opt.watch_preview,first_interval=20)
history._before_undo()
assert not bpy.app.timers.is_registered(opt.poll),'Optimizer worker callback survived undo_pre'
assert not bpy.app.timers.is_registered(opt.watch_preview),'Preview callback survived undo_pre'
assert opt.STATE['scene'] is None and opt.STATE.get('preview_view_layer') is None,'RNA references survived undo_pre'
assert bpy.data.objects.get(opt.PREVIEW)==preview,'undo_pre mutated Blender object IDs'
assert original.hide_get(),'undo_pre changed visibility before native undo'
history._after_undo()
opt._recover_after_undo()
assert bpy.data.objects.get(opt.PREVIEW) is None and not original.hide_get(),'Deferred preview recovery failed'
with patch.object(guide,'_reconcile_workflow_after_undo') as repair:
    guide._dsg_restore_implant_step_after_undo()
    assert not repair.called,'Undo handler reconciles scene synchronously'
print('OPTIMIZER_UNDO_FREEZE_PASS:timers_stopped,rna_released,no_pre_swap_mesh_mutation,deferred_recovery,guide_repair_deferred')
