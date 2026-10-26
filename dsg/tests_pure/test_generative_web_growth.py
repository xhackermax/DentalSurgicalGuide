import unittest
import numpy as np
class GenerativeWebGrowthTests(unittest.TestCase):
 def test_branching_reuses_physical_curves_and_exposes_secondary_nodes(self):
  from dsg.generative_web_growth import BranchNetwork
  from dsg.geodesic_router import CandidatePath
  points=np.array([[0,y,0]for y in np.linspace(0,12,49)],float)
  route=CandidatePath('side:SEG0','F','J',points,(),12.,12.,'IOS',0,.6)
  network=BranchNetwork((route,),{'side:SEG0':{'role':'SECONDARY','sleeve_id':'','pre_faired':True,'continuous_branch':True}},1.25)
  node=network.bind('side',19)
  paths,metadata=network.pack()
  from dsg.organic_reinforcement import smooth_network_paths
  _,render,_=smooth_network_paths(paths,metadata,1.25)
  self.assertEqual(render[0]['member_role'],'SECONDARY');self.assertEqual(render[0]['radius_mm'],.6)
  self.assertIn(node,render[0]['nodes']);np.testing.assert_array_equal(render[0]['points_mm'],points)
 def test_failed_growth_never_changes_the_existing_geometry(self):
  from dsg.generative_web_growth import BranchNetwork
  from dsg.geodesic_router import CandidatePath
  points=np.array([[x,0,0]for x in np.linspace(0,15,61)])
  route=CandidatePath('main:SEG0','F','P',points,(),15.,15.,'IOS',0,1.)
  network=BranchNetwork((route,),{'main:SEG0':{'role':'PRIMARY','sleeve_id':'S','pre_faired':True}},1.)
  before=network.pack();checkpoint=network.checkpoint();network.bind('main',21);network.rollback(checkpoint)
  after=network.pack();self.assertEqual([p.start_id for p in before[0]],[p.start_id for p in after[0]])
  self.assertEqual([p.end_id for p in before[0]],[p.end_id for p in after[0]])
  np.testing.assert_array_equal(before[0][0].points_mm,after[0][0].points_mm)
 def test_growth_can_branch_from_secondary_and_requires_both_physical_parents(self):
  from dsg.spiderweb import verify_web
  prim=[dict(route_id=x,member_role='PRIMARY',nodes={x+'0':[0,0,0],x+'1':[0,1,0]})for x in ['a','b']]
  arcs=[dict(route_id='r'+str(i),member_role='SECONDARY',origin='a'+str(i),port='b'+str(i),web_level=i,nodes={'c'+str(i):[0,0,0]})for i in range(2)]
  growth=[dict(route_id='g',member_role='SECONDARY',web_kind='GROWTH',origin='F2',port='c0',nodes={'child':[1,1,0]}),dict(route_id='h',member_role='SECONDARY',web_kind='GROWTH',origin='child',port='c1')]
  report=verify_web(prim+arcs+growth,frame_nodes=['F2'])
  self.assertEqual(report['web_growth_connected_branches'],2)
  with self.assertRaisesRegex(ValueError,'ORPHAN'):verify_web(prim+arcs+growth)
 def test_distinct_geodesics_between_same_joints_form_cell_but_duplicate_curve_fails(self):
  from dsg.spiderweb import verify_web
  prim=[dict(route_id=x,member_role='PRIMARY',nodes={x+'0':[0,0,0],x+'1':[0,1,0]})for x in ['a','b']]
  arcs=[dict(route_id='r'+str(i),member_role='SECONDARY',origin='a'+str(i),port='b'+str(i),web_level=i,points_mm=[[0,i,0],[4,i,0]])for i in range(2)]
  growth=dict(route_id='g',member_role='SECONDARY',web_kind='GROWTH',origin='a0',port='b0',points_mm=[[0,0,0],[2,2,0],[4,0,0]])
  self.assertEqual(verify_web(prim+arcs+[growth])['web_growth_connected_branches'],1)
  growth['points_mm']=arcs[0]['points_mm'][::-1]
  with self.assertRaisesRegex(ValueError,'DUPLICATE_CURVE'):verify_web(prim+arcs+[growth])
 def test_growth_creates_cells_on_surface_without_moving_backbone(self):
  from test_generative_router import grid_surface,anchor_at
  from dsg.ios_surface import prepare_surface,ConstraintSet,GenerationConfig
  from dsg.frame_generator import FramePerimeter,build_frame_graph
  from dsg.geodesic_router import CandidatePath
  from dsg.generative_web_growth import grow_web,BranchNetwork
  from dsg.organic_reinforcement import smooth_network_paths
  from dsg.frame_optimizer import evaluate_frame
  from dsg.reinforcement_coverage import continuous_groups
  original=grid_surface();surface=prepare_surface(original.vertices_mm*3,original.triangles,original.csr_offsets,original.csr_destinations,original.csr_lengths_mm*3,source_id='grid',source_role='IOS',world_matrix=np.eye(4),unit_scale_mm=1.)
  supports=tuple(anchor_at(surface,i,k)for i,k in [(0,'F1'),(8,'F2'),(54,'F3'),(62,'F4')]);positions={a.id:surface.vertices_mm[i]for a,i in zip(supports,[0,8,54,62])}
  perimeter=FramePerimeter('frame',np.array(list(positions.values())),supports,'fixture')
  curves=[np.array([[0,y,0]for y in np.linspace(0,18,73)]),np.array([[24,y,0]for y in np.linspace(0,18,73)])]
  paths=tuple(CandidatePath(k+':SEG0',f,p,points,(),18.,18.,'IOS',0,.8)for k,f,p,points in zip(['a','b'],['F1','F2'],['P1','P2'],curves))
  metadata={p.route_id:dict(role='PRIMARY',sleeve_id='S',pre_faired=True)for p in paths};config=GenerationConfig(radius_mm=.8);constraints=ConstraintSet()
  paths,meta,report,errors=grow_web(surface,perimeter,paths,metadata,supports,positions,constraints,config,{},lambda _:None,target_edges=6)
  self.assertGreaterEqual(report['web_growth_branches'],4,errors)
  _,render,_=smooth_network_paths(paths,meta,.8)
  for piece,curve in zip(render[:2],curves):np.testing.assert_array_equal(piece['points_mm'],curve)
  checked=evaluate_frame(build_frame_graph(perimeter,paths,config),constraints,config,continuous_primary_groups=continuous_groups(paths,meta))
  self.assertEqual(checked.status,'CANDIDATE',checked.rejections)
if __name__=='__main__':unittest.main()
