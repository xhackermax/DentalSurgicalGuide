import unittest
import numpy as np
from dsg.reinforcement_envelope import validate_path_envelope,validate_mesh_envelope
class EnvelopeTests(unittest.TestCase):
 def request(self):
  return {'reinforcement_envelope':{'version':1},'sleeves':[{'id':'S','center':[0,0,0],'axis':[0,0,1],'entry_axis':[0,0,1],'height_mm':8.,'outer_radius_mm':3.,'inner_radius_mm':2.}]}
 def test_entire_tube_must_stay_below_sleeve_entry_plane(self):
  r=self.request()
  with self.assertRaisesRegex(ValueError,'ABOVE_SLEEVE'):validate_path_envelope([[6,0,3.5],[7,0,3.5]],.6,r)
  self.assertTrue(validate_path_envelope([[6,0,2.5],[7,0,2.5]],.6,r)['valid'])
 def test_lower_face_can_not_be_crossed_even_if_vertices_are_outside_disk(self):
  r=self.request();vertices=np.array([[-5,0,-4],[5,0,-4],[0,5,-4.]])
  with self.assertRaisesRegex(ValueError,'SLEEVE_FLAT_FACE'):validate_mesh_envelope(vertices,[[0,1,2]],r)
 def test_tube_can_contact_curved_wall_at_middle_height(self):
  r=self.request();vertices=np.array([[2.9,0,-1],[3.2,0,1],[3.2,1,0]])
  self.assertTrue(validate_mesh_envelope(vertices,[[0,1,2]],r)['valid'])
 def test_cap_crossing_segment_with_clear_endpoints_is_rejected(self):
  with self.assertRaisesRegex(ValueError,'SLEEVE_FLAT_FACE'):
   validate_path_envelope([[-6,0,-4],[6,0,-4]],.3,self.request())
 def test_rotated_clinical_entry_axis_is_not_world_z(self):
  r=self.request();r['sleeves'][0].update(axis=[1,0,0],entry_axis=[-1,0,0],center=[10,0,0])
  with self.assertRaisesRegex(ValueError,'ABOVE_SLEEVE'):validate_path_envelope([[6,6,0],[6,7,0]],.3,r)
  self.assertTrue(validate_path_envelope([[8,6,0],[8,7,0]],.3,r)['valid'])
 def test_frame_origins_only_come_from_upper_facing_triangles(self):
  from dsg.reinforcement_envelope import upper_frame_vertex_mask
  vertices=np.asarray([[0,0,1],[1,0,1],[0,1,1],[0,0,-1],[1,0,-1],[0,1,-1]],float)
  faces=np.asarray([[0,1,2],[3,5,4]])
  self.assertEqual(upper_frame_vertex_mask(vertices,faces,[0,0,1]).tolist(),[True,True,True,False,False,False])
  self.assertEqual(upper_frame_vertex_mask(vertices,faces,[0,0,-1]).tolist(),[False,False,False,True,True,True])
 def test_open_lower_frame_barrier_checks_segment_interiors(self):
  from dsg.reinforcement_envelope import FrameLowerSurfaceBarrier
  v=np.array([[-4,-4,0],[4,-4,0],[4,4,0],[-4,4,0]],float);f=np.array([[0,1,2],[0,2,3]])
  barrier=FrameLowerSurfaceBarrier(v,f)
  self.assertFalse(barrier.clear([[0,0,-2],[0,0,2]],.2))
  self.assertFalse(barrier.clear([[-6,0,.1],[6,0,.1]],.2))
  self.assertTrue(barrier.clear([[-2,0,2],[2,0,2]],.2))
 def test_primary_steering_retains_valid_unpenalized_alternatives(self):
  from dsg.generative_frame_worker import primary_surface_candidates
  from dsg.geodesic_router import generate_geodesic_candidates
  from dsg.ios_surface import ConstraintSet,GenerationConfig
  from test_generative_router import grid_surface,anchor_at
  surface=grid_surface();start=anchor_at(surface,27,'A');end=anchor_at(surface,35,'B');config=GenerationConfig(radius_mm=.1)
  penalty=np.zeros(len(surface.vertices_mm));penalty[28:35]=1000.
  baseline=generate_geodesic_candidates(surface,start,end,ConstraintSet(),config)
  found=primary_surface_candidates(surface,start,end,ConstraintSet(vertex_penalty=penalty),config)
  self.assertTrue(baseline.paths)
  self.assertTrue({tuple(p.surface_vertex_ids) for p in baseline.paths}.issubset({tuple(p.surface_vertex_ids) for p in found.paths}))
 def test_impossible_required_link_stops_the_current_layout(self):
  from unittest.mock import patch
  from dsg import generative_frame_worker as worker
  from dsg.geodesic_router import RouteSearchResult
  from test_generative_lattice import LatticeTests
  original=worker.generate_lattice_paths
  class ProbeComplete(Exception):pass
  def blocked(*args,**kwargs):
   kwargs['envelope_request']={'coverage_policy':{'require_lattice':True}}
   with patch('dsg.geodesic_router.generate_geodesic_candidates',return_value=RouteSearchResult((),(),True,'NO_VALID_SURFACE_ROUTE')) as search:
    value=original(*args,**kwargs)
   self.assertFalse(value[2]['lattice_complete'])
   self.assertEqual(sum(x['reason']=='NO_VALID_LATTICE_ROUTE' for x in value[3]),1)
   self.assertLessEqual(search.call_count,2)
   raise ProbeComplete()
  with patch.object(worker,'generate_lattice_paths',blocked):
   with self.assertRaises(ProbeComplete):LatticeTests('test_surface_worker_builds_lattice_without_fan_to_sleeve').test_surface_worker_builds_lattice_without_fan_to_sleeve()
 def test_frame_sweep_keeps_a_margin_for_final_skin_regularization(self):
  import tempfile
  from pathlib import Path
  r=self.request();r['sleeves'][0].update(center=[1000,1000,0],height_mm=20.)
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder)/'frame_lower.npz';np.savez(p,vertices=[[-4,-4,0],[4,-4,0],[0,4,0]],triangles=[[0,1,2]])
   r['frame_lower_surface_file']=str(p)
   with self.assertRaisesRegex(ValueError,'LOWER_FRAME'):validate_path_envelope([[-1,0,.22],[1,0,.22]],.2,r)
 def test_no_valid_network_message_names_the_requested_limits(self):
  from dsg.reinforcement_coverage import failure_message
  text=failure_message({'status':'NO_VALID_SLEEVE_ANCHORED_LATTICE','report':{}},self.request())
  self.assertIn('superior',text);self.assertIn('sleeve',text)
 def test_lattice_fallback_tries_distinct_origin_pairs_before_route_variants(self):
  from types import SimpleNamespace as R
  from dsg.sleeve_priority import select_sleeve_routes
  routes=[];metrics={}
  for origin in range(4):
   for variant in range(3):
    route=R(route_id=str(origin)+'v'+str(variant),start_id='P'+str(origin),end_id='S'+str(origin),length_mm=20.+origin+variant*.01,points_mm=np.array([[origin*5,0,0],[0,5+origin+variant*.01,0]]))
    routes.append(route);metrics[route.route_id]={'targets':[],'origin_distance_mm':100.-origin*20,'useful_length_mm':route.length_mm}
  _,report=select_sleeve_routes(routes,{r.route_id:'S' for r in routes},lambda a,b:True,minimum_per_sleeve=2,maximum_per_sleeve=3,alternatives_limit=6,route_metrics=metrics)
  by_id={r.route_id:r for r in routes}
  distinct={tuple(sorted(by_id[key].start_id for key in ids)) for ids in report['alternative_route_sets'] if len(ids)==2}
  self.assertGreaterEqual(len(distinct),3)
 def test_layout_budget_is_not_spent_on_duplicate_origin_topologies(self):
  from dsg.reinforcement_coverage import lattice_trial_plan
  alternatives=[['a','b','c'],['a','b'],['a2','b'],['a3','b'],['a','c']]
  nodes={'a':('P0','S0'),'a2':('P0','S0'),'a3':('P0','S0'),'b':('P1','S1'),'c':('P2','S2')}
  trials=lattice_trial_plan(alternatives,route_nodes=nodes)
  self.assertIn(('a','c'),[ids for ids,_ in trials[:3]])
if __name__=='__main__':unittest.main()
