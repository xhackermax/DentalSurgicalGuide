import tempfile,unittest
from pathlib import Path
import numpy as np

class AnatomicalFrame(unittest.TestCase):
 def test_extracted_tooth_frame_and_candidate_are_authorized_geometrically(self):
  from dsg.implant_search_frames import search_frames,validate_candidate_reference
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);angle=np.radians(8);rotation=np.array([[np.cos(angle),0,np.sin(angle)],[0,1,0],[-np.sin(angle),0,np.cos(angle)]])
   v=np.array([[x,y,z] for z in (-7,7) for x in (-1,1) for y in (-1,1)])@rotation.T
   np.save(root/'v.npy',v)
   request={'implant':{'matrix':np.eye(4).tolist()},'platform':[0,0,5], 'target_fdi':15,
            'sockets':[{'name':'Tooth15','fdi':15,'vertices_path':str(root/'v.npy'),'matrix':np.eye(4).tolist()}],
            'settings':{'max_shift_mm':3.,'max_depth_mm':1.5}}
   frames=search_frames(request);self.assertEqual(len(frames),2)
   seed=frames[1];matrix=np.asarray(seed['matrix']);self.assertAlmostEqual(seed['angle_deg'],8)
   asset={'platform_local_mm':[0,0,6]};matrix[:3,3]=np.asarray(request['platform'])-matrix[:3,:3]@np.asarray(asset['platform_local_mm'])
   row={'matrix':matrix.tolist(),'asset':asset,'parameters':[0,0,0,0,0],'axis_reference':seed['id']}
   validate_candidate_reference(request,row)
   row['axis_reference']='UNAUTHORIZED'
   with self.assertRaises(ValueError):validate_candidate_reference(request,row)
   request['settings']['anatomical_frame_max_angle_deg']=5.
   self.assertEqual(len(search_frames(request)),1)
   row['axis_reference']=seed['id'];row['matrix'][0][3]+=1
   with self.assertRaises(ValueError):validate_candidate_reference(request,row)
 def test_no_unrelated_tooth_can_change_the_search_axis(self):
  from dsg.implant_search_frames import search_frames
  req={'implant':{'matrix':np.eye(4).tolist()},'platform':[0,0,5],'target_fdi':15,'settings':{},'sockets':[{'fdi':16}]}
  self.assertEqual(len(search_frames(req)),1)

if __name__=='__main__':unittest.main()
