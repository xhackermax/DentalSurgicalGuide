"""One closed-model action performs safe holes first, then existing base creation."""
import sys,unittest
from types import SimpleNamespace
from unittest.mock import patch
import bpy
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import dsg
dsg.register()
from dsg import guide_module as g

class Layout:
 def __init__(self):self.operators=[];self.texts=[]
 def operator(self,name,**kw):self.operators.append(name);self.texts.append(kw.get('text',''));return SimpleNamespace()
 def label(self,**kw):self.texts.append(kw.get('text',''))
 def __getattr__(self,key):return lambda *a,**k:self

class CombinedClosureTests(unittest.TestCase):
 def setUp(self):
  mesh=bpy.data.meshes.new('CombinedClosureInput')
  mesh.from_pydata([(-2,-2,0),(2,-2,0),(2,2,0),(-2,2,0),(-1,-1,2),(1,-1,2),(1,1,2),(-1,1,2)],[],[(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)])
  mesh.update();self.obj=bpy.data.objects.new('CombinedClosureInput',mesh);bpy.context.scene.collection.objects.link(self.obj)
  self.before=[tuple(v.co) for v in mesh.vertices]
  bpy.context.scene.dsg_props.model_obj=self.obj
  g._clear_model_topology_cache()
 def tearDown(self):
  bpy.context.scene.dsg_props.model_obj=None
  for name in ('CombinedClosureInput',g.HOLE_REPAIRED_MODEL_NAME,g.CLOSED_MODEL_NAME):
   obj=bpy.data.objects.get(name)
   if obj:g.safe_remove_object_with_data(obj)
 def run_operator(self):
  try:return bpy.ops.dsg.close_model_base()
  except RuntimeError:return {'CANCELLED'}
 def test_one_action_runs_both_real_geometry_stages_in_order(self):
  events=[];holes=g.close_scanned_model_holes;base=g.close_open_dental_model_base
  def fill(*args,**kw):events.append('holes');return holes(*args,**kw)
  def close(*args,**kw):events.append('base');self.assertTrue(args[1].get(g.SCAN_HOLES_PROCESSED_FLAG));return base(*args,**kw)
  with patch.object(g,'close_scanned_model_holes',side_effect=fill),patch.object(g,'close_open_dental_model_base',side_effect=close):
   self.assertEqual(self.run_operator(),{'FINISHED'})
  self.assertEqual(events,['holes','base'])
  closed=bpy.context.scene.dsg_props.model_obj
  self.assertTrue(g.get_model_topology_report_cached(closed)['solid'])
  self.assertTrue(closed.get(g.CLOSED_MODEL_ACCEPTED_FLAG))
  self.assertEqual([tuple(v.co) for v in self.obj.data.vertices],self.before)
 def test_reviewed_holes_are_not_processed_again(self):
  self.obj[g.SCAN_HOLES_PROCESSED_FLAG]=True
  with patch.object(g,'close_scanned_model_holes') as holes,patch.object(g,'close_open_dental_model_base',return_value=(self.obj,{'solid':True})) as base:
   self.assertEqual(self.run_operator(),{'FINISHED'})
   holes.assert_not_called();base.assert_called_once()
 def test_hole_failure_stops_base_creation(self):
  with patch.object(g,'close_scanned_model_holes',side_effect=RuntimeError('SAFE_HOLE_TEST_FAILURE')),patch.object(g,'close_open_dental_model_base') as base:
   self.assertEqual(self.run_operator(),{'CANCELLED'})
   base.assert_not_called()
  self.assertIs(bpy.context.scene.dsg_props.model_obj,self.obj)
  self.assertEqual([tuple(v.co) for v in self.obj.data.vertices],self.before)
 def test_assistant_phase_matches_combined_action_before_hole_review(self):
  from dsg import step_guide
  self.assertEqual(step_guide._model_phase(bpy.context),'closed_model')
  self.assertIn('CREAR MODELO CERRADO',step_guide.TIP['closed_model'][0])
 def test_registered_step_dispatch_uses_combined_action(self):
  layout=Layout()
  with patch.object(g,'get_model_topology_report_cached',return_value={'checked':True,'boundary_edges':8,'solid':False}):
   g._DSG_STEP_DRAWERS[g.STEP_MODEL](layout,layout,bpy.context,bpy.context.scene.dsg_props)
  self.assertEqual(layout.operators,['dsg.close_model_base'])
 def test_panel_has_one_button_with_requested_name(self):
  layout=Layout()
  with patch.object(g,'get_model_topology_report_cached',return_value={'checked':True,'boundary_edges':8,'solid':False}):
   g._draw_step_model_axis(layout,layout,bpy.context,bpy.context.scene.dsg_props)
  self.assertEqual(layout.operators,['dsg.close_model_base'])
  self.assertIn('CREAR MODELO CERRADO',layout.texts)

r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(CombinedClosureTests))
if not r.wasSuccessful():raise SystemExit(1)
print('COMBINED_CLOSED_MODEL_PASS')
