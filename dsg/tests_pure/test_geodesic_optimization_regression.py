import unittest
from types import SimpleNamespace as R
import numpy as np
from dsg.sleeve_priority import select_sleeve_routes
class OptimizationRegressionTests(unittest.TestCase):
 def test_available_routes_can_form_network_when_one_preferred_flank_is_unavailable(self):
  routes=[R(route_id=str(i),start_id='P'+str(i),end_id='S'+str(i),length_mm=float(10+i),points_mm=np.asarray([[i*5,0,0],[0,5+i,0]],float)) for i in range(6)]
  owners={r.route_id:'S' for r in routes}
  metrics={r.route_id:{'targets':['left'],'origin_distance_mm':float(10+i),'useful_length_mm':r.length_mm} for i,r in enumerate(routes)}
  chosen,report=select_sleeve_routes(routes,owners,lambda a,b:True,minimum_per_sleeve=2,maximum_per_sleeve=3,preferred_targets=('left','right'),route_metrics=metrics)
  self.assertEqual(len(chosen),3)
  self.assertEqual({r.start_id for r in chosen},{'P3','P4','P5'})
  self.assertEqual(report['uncovered_preferred_targets'],['right'])
  self.assertTrue(report['minimum_connections_satisfied'])
 def test_required_flank_stays_a_hard_constraint(self):
  r=R(route_id='r',start_id='P',end_id='S',length_mm=10.,points_mm=np.asarray([[0,0,0],[10,0,0]],float))
  selected,report=select_sleeve_routes([r],{'r':'S'},lambda a,b:True,required_targets=('right',),route_metrics={'r':{'targets':['left'],'origin_distance_mm':10.,'useful_length_mm':10.}})
  self.assertEqual(selected,())

 def test_surface_certificate_does_not_miss_a_large_nearby_face(self):
  from dsg.geodesic_router import surface_path_certificate
  vertices=[[-100,-100,0],[100,-100,0],[0,100,0]];triangles=[[0,1,2]]
  for i in range(24):
   x=(i%6-3)*.05;y=(i//6-2)*.05;index=len(vertices)
   vertices.extend([[x,y,2],[x+.01,y,2],[x,y+.01,2]]);triangles.append([index,index+1,index+2])
  surface=R(vertices_mm=np.asarray(vertices,float),triangles=np.asarray(triangles,int))
  good=surface_path_certificate(surface,[[-1,0,.2],[1,0,.2]],.5)
  self.assertTrue(good['valid'],good)
  self.assertFalse(surface_path_certificate(surface,[[-1,0,1],[1,0,1]],.5)['valid'])

 def test_candidate_layout_diagnostics_are_serializable(self):
  import json
  from dsg.reinforcement_coverage import layout_trial_report
  report={'sleeve_anchor_selection':{'direct_connection_count':2},'lattice_complete':True}
  trial={'layout_report':layout_trial_report(report)}
  report['sleeve_anchor_selection']['layout_trials']=[trial]
  self.assertIn('lattice_complete',json.dumps(report))

 def test_preferred_flank_gap_is_reported_without_claiming_full_coverage(self):
  from test_coverage_integration import IntegrationCoverageTests
  from dsg.reinforcement_coverage import verify_coverage
  target={'sleeve_id':'S','matrix_world':np.eye(4).tolist(),'tolerance_deg':30.}
  policy={'require_all_flanks':False,'targets':[dict(target,id='left',angle_rad=0.),dict(target,id='right',angle_rad=np.pi)]}
  report=verify_coverage({'coverage_policy':policy},IntegrationCoverageTests().network(),{'lattice_complete':True})
  self.assertEqual(report['uncovered_targets'],['right'])
  self.assertFalse(report['opening_flanks_complete'])
  policy['require_all_flanks']=True
  with self.assertRaisesRegex(ValueError,'FLANK'):verify_coverage({'coverage_policy':policy},IntegrationCoverageTests().network(),{'lattice_complete':True})
 def test_structural_neck_check_does_not_hide_an_interior_ios_gap(self):
  from dsg import generative_frame_worker as worker
  from test_generative_router import grid_surface
  from dsg.geodesic_router import surface_path_certificate
  points=np.asarray([[0,1,2],[0,1,0]]+[[x,1,0] for x in range(1,9)]+[[8,1,2]],float)
  body,_=worker.central_ios_body(points,2.,2.,.5)
  self.assertTrue(surface_path_certificate(grid_surface(),body,.42)['valid'])
  points[5,2]=2.;body,_=worker.central_ios_body(points,2.,2.,.5)
  self.assertFalse(surface_path_certificate(grid_surface(),body,.42)['valid'])

 def test_exact_plane_broadphase_keeps_crossings_and_boundary_contacts(self):
  from dsg.organic_reinforcement import intersecting_plane_candidates
  first=np.asarray([[0,0,0],[2,0,0],[0,2,0]],float)
  others=np.asarray([[[.2,.2,2],[1,.2,2],[.2,1,2]],[[.2,.2,-1],[.2,.2,1],[1,.2,0]],[[.2,.2,0],[1,.2,0],[.2,1,0]]],float)
  self.assertEqual(intersecting_plane_candidates(first,others).tolist(),[False,True,True])

 def test_plane_pruning_keeps_all_existing_exact_crossings(self):
  from dsg.organic_reinforcement import intersecting_plane_candidates
  from dsg.frame_optimizer import _kernel
  kernel=_kernel();rng=np.random.default_rng(8342)
  for _ in range(10):
   first=rng.normal(size=(3,3));others=rng.normal(size=(20,3,3));keep=intersecting_plane_candidates(first,others)
   for i,second in enumerate(others):
    hit=any(kernel._segment_triangle_hit(a,b,second) for a,b in zip(first,np.roll(first,-1,axis=0))) or any(kernel._segment_triangle_hit(a,b,first) for a,b in zip(second,np.roll(second,-1,axis=0)))
    if hit:self.assertTrue(keep[i])

 def test_lattice_alternatives_include_a_smaller_network(self):
  routes=[R(route_id=str(i),start_id='P'+str(i),end_id='S'+str(i),length_mm=float(10+i),points_mm=np.asarray([[i*5,0,0],[0,5+i,0]],float)) for i in range(6)]
  metrics={r.route_id:{'targets':[],'origin_distance_mm':float(10+i),'useful_length_mm':r.length_mm} for i,r in enumerate(routes)}
  _,report=select_sleeve_routes(routes,{r.route_id:'S' for r in routes},lambda a,b:True,minimum_per_sleeve=2,maximum_per_sleeve=3,alternatives_limit=3,route_metrics=metrics)
  self.assertEqual({len(ids) for ids in report['alternative_route_sets']},{2,3})

 def test_lattice_search_varies_joint_positions_before_exhausting_layouts(self):
  from dsg.reinforcement_coverage import lattice_trial_plan
  alternatives=[['a','b','c'],['a','b'],['a','c','d'],['b','c','d']]
  trials=lattice_trial_plan(alternatives,limit=12)
  self.assertLessEqual(len(trials),12)
  self.assertEqual({len(ids) for ids,_ in trials[:4]},{2,3})
  self.assertGreater(len({tuple(f) for ids,f in trials[:4]}),1)
  self.assertEqual(len(trials),len({(tuple(ids),tuple(f)) for ids,f in trials}))

 def test_geodesic_lattice_checks_organic_secondary_before_acceptance(self):
  from unittest.mock import patch
  from test_generative_lattice import LatticeTests
  from dsg import generative_frame_worker as worker
  original=worker.generate_lattice_paths;observed=[]
  def checked(*args,**kwargs):
   kwargs['organic_preflight']=True
   value=original(*args,**kwargs)
   self.assertGreaterEqual(value[2]['organic_secondary_paths_verified'],3)
   self.assertEqual(value[2]['organic_primary_paths_verified'],2)
   observed.append(True)
   return value
  with patch.object(worker,'generate_lattice_paths',checked):
   LatticeTests('test_surface_worker_builds_lattice_without_fan_to_sleeve').test_surface_worker_builds_lattice_without_fan_to_sleeve()
  self.assertTrue(observed)
 def test_alternative_budget_is_shared_between_two_and_three_branches(self):
  routes=[R(route_id=str(i),start_id='P'+str(i),end_id='S'+str(i),length_mm=float(10+i),points_mm=np.asarray([[i*5,0,0],[0,5+i,0]],float)) for i in range(8)]
  metrics={r.route_id:{'targets':[],'origin_distance_mm':float(10+i),'useful_length_mm':r.length_mm} for i,r in enumerate(routes)}
  _,report=select_sleeve_routes(routes,{r.route_id:'S' for r in routes},lambda a,b:True,minimum_per_sleeve=2,maximum_per_sleeve=3,alternatives_limit=12,route_metrics=metrics)
  counts=[len(ids) for ids in report['alternative_route_sets']]
  self.assertGreaterEqual(counts.count(2),4)
  self.assertGreaterEqual(counts.count(3),4)

 def test_collar_control_hull_stays_outside_nominal_tube_body(self):
  from dsg.organic_reinforcement import bounded_collar_handle
  rng=np.random.default_rng(1749)
  axis=np.array([1.,0,0]);center=np.zeros(3)
  for _ in range(200):
   start=rng.normal(size=3);start[0]=-rng.uniform(.001,4.)
   direction=rng.normal(size=3);direction/=np.linalg.norm(direction)
   handle=bounded_collar_handle(start,center,axis,direction,4.)
   controls=np.asarray([start,start+direction*handle,center-axis*2.,center])
   for t in np.linspace(0,1,41):
    point=(1-t)**3*controls[0]+3*t*(1-t)**2*controls[1]+3*t*t*(1-t)*controls[2]+t**3*controls[3]
    self.assertLessEqual(float(point@axis),1.e-10)
  self.assertEqual(bounded_collar_handle([-1,0,0],center,axis,[-1,0,0],2.),2.)
  with self.assertRaisesRegex(ValueError,'SUPPORT_CROSSES'):
   bounded_collar_handle([.1,0,0],center,axis,[1,0,0],2.)
