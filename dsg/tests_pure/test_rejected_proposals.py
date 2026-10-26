import unittest,numpy as np
from dsg.implant_optimization import search_position,search_size,search_joint_sizes
def asset(d,l):return dict(id=f'{d}x{l}',family='T',diameter_mm=d,length_mm=l,platform_local_mm=[0,0,l/2],vertices_path='v',faces_path='f',reference='TEST')
def rejected(code,excess):return {'admissible':False,'score':0.,'reason':code,'violations':[{'code':code,'excess_mm':excess}]}
class Rejected(unittest.TestCase):
 def test_closest_is_never_a_valid_best(self):
  result=search_position(lambda m,asset=None:rejected('APICAL',abs(m[2,3]+1.5)),np.eye(4),[0,0,0],max_shift_mm=0,max_tilt_deg=0,max_depth_mm=1.5)
  self.assertEqual(result['status'],'NO_FEASIBLE');self.assertIsNone(result['best'])
  self.assertAlmostEqual(result['closest']['matrix'][2][3],-1.5)
 def test_critical_structure_outranks_better_bone(self):
  def evaluate(m,asset=None):return rejected('STRUCTURE',.01) if asset['diameter_mm']==5 else rejected('WALL',3.)
  result=search_size(evaluate,[asset(4,13),asset(5,13)],'T',np.eye(4),[0,0,0])
  self.assertEqual(result['closest']['asset']['diameter_mm'],4)
 def test_graft_scenario_is_still_not_admissible(self):
  def evaluate(m,asset=None):return dict(rejected('WALL',.8),scenario_eligible=True)
  result=search_size(evaluate,[asset(4,13)],'T',np.eye(4),[0,0,0])
  self.assertIsNone(result['best']);self.assertEqual(result['status'],'GRAFT_SCENARIO')
  self.assertFalse(result['conditional']['evaluation']['admissible'])
 def test_joint_respects_depth_and_lateral_limits(self):
  seen=[]
  def evaluate(m,asset=None):
   seen.append(m.copy());ok=abs(m[0,3]-.5)<1e-8 and abs(m[2,3]+asset['length_mm']/2+1.5)<1e-8
   return {'admissible':ok,'score':1.,'violations':[] if ok else [{'code':'WALL','excess_mm':1.}]}
  result=search_joint_sizes(evaluate,[asset(4,13)],'T',np.eye(4),[0,0,0],max_shift_mm=.5,max_depth_mm=1.5)
  self.assertIsNotNone(result['best']);self.assertAlmostEqual(result['best']['parameters'][2],-1.5)
  self.assertTrue(all(np.linalg.norm(m[:2,3])<=.5+1e-9 and -1.5-1e-9<=m[2,3]+6.5<=0 for m in seen))
if __name__=='__main__':unittest.main()
