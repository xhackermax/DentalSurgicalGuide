import math,unittest
from types import SimpleNamespace as R
import numpy as np
from dsg.reinforcement_coverage import opening_targets,route_metrics,continuous_groups,verify_coverage
from dsg.sleeve_priority import select_sleeve_routes

def route(name,origin,port,length,end=(4,0,0)):
 return R(route_id=name,start_id=origin,end_id=port,length_mm=length,points_mm=np.asarray([(12,0,0),end],float))
class CoverageTests(unittest.TestCase):
 def sleeve(self):return {'id':'S1','implant_name':'I1','center':[0,0,0],'axis':[0,0,1],'matrix_world':np.eye(4).tolist(),'outer_radius_mm':4.,'inner_radius_mm':2.5,'height_mm':10.}
 def test_flank_targets_are_outside_window_and_allow_full_radius(self):
  rows=opening_targets([self.sleeve()],[{'implant':'I1','angle_rad':0.,'width_mm':4.7}],1.25)
  self.assertEqual(len(rows),2)
  self.assertTrue(rows[0]['angle_rad']<0<rows[1]['angle_rad'])
  for row in rows:
   self.assertGreater(4.04*abs(math.sin(row['angle_rad'])),2.35+1.25)
 def test_missing_opening_record_is_not_invented(self):
  with self.assertRaises(ValueError):opening_targets([self.sleeve()],[{'implant':'wrong','angle_rad':0.,'width_mm':4.7}],1.25)
 def test_longer_route_wins_equal_validated_coverage(self):
  a,b=route('short','A','P0',10),route('long','A','P0',15)
  b.points_mm=np.asarray([(12,0,0),(8,3,0),(4,0,0)],float)
  owners={'short':'S1','long':'S1'}
  metrics={key:{'origin_distance_mm':12.,'useful_length_mm':r.length_mm,'targets':[]} for key,r in [('short',a),('long',b)]}
  selected,report=select_sleeve_routes([a,b],owners,lambda a,b:True,route_metrics=metrics)
  self.assertEqual(selected[0].route_id,'long');self.assertEqual(report['direct_total_length_mm'],15)
 def test_far_origin_wins_conflicting_near_origin(self):
  a,b=route('near','A','P0',5),route('far','B','P0',20)
  metrics={'near':{'origin_distance_mm':4.,'useful_length_mm':5.,'targets':[]},'far':{'origin_distance_mm':16.,'useful_length_mm':20.,'targets':[]}}
  chosen,_=select_sleeve_routes([a,b],{'near':'S1','far':'S1'},lambda a,b:False,route_metrics=metrics)
  self.assertEqual(chosen[0].route_id,'far')
 def test_both_flanks_required_not_replaced_by_more_unrelated_routes(self):
  pool=[route('left','A','L',15),route('right','B','R',18),route('other','C','O',25)]
  metrics={r.route_id:{'origin_distance_mm':r.length_mm,'useful_length_mm':r.length_mm,'targets':[r.route_id] if r.route_id!='other' else []} for r in pool}
  chosen,report=select_sleeve_routes(pool,{r.route_id:'S1' for r in pool},lambda a,b:True,route_metrics=metrics,required_targets=('left','right'))
  self.assertEqual(set(report['covered_targets']),{'left','right'});self.assertEqual(len(chosen),3)
  chosen,report=select_sleeve_routes(pool[:1],{'left':'S1'},lambda a,b:True,route_metrics=metrics,required_targets=('left','right'))
  self.assertEqual(chosen,());self.assertIn('right',report['uncovered_targets'])
 def test_direct_branches_are_not_a_lattice(self):
  request={'sleeves':[self.sleeve()],'coverage_policy':{'targets':[]},'supports':[]}
  with self.assertRaisesRegex(ValueError,'LATTICE'):
   verify_coverage(request,[{'member_role':'PRIMARY','route_id':'a','origin':'A','port':'P','sleeve_id':'S1','points_mm':[[8,0,0],[4,0,0]]}],{})
 def test_loop_length_is_capped_by_structural_reach(self):
  request={'sleeves':[self.sleeve()],'supports':[{'id':'A','original_mm':[12,0,0]}],'coverage_policy':{'targets':[]}}
  rows=route_metrics([route('loop','A','P',1000)],{'loop':'S1'},request)
  self.assertLess(rows['loop']['useful_length_mm'],30)
 def test_continuous_groups_do_not_combine_distinct_bars(self):
  paths=[R(route_id='a:SEG0'),R(route_id='a:SEG1'),R(route_id='b:SEG0'),R(route_id='s')]
  meta={r.route_id:{'role':'PRIMARY' if r.route_id!='s' else 'SECONDARY'} for r in paths}
  self.assertEqual(continuous_groups(paths,meta),{'a':['a:SEG0','a:SEG1'],'b':['b:SEG0']})
if __name__=='__main__':unittest.main()
