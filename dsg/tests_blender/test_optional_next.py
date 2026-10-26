"""Optional Next availability, retained confirmed work, real skip transitions."""
import sys
from types import SimpleNamespace
from unittest.mock import patch

import bpy

sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import dsg
dsg.register()
from dsg import core, guide_module as g
from dsg.blender import optional_next as nxt


class Layout:
    def __init__(self):
        self.actions = []
    def operator(self, identifier, **kwargs):
        self.actions.append((identifier,kwargs.get('text','')))
        return self
    def __getattr__(self,name):
        return lambda *args,**kwargs:self


class Reporter:
    def report(self,level,message):
        self.message = message


try:
    scene = bpy.context.scene
    scene.dsg_suite_settings.workflow_route = 'SIMPLE'
    scene[core.SUITE_STAGE_KEY] = core.STAGE_GUIDE
    props = scene.dsg_props
    for obj in list(scene.objects):
        bpy.data.objects.remove(obj,do_unlink=True)
    props.current_step = g.STEP_MODEL
    with patch.object(nxt,'call') as call:
        assert nxt.advance(bpy.context,Reporter()) == {'CANCELLED'}
        assert not call.called, 'Next bypasses a required stage'
    bpy.ops.mesh.primitive_cube_add(size=4)
    fixture = bpy.context.object
    fixture.name = 'Next fixture'
    fixture['DSG_sleeves_applied'] = True
    props.model_obj = fixture
    props.frame_obj = fixture
    props.guide_obj = fixture
    # Only clinical fixture prerequisites are stubbed; the existing skip and
    # frame-confirm operators execute for real and write their status markers.
    with patch.object(g,'_workflow_requirement_report',side_effect=lambda context,step,scene=None:{'ok':True,'target':step}), \
         patch.object(g,'_require_workflow_stage',return_value=True), \
         patch.object(g,'prepare_final_cut_references'):
        props.current_step = g.STEP_FRAME
        assert bpy.ops.dsg.optional_next() == {'FINISHED'}
        assert props.current_step == g.STEP_SLEEVE and fixture['DSG_frame_confirmed']
        props.current_step = g.STEP_IRRIGATION
        assert bpy.ops.dsg.optional_next() == {'FINISHED'}
        assert props.current_step == g.STEP_REINFORCEMENT
        assert fixture['DSG_irrigation_resolution'] == 'SKIPPED'
        props.current_step = g.STEP_REINFORCEMENT
        assert bpy.ops.dsg.optional_next() == {'FINISHED'}
        assert props.current_step == g.STEP_DRILL
        assert fixture['DSG_reinforcement_resolution'] == 'SKIPPED'
        # Confirmed work must be applied, never passed to destructive skip ops.
        props.current_step = g.STEP_IRRIGATION
        fixture['DSG_irrigation_resolution'] = ''
        calls = []
        with patch.object(nxt,'call',side_effect=lambda action:calls.append(action) or True), \
             patch.object(g,'get_pending_irrigation_preview',return_value=fixture), \
             patch.object(g,'get_confirmed_irrigation_walls',return_value=[fixture]):
            assert nxt.advance(bpy.context,Reporter()) == {'FINISHED'}
        assert calls == ['dsg.remove_last_irrigation','dsg.confirm_irrigation','dsg.continue_after_irrigation']
        props.current_step = g.STEP_REINFORCEMENT
        calls = []
        with patch.object(nxt,'call',side_effect=lambda action:calls.append(action) or True), \
             patch.object(g,'get_pending_reinforcement_preview',return_value=fixture), \
             patch.object(g,'get_confirmed_reinforcement_curves',return_value=[fixture]):
            assert nxt.advance(bpy.context,Reporter()) == {'FINISHED'}
        assert calls == ['dsg.cancel_reinforcement_preview','dsg.apply_reinforcements']
        # A failing prerequisite prevents cancellation or modification of work.
        with patch.object(g,'_require_workflow_stage',return_value=False), patch.object(nxt,'call') as call:
            assert nxt.advance(bpy.context,Reporter()) == {'CANCELLED'}
            assert not call.called
    # A single Next action is present even while an optional preview is pending.
    for draw, getter in [(g._draw_step_frame,'get_pending_microscrew_preview'),
                         (g._draw_step_irrigation,'get_pending_irrigation_preview'),
                         (g._draw_step_reinforcement,'get_pending_reinforcement_preview')]:
        fixture['DSG_irrigation_resolution'] = ''
        layout = Layout()
        with patch.object(g,getter,return_value=fixture):
            draw(layout,layout,bpy.context,props)
        assert layout.actions.count(('dsg.optional_next','SIGUIENTE')) == 1, layout.actions
    print('OPTIONAL_NEXT_PASS: required stages blocked, real frame/irrigation/reinforcement transitions, confirmed work preserved, preview Next UI',flush=True)
finally:
    dsg.unregister()
