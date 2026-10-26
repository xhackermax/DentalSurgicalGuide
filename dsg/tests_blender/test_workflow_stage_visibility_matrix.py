"""Full role matrix, including fixtures for steps not yet generated clinically."""
import sys,unittest
from unittest.mock import patch
from contextlib import ExitStack
import bpy
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import dsg
dsg.register()
from dsg import core,guide_module as g
from dsg.blender import workflow_visibility as w,protected_neighbors,implant_plane

class VisibilityMatrixTests(unittest.TestCase):
 def test_all_roles_in_both_directions_and_routes(self):
  objects={}
  roles={'model':g.ROLE_MODEL,'passive':g.ROLE_PASSIVE,'frame':g.ROLE_FRAME,'guide':g.ROLE_GUIDE,'implant':g.ROLE_IMPLANT,'micro':g.ROLE_MICROSCREW_VISUAL,'sleeve':g.ROLE_SLEEVE,'irrigation':g.ROLE_IRRIGATION,'reinforcement':g.ROLE_REINFORCEMENT,'drill':g.ROLE_DRILL_VISUAL,'contour':'','path':'','lumen':''}
  names={'contour':g.CONTOUR_CURVE_NAME,'path':g.IRR_PREVIEW_PATH_PREFIX+'Matrix','lumen':g.IRR_LUMEN_DIAGNOSTIC_NAME,'irrigation':g.IRR_PREVIEW_PREFIX+'Matrix','drill':g.ANIMATED_DRILL_PREFIX+'Matrix'}
  for key,role in roles.items():
   bpy.ops.mesh.primitive_cube_add();obj=bpy.context.object
   obj.name=names.get(key,'Matrix_'+key);obj['dental_suite_dsg_role']=role
   if role:g.register_dsg_object(obj,role,obj.name)
   obj.hide_set(True);objects[key]=obj
  objects['lumen']['DSG_irrigation_lumen_diagnostic']=True
  expected=[{'passive'},{'passive','implant'},{'passive','contour'},{'frame','passive','implant','micro'},{'guide','frame','implant','sleeve'},{'guide','model','implant','irrigation','path','lumen'},{'guide','model','reinforcement'},{'guide','drill'},{'guide','passive'},{'guide'}]
  scene=bpy.context.scene;scene[implant_plane.VISIBLE_KEY]=False
  scene.dsg_props.model_obj=objects['model']
  try:
   with ExitStack() as stack:
    for name,key in [('_workflow_model_candidate','model'),('get_confirmed_passive_model_obj','passive'),('get_passive_model_obj','passive'),('_workflow_frame_candidate','frame'),('_workflow_guide_candidate','guide')]:stack.enter_context(patch.object(g,name,return_value=objects[key]))
    for name,key in [('get_all_implant_objects','implant'),('get_confirmed_microscrew_objects','micro'),('get_sleeve_preview_objects','sleeve')]:stack.enter_context(patch.object(g,name,return_value=[objects[key]]))
    stack.enter_context(patch.object(g,'get_pending_microscrew_preview',return_value=None))
    stack.enter_context(patch.object(g,'create_implant_emergence_tube',return_value=None))
    stack.enter_context(patch.object(g,'rebuild_implant_safety_halos'))
    stack.enter_context(patch.object(protected_neighbors,'sync'))
    for route in (core.ROUTE_SIMPLE,core.ROUTE_IMMEDIATE):
     scene.dsg_suite_settings['workflow_route']=scene.dsg_suite_settings.bl_rna.properties['workflow_route'].enum_items[route].value
     for direction,steps in [('forward',range(10)),('backward',reversed(range(10)))]:
      for step in steps:
       with self.subTest(route=route,direction=direction,step=step):
        scene.dsg_props['current_step']=step
        self.assertTrue(g._restore_workflow_stage(bpy.context,scene,step))
        bpy.context.view_layer.update()
        self.assertEqual({k for k,o in objects.items() if o.visible_get()},expected[step])
        for k in expected[step]:objects[k].hide_set(True)
        w.reveal(bpy.context);bpy.context.view_layer.update()
        self.assertEqual({k for k,o in objects.items() if o.visible_get()},expected[step])
  finally:
   scene.dsg_props.model_obj=None
   for obj in objects.values():bpy.data.objects.remove(obj,do_unlink=True)

if not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(VisibilityMatrixTests)).wasSuccessful():raise SystemExit(1)
print('WORKFLOW_STAGE_VISIBILITY_MATRIX_PASS 40 stage-role checks')
