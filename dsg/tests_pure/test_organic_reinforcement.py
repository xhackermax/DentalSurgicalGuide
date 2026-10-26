import unittest
import numpy as np
from dsg.organic_reinforcement import fair_open_path,curvature_profile,transport_frames,mesh_fold_report

class OrganicReinforcementTests(unittest.TestCase):
    def test_removes_edge_zigzag_without_changing_endpoints_or_radius(self):
        x=np.linspace(0,20,201);raw=np.column_stack((x,.15*np.sin(x*22),np.zeros(len(x))))
        pts,info=fair_open_path(raw,.8)
        np.testing.assert_allclose(pts[[0,-1]],raw[[0,-1]],atol=1e-10)
        self.assertLess(info['maximum_reference_distance_mm'],.8*.8+1e-5)
        self.assertLess(curvature_profile(pts).max(),curvature_profile(raw).max()*.2)
        self.assertGreater(np.linalg.norm(np.diff(pts,axis=0),axis=1).min(),.03)

    def test_mandatory_junction_stays_on_same_continuous_branch(self):
        raw=np.array([[0,0,0],[2,.2,0],[4,0,0],[6,.2,0],[8,0,0]],float)
        pts,info=fair_open_path(raw,.5,locked_indices=(2,))
        self.assertLess(np.linalg.norm(pts-raw[2],axis=1).min(),1e-10)
        u,v,t=transport_frames(pts)
        np.testing.assert_allclose(np.sum(u*t,axis=1),0,atol=1e-9)
        np.testing.assert_allclose(np.sum(v*t,axis=1),0,atol=1e-9)
        self.assertTrue(np.isfinite(u).all())

    def test_curvature_and_fold_diagnostics_detect_too_tight_tube(self):
        theta=np.linspace(0,np.pi/2,21);tight=np.column_stack((.2*np.cos(theta),.2*np.sin(theta),theta*0))
        self.assertGreater(curvature_profile(tight).max(),4.9)
        self.assertFalse(mesh_fold_report(tight,1.)['valid'])
        theta=np.linspace(0,np.pi/2,41);gentle=np.column_stack((4*np.cos(theta),4*np.sin(theta),theta*0))
        self.assertTrue(mesh_fold_report(gentle,.5)['valid'])

    def test_near_duplicate_endpoint_does_not_create_ninety_degree_ring(self):
        pts,info=fair_open_path([[0,0,0],[0,.0001,0],[1,0,0],[2,0,0]],.5)
        self.assertGreater(np.linalg.norm(np.diff(pts,axis=0),axis=1).min(),.03)
        self.assertLess(np.degrees(np.arccos(np.clip(np.sum(np.diff(pts,axis=0)[:-1]*np.diff(pts,axis=0)[1:],axis=1)/(np.linalg.norm(np.diff(pts,axis=0)[:-1],axis=1)*np.linalg.norm(np.diff(pts,axis=0)[1:],axis=1)),-1,1))).max(),1.)

class FinalMeshTests(unittest.TestCase):
    def test_every_closed_obstacle_shell_is_checked_for_containment(self):
        from dsg.organic_reinforcement import validate_mesh_keepouts
        from test_generative_bridges import box_obstacle
        big=box_obstacle();v=np.asarray(big['vertices_mm']);f=np.asarray(big['triangles'])
        # Build the test from normalized cubes, independent of fixture bounds.
        cube=(v-v.mean(axis=0))/np.ptp(v,axis=0)*2
        small=cube*.1
        obstacle={'label':'two shells','vertices_mm':np.vstack((small+[10,0,0],small)),
                  'triangles':np.vstack((f,f+len(cube))),'closed':True}
        self.assertFalse(validate_mesh_keepouts(cube,f,[],[obstacle])['valid'])

    def test_protected_solid_inside_triangle_cannot_hide_between_vertices(self):
        from dsg.organic_reinforcement import validate_mesh_keepouts
        from dsg.frame_swept_clearance_core import SphereKeepOut
        vertices=np.array([[-3,-3,0],[3,-3,0],[0,3,0]],float)
        zone=SphereKeepOut('protected',(0.,0.,0.),.5)
        self.assertFalse(validate_mesh_keepouts(vertices,[[0,1,2]],[zone])['valid'])
        self.assertTrue(validate_mesh_keepouts(vertices+[0,0,2],[[0,1,2]],[zone])['valid'])

class OrganicNetworkTests(unittest.TestCase):
    def test_direct_sleeve_branch_keeps_full_geometry_with_locked_interior_stations(self):
        from dsg.organic_reinforcement import smooth_network_paths
        from dsg.geodesic_router import CandidatePath
        points=np.array([[x,.1*np.sin(x),0] for x in np.linspace(0,12,61)])
        path=CandidatePath('direct:SEG0','P1','S1_PORT0',points,(),12.,12.,'SURFACE',0)
        revised,render,report=smooth_network_paths((path,),{path.route_id:{'role':'PRIMARY','sleeve_id':'S1','preserve_joint_fractions':True}},.5)
        np.testing.assert_allclose(revised[0].points_mm[-1],points[-1],atol=1e-10)
        self.assertEqual(len(render),1);self.assertEqual(render[0]['port'],'S1_PORT0')
        self.assertGreater(revised[0].length_mm,11.)

    def test_primary_sections_share_transport_and_render_as_one_branch(self):
        from dsg.organic_reinforcement import smooth_network_paths
        from dsg.geodesic_router import CandidatePath
        def part(i,a,b,start,end):
            p=np.array([[a,0,0],[b,0,0]],float)
            return CandidatePath('main:SEG'+str(i),start,end,p,(),b-a,b-a,'SURFACE',0)
        paths=(part(0,0,4,'P1','J0'),part(1,4,8,'J0','J1'),part(2,8,12,'J1','S1'))
        metadata={p.route_id:{'role':'PRIMARY','sleeve_id':'S1'} for p in paths}
        revised,render,report=smooth_network_paths(paths,metadata,.5)
        self.assertEqual(len(revised),3);self.assertEqual(len(render),1)
        self.assertTrue(report['organic_geometry_valid'])
        self.assertEqual(render[0]['source_routes'],[p.route_id for p in paths])
        for a,b in zip(revised,revised[1:]):
            np.testing.assert_allclose(a.points_mm[-1],b.points_mm[0],atol=1e-12)

if __name__=='__main__':unittest.main()
