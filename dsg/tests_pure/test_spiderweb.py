import unittest
import numpy as np
from types import SimpleNamespace as R
class SpiderwebTests(unittest.TestCase):
 def test_three_spokes_make_two_rings_without_diagonals(self):
  from dsg.spiderweb import ring_links
  rings=ring_links(['a','b','c'],2,closed=True)
  self.assertEqual(len(rings),6)
  self.assertTrue(all(a[1]==b[1] for a,b in rings))
  self.assertEqual({tuple(sorted((a[0],b[0]))) for a,b in rings},{('a','b'),('b','c'),('a','c')})
 def test_open_frame_sector_has_two_arcs_and_a_real_cycle(self):
  from dsg.spiderweb import ring_links,verify_web
  self.assertEqual(len(ring_links(['a','b'],2,closed=False)),2)
  prim=[{'route_id':x,'member_role':'PRIMARY','nodes':{x+'0':[0,0,0],x+'1':[0,1,0]}} for x in ['a','b']]
  arcs=[{'route_id':'r'+str(i),'member_role':'SECONDARY','origin':'a'+str(i),'port':'b'+str(i),'web_level':i} for i in range(2)]
  self.assertTrue(verify_web(prim+arcs)['spiderweb_topology_verified'])
  with self.assertRaisesRegex(ValueError,'INCOMPLETE'):verify_web(prim+arcs[:1])
 def test_splitting_certified_spokes_preserves_the_curve_exactly(self):
  from dsg.spiderweb import split_spoke
  from dsg.geodesic_router import CandidatePath
  points=np.array([[i, np.sin(i/4),0] for i in range(20)])
  parent=CandidatePath('a','F','S',points,(),20.,20.,'CERTIFIED',0)
  parts,nodes=split_spoke(parent,[5,12])
  np.testing.assert_array_equal(np.vstack([parts[0].points_mm]+[p.points_mm[1:] for p in parts[1:]]),points)
  self.assertEqual([n['index'] for n in nodes],[5,12])
 def test_router_uses_surface_edges_and_hard_height_limit(self):
  from dsg.spiderweb import SurfaceWebRouter
  from test_generative_router import grid_surface,anchor_at
  from dsg.ios_surface import ConstraintSet
  surface=grid_surface();allowed=surface.vertices_mm[:,1]<=4.
  router=SurfaceWebRouter(surface,ConstraintSet(allowed_vertices=allowed),None,.1)
  a=anchor_at(surface,27,'A');b=anchor_at(surface,35,'B')
  path=router.route(a,b)
  self.assertIsNotNone(path)
  self.assertTrue(np.all(path.points_mm[:,1]<=4.))
  self.assertGreaterEqual(path.length_mm,8.)
 def test_certified_spokes_are_not_refaired_when_nodes_move(self):
  from dsg.spiderweb import split_spoke
  from dsg.geodesic_router import CandidatePath
  from dsg.organic_reinforcement import smooth_network_paths
  points=np.array([[i*.3,np.sin(i*.03),0] for i in range(40)])
  parent=CandidatePath('a','F','S',points,(),12.,12.,'CERTIFIED',0)
  parts,_=split_spoke(parent,[12,24]);meta={p.route_id:{'role':'PRIMARY','sleeve_id':'S','pre_faired':True,'reference_points_mm':points.tolist()} for p in parts}
  _,render,_=smooth_network_paths(parts,meta,.3)
  np.testing.assert_array_equal(render[0]['points_mm'],points)
 def test_adaptive_web_builds_surface_arcs_without_forcing_diagonals(self):
  from unittest.mock import patch
  from test_generative_lattice import LatticeTests
  from dsg import generative_frame_worker as worker
  from dsg.spiderweb import generate_spiderweb_paths
  captured={}
  class Ready(Exception):pass
  def capture(*args,**kwargs):captured.update(args=args,kwargs=kwargs);raise Ready()
  with patch.object(worker,'generate_lattice_paths',capture):
   with self.assertRaises(Ready):LatticeTests('test_surface_worker_builds_lattice_without_fan_to_sleeve').test_surface_worker_builds_lattice_without_fan_to_sleeve()
  paths,metadata,report,rejections,_=generate_spiderweb_paths(*captured['args'],request=None)
  self.assertTrue(report['lattice_complete'],rejections)
  self.assertEqual(report['lattice_layout'],'ADAPTIVE_RADIAL_WEB_ON_IOS')
  self.assertGreaterEqual(report['web_ring_levels'],2)
  self.assertEqual(sum(row['role']=='SECONDARY' for row in metadata.values()),2)
 def test_exact_edge_witnesses_match_the_existing_segment_kernel(self):
  from dsg.spiderweb import segment_pair_witnesses
  from dsg.frame_optimizer import _kernel
  rng=np.random.default_rng(619);a,b,c,d=rng.normal(size=(4,100,3));a[0]=b[0];c[1]=d[1];a[2]=b[2];c[2]=d[2];c[3]=a[3]+1.;d[3]=b[3]+1.
  p,q=segment_pair_witnesses(a,b,c,d);kernel=_kernel()
  for i in range(len(a)):
   _,_,distance=kernel.closest_points_segments(a[i],b[i],c[i],d[i])
   self.assertAlmostEqual(float(np.sum((p[i]-q[i])**2)),distance,places=9)
 def test_web_coverage_keeps_physical_attachment_checks(self):
  from dsg.reinforcement_coverage import verify_coverage
  primary=[{'route_id':x,'member_role':'PRIMARY','sleeve_id':'S','points_mm':[[0,0,0],[0,10,0]],'nodes':{x+'0':[0,3,0],x+'1':[0,7,0]}} for x in ['a','b']]
  arcs=[{'route_id':'r'+str(i),'member_role':'SECONDARY','origin':'a'+str(i),'port':'b'+str(i),'web_level':i} for i in range(2)]
  request={'reinforcement_topology':'ADAPTIVE_SPIDERWEB_V1','coverage_policy':{'targets':[]}};report={'lattice_complete':True}
  self.assertTrue(verify_coverage(request,primary+arcs,report)['spiderweb_topology_verified'])
  with self.assertRaisesRegex(ValueError,'PHYSICAL'):verify_coverage(request,primary+arcs,report,{})
  with self.assertRaisesRegex(ValueError,'INCOMPLETE'):verify_coverage(request,primary+arcs[:1],report)
 def test_existing_frame_is_an_explicit_outer_ring(self):
  from dsg.spiderweb import verify_web
  primary=[{'route_id':x,'member_role':'PRIMARY','nodes':{x+'1':[0,1,0]}} for x in ['a','b']]
  arc={'route_id':'arc','member_role':'SECONDARY','origin':'a1','port':'b1','web_level':1}
  with self.assertRaisesRegex(ValueError,'INCOMPLETE'):verify_web(primary+[arc])
  report=verify_web(primary+[arc],frame_rim=True)
  self.assertEqual(report['web_ring_levels'],2)
  self.assertEqual(report['web_internal_ring_levels'],1)
  self.assertTrue(report['web_existing_frame_outer_ring'])
  self.assertEqual(report['web_closed_rings'],0)
 def test_each_sleeve_has_a_web_connected_to_the_original_frame(self):
  from dsg.spiderweb import verify_web
  pieces=[]
  for sleeve in ['S1','S2']:
   for x in ['a','b']:pieces.append({'route_id':sleeve+x,'member_role':'PRIMARY','sleeve_id':sleeve,'nodes':{sleeve+x+'1':[0,1,0]}})
   pieces.append({'route_id':sleeve+'arc','member_role':'SECONDARY','origin':sleeve+'a1','port':sleeve+'b1','web_level':1})
  self.assertTrue(verify_web(pieces,frame_rim=True)['spiderweb_topology_verified'])
 def test_rings_are_measured_from_their_own_sleeve(self):
  from dsg.spiderweb import SurfaceWebRouter
  from test_generative_router import grid_surface
  from dsg.ios_surface import ConstraintSet
  surface=grid_surface();request={'ports':[{'sleeve_id':'S1','point_mm':surface.vertices_mm[0].tolist()},{'sleeve_id':'S2','point_mm':surface.vertices_mm[-1].tolist()}]}
  router=SurfaceWebRouter(surface,ConstraintSet(),request,.1)
  self.assertEqual(router.radial_fields['S1'][0],0.)
  self.assertEqual(router.radial_fields['S2'][-1],0.)
  self.assertGreater(router.radial_fields['S1'][-1],8.)
  self.assertGreater(router.radial_fields['S2'][0],8.)
 def test_a_solid_ball_or_an_open_mesh_cannot_replace_a_frame_ring(self):
  import tempfile
  from pathlib import Path
  from dsg.spiderweb import frame_rim_available
  xyz=np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1]],float);faces=np.array([[0,2,1],[0,1,3],[1,2,3],[2,0,3]])
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'frame.npz';request={'frame_support_file':str(path),'frame_digest':'verified-input'}
   np.savez(path,vertices=xyz,triangles=faces);self.assertFalse(frame_rim_available(request))
   n,m=12,8;xyz=[];faces=[]
   for i in range(n):
    for j in range(m):
     u=2*np.pi*i/n;v=2*np.pi*j/m;xyz.append([(4+np.cos(v))*np.cos(u),(4+np.cos(v))*np.sin(u),np.sin(v)])
   for i in range(n):
    for j in range(m):
     a=i*m+j;b=((i+1)%n)*m+j;c=((i+1)%n)*m+(j+1)%m;d=i*m+(j+1)%m;faces.extend([[a,b,c],[a,c,d]])
   np.savez(path,vertices=xyz,triangles=faces);self.assertTrue(frame_rim_available(request))
   np.savez(path,vertices=xyz,triangles=faces[:-1]);self.assertFalse(frame_rim_available(request))
if __name__=='__main__':unittest.main()
