import unittest,numpy as np
from scipy.sparse import csr_matrix
class AxialRadialWebTests(unittest.TestCase):
 def grid(self,nx=31,ny=25):
  vertices=np.array([[x,y,.03*np.sin(x/5)*np.sin(y/4)]for y in range(ny)for x in range(nx)])
  faces=[]
  for y in range(ny-1):
   for x in range(nx-1):
    a=y*nx+x;faces.extend([[a,a+1,a+nx],[a+1,a+nx+1,a+nx]])
  return vertices,np.array(faces)
 def test_axis_frame_is_orthonormal_and_oriented_to_exterior(self):
  from dsg.axial_radial_web import axis_basis
  n=np.array([.2,-.4,.8]);n/=np.linalg.norm(n);basis=axis_basis(n)
  np.testing.assert_allclose(basis.T@basis,np.eye(3),atol=1e-12);np.testing.assert_allclose(basis[:,2],n)
 def test_radials_and_levels_share_nodes_and_cover_four_sides(self):
  from dsg.axial_radial_web import build_radial_graph
  v,f=self.grid();sources={'S1':[12*31+15]};starts={k:i for k,i in zip(['F1','F2','F3','F4','F5','F6','F7','F8'],[0,15,30,12*31,12*31+30,24*31,24*31+15,24*31+30])}
  result=build_radial_graph(v,f,np.ones(len(v),bool),sources,starts,spacing=3.)
  self.assertGreaterEqual(result['report']['cycle_count'],12)
  self.assertEqual(set(result['frame_nodes']),set(starts));self.assertEqual(result['report']['used_sleeves'],['S1'])
  self.assertGreaterEqual(result['report']['radial_transverse_junctions'],16)
  self.assertGreater(np.ptp(np.array(list(result['nodes'].values())),axis=0)[:2].min(),20.)
  self.assertTrue(all(e['points_mm'][0]==result['nodes'][e['origin']]and e['points_mm'][-1]==result['nodes'][e['port']]for e in result['pieces']))
 def test_multiple_sleeves_both_receive_distal_routes(self):
  from dsg.axial_radial_web import build_radial_graph
  v,f=self.grid();sources={'S1':[12*31+7],'S2':[12*31+23]};starts={'F1':0,'F2':30,'F3':24*31,'F4':24*31+30,'F5':12*31,'F6':12*31+30}
  result=build_radial_graph(v,f,np.ones(len(v),bool),sources,starts,spacing=3.)
  self.assertEqual(result['report']['used_sleeves'],['S1','S2']);self.assertEqual(result['report']['frame_origin_count'],6)
  self.assertGreaterEqual(result['report']['cycle_count'],8)
 def test_disconnected_sleeve_is_not_silently_ignored(self):
  from dsg.axial_radial_web import build_radial_graph
  v,f=self.grid();allowed=np.ones(len(v),bool);allowed[(v[:,0]>=14)&(v[:,0]<=16)]=False
  with self.assertRaisesRegex(ValueError,'UNCONNECTED_SLEEVE'):build_radial_graph(v,f,allowed,{'S1':[12*31+7],'S2':[12*31+23]},{'F1':0,'F2':24*31},spacing=3.)
 def test_pinned_distal_route_reaches_central_sleeve(self):
  from dsg.axial_radial_web import build_radial_graph
  v,f=self.grid();sources={'S0':[12*31+15],'S1':[12*31+4],'S2':[12*31+26]}
  starts={'F0':(15,'S0'),'F1':0,'F2':30,'F3':24*31,'F4':24*31+30}
  result=build_radial_graph(v,f,np.ones(len(v),bool),sources,starts,spacing=3.,spread_basis=np.eye(3)[:,:2])
  self.assertEqual(result['report']['used_sleeves'],['S0','S1','S2'])
  self.assertTrue(any(r['frame']=='F0'and r['sleeve']=='S0'for r in result['radials']))
if __name__=='__main__':unittest.main()
