import math,unittest
from types import SimpleNamespace as R
import numpy as np
from dsg.reinforcement_coverage import augment_request,prioritize_pairs,verify_coverage
class IntegrationCoverageTests(unittest.TestCase):
 def test_wall_normal_does_not_discard_an_unchecked_flank(self):
  sleeve={'id':'S','implant_name':'I','matrix_world':np.eye(4).tolist(),'height_mm':7.,'outer_radius_mm':4.,'axis':[0,0,1]}
  request={'sleeves':[sleeve],'radius_mm':1.25,'supports':[{'id':'Z'},{'id':'A'}],'ports':[],'lateral_openings':[{'implant':'I','width_mm':4.7,'angle_rad':0.}]}
  def project(label,point):return {'id':label,'point_mm':(np.asarray(point)+[0,0,1]).tolist(),'original_mm':list(point),'normal':[0,0,1]}
  augment_request(request,project)
  self.assertEqual(len({p['opening_target'] for p in request['ports']}),2)
  self.assertEqual([r['id'] for r in request['supports']],['Z','A'])
 def test_farthest_first_and_both_flanks_within_pair_budget(self):
  request={'sleeves':[{'id':'S','center':[0,0,0]}],'supports':[{'id':'near','original_mm':[2,0,0]},{'id':'far','original_mm':[20,0,0]}],'ports':[{'id':p,'point_mm':[0,0,0],'original_mm':[0,0,0],'opening_target':p[:1]} for p in ['a1','a2','b1','b2']]}
  pairs=[R(port=R(sleeve_id='S'),start=R(id=a),end=R(id=p['id'])) for a in ['near','far'] for p in request['ports']]
  chosen=prioritize_pairs(pairs,request,4)
  self.assertEqual([(p.start.id,p.end.id[0]) for p in chosen],[('far','a'),('near','a'),('far','b'),('near','b')])
 def network(self):
  primary=[{'route_id':p,'member_role':'PRIMARY','nodes':{p+'0':[0,0,0],p+'1':[1,0,0]},'points_mm':[[0,0,0],[1,0,0]],'sleeve_id':'S'} for p in ['a','b']]
  secondary=[{'route_id':'s'+str(i),'member_role':'SECONDARY','origin':a,'port':b} for i,(a,b) in enumerate([('a0','b0'),('a1','b1'),('a0','b1')])]
  return primary+secondary
 def test_real_triangle_required_and_physical_receipts_checked(self):
  request={'coverage_policy':{'targets':[]}};pieces=self.network();report={'lattice_complete':True}
  self.assertTrue(verify_coverage(request,pieces,report)['geodesic_lattice_verified'])
  with self.assertRaisesRegex(ValueError,'TRIANGULATED'):verify_coverage(request,pieces[:-1],report)
  with self.assertRaisesRegex(ValueError,'PHYSICAL'):verify_coverage(request,pieces,report,receipts={})
  receipts={p:{'sleeve_id':'S','positive_volume_overlap':True,'witness_mm':[1,0,0]} for p in ['a','b']}
  self.assertTrue(verify_coverage(request,pieces,report,receipts)['physical_witnesses'])

 def test_real_surface_router_builds_a_triangulated_geodesic_network(self):
  from unittest.mock import patch
  from test_generative_lattice import LatticeTests
  from dsg import generative_frame_worker as worker
  from dsg.organic_reinforcement import smooth_network_paths
  original=worker.generate_lattice_paths;observed=[]
  def audited(*args,**kwargs):
   paths,metadata,report,rejections,local=original(*args,**kwargs)
   _,pieces,_=smooth_network_paths(paths,metadata,.5)
   receipt=verify_coverage({'coverage_policy':{'targets':[]}},pieces,report)
   self.assertEqual(receipt['primary_count'],2)
   self.assertGreaterEqual(receipt['secondary_count'],3)
   observed.append(receipt)
   return paths,metadata,report,rejections,local
  with patch.object(worker,'generate_lattice_paths',audited):
   LatticeTests('test_surface_worker_builds_lattice_without_fan_to_sleeve').test_surface_worker_builds_lattice_without_fan_to_sleeve()
  self.assertEqual(len(observed),1)

 def test_functional_mesh_is_routed_around_before_final_rejection(self):
  from test_generative_router import grid_surface,anchor_at
  from test_generative_bridges import box_obstacle
  from dsg.ios_surface import ConstraintSet,GenerationConfig,check_mesh_obstacles
  from dsg.geodesic_router import generate_geodesic_candidates
  from dsg.reinforcement_coverage import functional_surface_mask
  surface=grid_surface();obstacle=box_obstacle((3.5,2.5,-1),(4.5,3.5,1))
  config=GenerationConfig(radius_mm=.15)
  allowed,report=functional_surface_mask(surface,(obstacle,),config.radius_mm,config.surface_tolerance_mm)
  self.assertFalse(allowed[31]);self.assertGreater(report['blocked_vertices'],0)
  outcome=generate_geodesic_candidates(surface,anchor_at(surface,27,'A'),anchor_at(surface,35,'B'),ConstraintSet(mesh_obstacles=(obstacle,),vertex_penalty=(~allowed).astype(float)*1000.),config)
  self.assertTrue(outcome.paths,outcome.rejections)
  for path in outcome.paths:self.assertTrue(check_mesh_obstacles(path.points_mm,config.radius_mm,(obstacle,))[0])

 def test_protected_endpoint_is_reported_before_surface_search(self):
  from test_generative_router import grid_surface,anchor_at
  from test_generative_bridges import box_obstacle
  from dsg.reinforcement_coverage import protected_anchor_reason
  surface=grid_surface();obstacle=box_obstacle((3.5,2.5,-1),(4.5,3.5,1))
  self.assertIn('CONTAINMENT',protected_anchor_reason(surface,anchor_at(surface,31,'blocked'),.15,(obstacle,)))
  self.assertIsNone(protected_anchor_reason(surface,anchor_at(surface,27,'clear'),.15,(obstacle,)))

 def test_missing_flank_prunes_the_real_pool_without_exhausting_budget(self):
  from types import SimpleNamespace as R
  from dsg.sleeve_priority import select_sleeve_routes
  routes=[R(route_id=str(i),start_id='A'+str(i),end_id='L',length_mm=10.,points_mm=np.asarray([[i,0,0],[0,5,0]],float)) for i in range(20)]
  metrics={r.route_id:{'targets':['left'],'origin_distance_mm':10.,'useful_length_mm':10.} for r in routes}
  selected,report=select_sleeve_routes(routes,{r.route_id:'S' for r in routes},lambda a,b:True,route_metrics=metrics,required_targets=('left','right'))
  self.assertEqual(selected,());self.assertTrue(report['search_complete'])
  self.assertLessEqual(report['search_states_visited'],1)
  self.assertEqual(report['missing_targets_in_pool'],['right'])

 def test_action_diagnostic_survives_minimal_workflow_label_filter(self):
  import ast
  from pathlib import Path
  import dsg
  path=Path(dsg.__file__).parent/'blender/generative_frame.py'
  node=next(n for n in ast.parse(path.read_text(encoding='utf-8')).body if isinstance(n,ast.FunctionDef) and n.name=='_draw_status')
  scope={};exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),'exec'),scope)
  rows=[]
  class Raw:
   def label(self,**kwargs):rows.append(kwargs['text'])
  class Minimal:
   _layout=Raw()
   def label(self,**kwargs):raise AssertionError('A diagnostic must not be silently filtered')
  scope['_draw_status'](Minimal(),'Sin celosía completa: falta un anclaje válido al otro lado de la apertura lateral.')
  self.assertIn('falta un anclaje válido',' '.join(rows))
