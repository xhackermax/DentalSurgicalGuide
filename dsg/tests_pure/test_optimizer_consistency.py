import unittest
from unittest.mock import patch
import numpy as np
from dsg import section_optimizer as sections

class Consistency(unittest.TestCase):
 def test_crest_uses_anatomy_not_initial_platform_or_size(self):
  # Identical world bone surface, two different initial platform heights.
  from dsg.optimizer_reference import crest_reference
  grid=np.arange(-5,5.01,.25);world_z=np.arange(-12,3.01,.25)
  native=np.broadcast_to((world_z<=0)[:,None,None],(len(world_z),len(grid),len(grid)))
  a=crest_reference(native,grid,grid,world_z,0,0)
  b=crest_reference(native,grid,grid,world_z-1,0,0)
  self.assertAlmostEqual(a['height_mm'],b['height_mm']+1)
  self.assertAlmostEqual(a['height_mm'],.125)
 def test_missing_and_fragmented_crest_fail_closed(self):
  from dsg.optimizer_reference import crest_reference
  grid=np.arange(-4,4.01,.25);z=np.arange(-3,3.01,.25)
  native=np.zeros((len(z),len(grid),len(grid)),bool)
  self.assertIsNone(crest_reference(native,grid,grid,z,0,0))
  native[8]=True # an isolated thin island must not become the crest.
  self.assertIsNone(crest_reference(native,grid,grid,z,0,0))
  native[:8,:,grid<=0]=True
  self.assertIsNone(crest_reference(native,grid,grid,z,0,0),'A one-sided rim became a full crest reference')
  native[:]=True
  self.assertIsNone(crest_reference(native,grid,grid,z,0,0),'Map boundary became a false bone crest')
 def test_exact_search_does_not_stop_after_24_poses_of_one_size(self):
  class Field:
   base=np.eye(4);origin=np.zeros(3);frame=np.eye(3);summary={}
   def reference(self,x,y):return {'height_mm':0.,'spread_mm':0.,'samples':16}
   def assess(self,d,l,p):return {'admissible':True,'section_hard_ok':True,'score':100-abs(p[0])-abs(p[1]),'section_fit_fraction':1.,'section_anchor_mm':5.}
  def asset(key,d,l):return dict(id=key,family='TEST',diameter_mm=d,length_mm=l,platform_local_mm=[0,0,l/2],vertices_path='v',faces_path='f',reference='test',dimension_only=True)
  request={'settings':{'max_shift_mm':2.,'max_depth_mm':1.5},'family':'TEST','catalogue':[asset('long',4,14),asset('wide',5,10)]}
  calls=[]
  def exact(field,evaluator,matrix,asset):
   calls.append(asset['id'])
   return {'admissible':asset['id']=='wide','score':1.,'violations':[{'code':'STRUCTURE'}] if asset['id']=='long' else []}
  with patch.object(sections,'exact_section_evaluation',side_effect=exact):
   out=sections.search_sections(request,Field(),None)
  self.assertGreater(len(calls),24)
  self.assertEqual(out['best']['asset']['id'],'wide')
  with patch.object(sections,'exact_section_evaluation',side_effect=exact):
   limited=sections.search_sections(request,Field(),None,verification_budget=24)
  self.assertEqual(limited['status'],'SEARCH_INCOMPLETE')
  self.assertIsNone(limited['best'])
 def test_catalogue_permutation_does_not_change_tied_selection(self):
  from dsg.optimizer_reference import candidate_rank
  rows=[{'asset':{'id':key,'length_mm':l,'diameter_mm':d},'parameters':[0,0,0,0,0],'movement_mm':0.,'evaluation':{'score':score}} for key,l,d,score in [('short',10,5,999),('long',14,4,1),('long_wider',14,4.5,0)]]
  self.assertEqual(min(rows,key=candidate_rank)['asset']['id'],'long_wider')
  self.assertEqual(min(rows[::-1],key=candidate_rank)['asset']['id'],'long_wider')
 def test_anatomical_trajectories_compete_before_selecting_a_shorter_size(self):
  class Field:
   base=np.eye(4);origin=np.zeros(3);frame=np.eye(3);summary={}
   def __init__(self,name):self.request={'axis_frame':{'id':name,'angle_deg':0. if name=='PLACED' else 8.}}
   def reference(self,x,y):return {'height_mm':0.,'spread_mm':0.,'samples':16}
   def assess(self,d,l,p):return {'admissible':False,'section_hard_ok':True,'score':1.,'section_fit_fraction':.97,'section_anchor_mm':4.}
  assets=[dict(id=str(l),family='T',diameter_mm=3.1,length_mm=l,platform_local_mm=[0,0,l/2],vertices_path='v',faces_path='f',reference='test',dimension_only=True) for l in [8,12]]
  request={'settings':{'max_shift_mm':0.,'max_depth_mm':1.5},'family':'T','catalogue':assets}
  def exact(field,evaluator,matrix,asset):
   valid=asset['length_mm']==8 or field.request['axis_frame']['id']=='EXTRACTED_TOOTH:15'
   return {'admissible':valid,'score':1.,'violations':[] if valid else [{'code':'WALL'}]}
  with patch.object(sections,'exact_section_evaluation',side_effect=exact):
   out=sections.search_sections(request,Field('PLACED'),None,additional_fields=[Field('EXTRACTED_TOOTH:15')])
  self.assertEqual(out['best']['asset']['length_mm'],12)
  self.assertEqual(out['best']['axis_reference'],'EXTRACTED_TOOTH:15')

if __name__=='__main__':unittest.main()
