"""Native rotations remain editable; exact collisions still gate confirmation."""
import sys,time
from unittest.mock import patch
import bpy
from mathutils import Matrix
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import dsg
dsg.register()
from dsg import core,guide_module as g
from dsg.blender import safety_volume as safety
try:
    control=bpy.data.objects.new('MotionController',None);bpy.context.scene.collection.objects.link(control)
    bpy.ops.mesh.primitive_cube_add(size=2)
    implant=bpy.context.object;implant.parent=control
    bpy.context.scene.dsg_props.current_step=g.STEP_IMPLANT
    safety.remember(implant)
    control.matrix_world=Matrix.Rotation(.1,4,'Y')
    safety.STATE['busy']=True;bpy.context.view_layer.update();safety.STATE['busy']=False
    moved=control.matrix_world.copy()
    safety.STATE['checked'].pop(implant.name,None)
    with patch.object(core,'infer_stage',return_value=core.STAGE_GUIDE),patch.object(g,'STEP_IMPLANT',bpy.context.scene.dsg_props.current_step),patch.object(g,'get_all_implant_objects',return_value=[implant]),patch.object(safety,'contacts',return_value=['ProtectedTooth']) as expensive:
        safety.update(bpy.context.scene,bpy.context.evaluated_depsgraph_get())
        assert expensive.call_count==0,'Heavy collision checking still runs inside movement handler'
        assert control.matrix_world==moved,'Rotation was overwritten'
        safety.STATE['pending_since']=time.monotonic()-1
        safety._audit_timer()
        assert expensive.call_count==1
        assert control.matrix_world==moved,'Contact warning reset the rotation'
        class Reporter:
            min_canal_distance_mm=2.
            def report(self,level,message):self.message=message
        reporter=Reporter()
        assert not safety.gate(bpy.context,reporter)
        assert 'ProtectedTooth' in reporter.message
    with patch.object(g,'_require_workflow_stage',return_value=True),patch.object(g,'get_active_guide_obj',return_value=implant),patch.object(safety,'gate',return_value=False) as export_guard:
        assert g.DSG_OT_ExportGuideSTL.execute(Reporter(),bpy.context)=={'CANCELLED'}
        assert export_guard.call_count==1,'Export bypasses exact implant safety'
    print('IMPLANT_INTERACTIVE_MOTION_PASS: cheap handler, retained rotation, deferred contact warning, exact confirmation gate',flush=True)
finally:
    dsg.unregister()
