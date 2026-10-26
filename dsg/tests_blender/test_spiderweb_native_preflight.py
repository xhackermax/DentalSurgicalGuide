"""Physical rejection, cleanup and scene isolation in the worker adapter."""
import sys,unittest,tempfile,json
from pathlib import Path
from types import SimpleNamespace as R
from unittest.mock import patch
import numpy as np
args=sys.argv[sys.argv.index('--')+1:];sys.path.insert(0,args[0])
import dsg;dsg.register()
from dsg.blender import native_primary_preflight as preflight,generative_frame as gf,organic_reinforcement as organic,reinforcement_envelope as envelope
from dsg import guide_module as g
class NativePreflightTests(unittest.TestCase):
 def test_failed_layout_is_cleaned_and_returned_for_another_search(self):
  with patch.object(gf,'case_fingerprint',return_value='fp'),patch.object(gf,'stage_candidate',side_effect=ValueError('LOWER_FRAME_CONTACT')),patch.object(gf,'discard_candidate') as clean:
   report=preflight.preflight_web_candidate({'case_fingerprint':'fp'},{})
  self.assertFalse(report['valid']);self.assertEqual(report['reason'],'LOWER_FRAME_CONTACT');clean.assert_called_once()
 def test_unexpected_failure_is_not_reported_as_a_valid_layout(self):
  with patch.object(gf,'case_fingerprint',return_value='fp'),patch.object(gf,'stage_candidate',side_effect=RuntimeError('worker problem')),patch.object(gf,'discard_candidate') as clean:
   with self.assertRaisesRegex(RuntimeError,'worker problem'):preflight.preflight_web_candidate({'case_fingerprint':'fp'},{})
  clean.assert_called_once()
 def test_only_mesh_certified_radials_enter_the_selection_pool(self):
  names=['frame','ios','guide'];objects={name:R(name=name)for name in names};fake=R(app=R(background=True),types=R(Scene=R(dsg_props=True)),context=object(),data=R(objects=objects),ops=R(wm=R(open_mainfile=lambda **kw:None)))
  def mesh(context,pieces,request):
   if pieces[0]['route_id']=='bad':raise ValueError('LOWER_FRAME_CONTACT')
   return [{'DSG_organic_final_support_verified':True,'DSG_organic_final_keepouts_verified':True,'DSG_reinforcement_envelope_verified':True,'DSG_web_frame_rim_verified':True,'DSG_sleeve_anchor_receipt_json':'{}','DSG_frame_anchor_receipt_json':'{}'}]
  paths=[R(route_id=key,start_id='F',end_id='P',points_mm=np.array([[0,0,0],[3,0,0]],float))for key in ['good','bad']]
  with tempfile.TemporaryDirectory() as folder:
   request={'native_case_file':'immutable-case.blend','case_fingerprint':'fp','frame_name':'frame','surface_name':'ios','guide_name':'guide','radius_mm':1.,'job_dir':folder}
   with patch.dict(sys.modules,{'bpy':fake}),patch.object(gf,'case_fingerprint',return_value='fp'),patch.object(gf,'case_geometry_fingerprint',side_effect=lambda o:o.name),patch.object(envelope,'verify_context_envelope'),patch.object(organic,'build_network',side_effect=mesh),patch.object(g,'safe_remove_object_with_data') as clean:
    valid,report=preflight.preflight_primary_pool(request,paths,{'good':'S','bad':'S'},lambda message:None)
   self.assertEqual(valid,{'good'});self.assertEqual(report['native_primary_meshes_checked'],2);self.assertEqual(report['native_primary_meshes_valid'],1);clean.assert_called_once()
   self.assertEqual(json.loads((Path(folder)/'native_primary_preflight.json').read_text())['records'][1]['reason'],'LOWER_FRAME_CONTACT')
if not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(NativePreflightTests)).wasSuccessful():raise SystemExit(1)
