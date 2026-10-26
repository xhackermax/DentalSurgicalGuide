import unittest
import numpy as np
from dsg.ios_surface import prepare_surface, SurfaceAnchor, ConstraintSet, GenerationConfig
from dsg.geodesic_router import generate_geodesic_candidates
from dsg.frame_swept_clearance_core import SphereKeepOut,check_swept_tube_clearance


def grid_surface():
    xyz=np.array([[x,y,0] for y in range(7) for x in range(9)],float);faces=[]
    for y in range(6):
        for x in range(8):
            a=y*9+x;faces.extend([[a,a+1,a+9],[a+1,a+10,a+9]])
    rows=[set() for _ in xyz]
    for face in faces:
        for a,b in ((face[0],face[1]),(face[1],face[2]),(face[2],face[0])):rows[a].add(b);rows[b].add(a)
    offsets=[0];dst=[];lengths=[]
    for i,row in enumerate(rows):
        for j in sorted(row):dst.append(j);lengths.append(np.linalg.norm(xyz[i]-xyz[j]))
        offsets.append(len(dst))
    return prepare_surface(xyz,faces,offsets,dst,lengths,source_id='grid',source_role='PASSIVE',world_matrix=np.eye(4),unit_scale_mm=1.)


def anchor_at(surface,index,label):
    face=next(i for i,row in enumerate(surface.triangles) if index in row);bary=[0.,0.,0.];bary[list(surface.triangles[face]).index(index)]=1.
    return SurfaceAnchor(label,surface.fingerprint,face,tuple(bary),0)


class RouterTests(unittest.TestCase):
    def setUp(self):self.surface=grid_surface();self.a=anchor_at(self.surface,27,'A');self.b=anchor_at(self.surface,35,'B')

    def test_smoothing_stays_on_sheet_and_preserves_endpoints(self):
        from dsg.geodesic_router import smooth_surface_path
        values=np.array([[0,3,0],[1,3,0],[2,4,0],[3,3,0],[4,3,0]],float)
        result=smooth_surface_path(self.surface,values,(27,28,38,30,31),ConstraintSet(),GenerationConfig(radius_mm=.1))
        self.assertTrue(np.allclose(result[[0,-1]],values[[0,-1]]))
        self.assertLess(float(np.max(result[:,1])),4.)
        self.assertLess(float(np.max(np.abs(result[:,2]))),1e-8)

    def test_lateral_alternative_avoids_blocked_direct_route(self):
        zone=SphereKeepOut('block',(4.,3.,0.),1.)
        result=generate_geodesic_candidates(self.surface,self.a,self.b,ConstraintSet(protected_zones=(zone,)),GenerationConfig(radius_mm=.15))
        self.assertTrue(result.paths)
        for path in result.paths:self.assertTrue(check_swept_tube_clearance(path.points_mm,[.15]*len(path.points_mm),(zone,)).clear)

    def test_repeat_preserves_route_ids_and_order(self):
        args=(self.surface,self.a,self.b,ConstraintSet(),GenerationConfig(radius_mm=.1))
        one=generate_geodesic_candidates(*args);two=generate_geodesic_candidates(*args)
        self.assertEqual([p.route_id for p in one.paths],[p.route_id for p in two.paths])

    def test_blocked_endpoint_is_not_reenabled(self):
        allowed=np.ones(len(self.surface.vertices_mm),bool);allowed[27]=False
        result=generate_geodesic_candidates(self.surface,self.a,self.b,ConstraintSet(allowed_vertices=allowed),GenerationConfig())
        self.assertFalse(result.paths)

    def test_edge_crosses_keepout_with_free_vertices(self):
        zone=SphereKeepOut('small',(4.5,3.,0.),.15)
        result=generate_geodesic_candidates(self.surface,self.a,self.b,ConstraintSet(protected_zones=(zone,)),GenerationConfig(radius_mm=.1))
        self.assertTrue(result.paths)
        for path in result.paths:
            self.assertTrue(check_swept_tube_clearance(path.points_mm,[.1]*len(path.points_mm),(zone,)).clear)

    def test_larger_radius_rechecks_route(self):
        zone=SphereKeepOut('block',(4.,3.,0.),2.)
        result=generate_geodesic_candidates(self.surface,self.a,self.b,ConstraintSet(protected_zones=(zone,)),GenerationConfig(radius_mm=3.))
        self.assertFalse(result.paths)

    def test_missing_required_geometry_is_unverifiable(self):
        result=generate_geodesic_candidates(self.surface,self.a,self.b,ConstraintSet(required_zones_complete=False),GenerationConfig())
        self.assertEqual(result.status,'UNVERIFIABLE')

    def test_mesh_obstacle_rejects_crossing_and_contained_paths(self):
        from dsg.ios_surface import check_mesh_obstacles
        xyz=np.array([[x,y,z] for z in (-1,1) for y in (-1,1) for x in (-1,1)],float)
        faces=np.array([[0,1,3],[0,3,2],[4,6,7],[4,7,5],[0,4,5],[0,5,1],[2,3,7],[2,7,6],[0,2,6],[0,6,4],[1,5,7],[1,7,3]])
        zone={'label':'cube','vertices_mm':xyz,'triangles':faces,'closed':True}
        self.assertFalse(check_mesh_obstacles([[-2,0,0],[2,0,0]],.1,(zone,))[0])
        self.assertFalse(check_mesh_obstacles([[0,0,0],[.5,0,0]],.1,(zone,))[0])
        self.assertTrue(check_mesh_obstacles([[-2,2,0],[2,2,0]],.1,(zone,))[0])


class SurfaceCertificateTests(unittest.TestCase):
    def test_segments_follow_surface_not_only_control_points(self):
        from dsg.geodesic_router import surface_path_certificate
        surface=grid_surface()
        self.assertTrue(surface_path_certificate(surface,[[1,1,0],[5,1,0]],.02)['valid'])
        self.assertFalse(surface_path_certificate(surface,[[1,1,0],[3,1,2],[5,1,0]],.02)['valid'])

    def test_crossing_an_empty_surface_gap_is_rejected(self):
        from dsg.geodesic_router import surface_path_certificate
        from types import SimpleNamespace
        surface=SimpleNamespace(vertices_mm=np.array([[0,0,0],[1,0,0],[0,1,0],[3,0,0],[4,0,0],[4,1,0]],float),triangles=np.array([[0,1,2],[3,4,5]]))
        self.assertFalse(surface_path_certificate(surface,[[.2,.2,0],[3.8,.2,0]],.02)['valid'])

if __name__=='__main__':unittest.main()
