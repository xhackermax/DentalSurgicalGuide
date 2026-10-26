import sys,unittest
from pathlib import Path
import numpy as np
from mathutils import Vector
args=sys.argv[sys.argv.index('--')+1:];sys.path.insert(0,args[0])
from dsg.blender.reinforcement_envelope import validate_upper_frame_contact

def box(low,high):
 a,b,c=low;x,y,z=high
 v=np.array([[a,b,c],[x,b,c],[x,y,c],[a,y,c],[a,b,z],[x,b,z],[x,y,z],[a,y,z]],float)
 f=np.array([[0,2,1],[0,3,2],[4,5,6],[4,6,7],[0,1,5],[0,5,4],[1,2,6],[1,6,5],[2,3,7],[2,7,6],[3,0,4],[3,4,7]])
 return v,f
class ContactTests(unittest.TestCase):
 def test_upper_frame_attachment_passes(self):
  fv,ff=box([-4,-4,-1],[4,4,1]);v,f=box([-.5,-.5,.8],[.5,.5,2])
  report=validate_upper_frame_contact(v,f,fv,ff,[0,0,1]);self.assertGreater(report['upper_surface_crossings'],0)
 def test_lower_frame_attachment_is_rejected(self):
  fv,ff=box([-4,-4,-1],[4,4,1]);v,f=box([-.5,-.5,-2],[.5,.5,-.8])
  with self.assertRaisesRegex(ValueError,'LOWER_FRAME'):validate_upper_frame_contact(v,f,fv,ff,[0,0,1])
 def test_coplanar_contact_with_frame_underside_is_rejected(self):
  fv,ff=box([-4,-4,-1],[4,4,1]);v,f=box([-.5,-.5,-2],[.5,.5,-1])
  with self.assertRaisesRegex(ValueError,'LOWER_FRAME'):validate_upper_frame_contact(v,f,fv,ff,[0,0,1])
 def test_changed_entry_axis_invalidates_an_existing_request(self):
  from types import SimpleNamespace
  from unittest.mock import patch
  from dsg.blender.reinforcement_envelope import verify_context_envelope
  from dsg import guide_module as g
  context=SimpleNamespace(scene=SimpleNamespace(dsg_props=SimpleNamespace()))
  request={'reinforcement_envelope':{'frame_entry_axis':[0,0,1]},'sleeves':[]}
  with patch.object(g,'get_insertion_axis',return_value=Vector((0,0,-1))):verify_context_envelope(context,request)
  with patch.object(g,'get_insertion_axis',return_value=Vector((0,0,1))):
   with self.assertRaisesRegex(ValueError,'STALE'):verify_context_envelope(context,request)
if not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ContactTests)).wasSuccessful():raise SystemExit(1)
