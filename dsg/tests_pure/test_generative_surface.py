import unittest
import numpy as np
from dsg.ios_surface import prepare_surface, SurfaceAnchor, validate_anchor, transform_points_mm


def surface_fixture():
    xyz=np.array([[0,0,0],[2,0,0],[0,2,0],[8,0,0],[10,0,0],[8,2,0]],float)
    triangles=np.array([[0,1,2],[3,4,5]])
    adjacency=[[] for _ in xyz]
    for tri in triangles:
        for a,b in ((tri[0],tri[1]),(tri[1],tri[2]),(tri[2],tri[0])):
            adjacency[a].append(b);adjacency[b].append(a)
    dst=[];weights=[];offset=[0]
    for i,row in enumerate(adjacency):
        for j in sorted(set(row)):dst.append(j);weights.append(np.linalg.norm(xyz[i]-xyz[j]))
        offset.append(len(dst))
    return xyz,triangles,offset,dst,weights


def make_surface(**kwargs):
    return prepare_surface(*surface_fixture(),source_id='surface',source_role='PASSIVE',world_matrix=kwargs.get('matrix',np.eye(4)),unit_scale_mm=1.)


class SurfaceTests(unittest.TestCase):
    def test_snapshot_is_immutable(self):
        surface=make_surface()
        with self.assertRaises(ValueError):surface.vertices_mm[0,0]=100

    def test_hash_changes_with_matrix_or_geometry(self):
        first=make_surface();matrix=np.eye(4);matrix[0,3]=1
        self.assertNotEqual(first.fingerprint,make_surface(matrix=matrix).fingerprint)
        self.assertEqual(first.fingerprint,make_surface().fingerprint)

    def test_anchor_rejects_wrong_component(self):
        surface=make_surface();anchor=SurfaceAnchor('P1',surface.fingerprint,0,(1.,0.,0.),1,'SUPPORT')
        with self.assertRaisesRegex(ValueError,'COMPONENT'):validate_anchor(surface,anchor)
        valid=SurfaceAnchor('P1',surface.fingerprint,0,(.5,.25,.25),0,'SUPPORT')
        np.testing.assert_allclose(validate_anchor(surface,valid),[.5,.5,0])

    def test_nonuniform_transform_uses_world_mm(self):
        matrix=np.diag([2.,3.,4.,1.]);matrix[0,3]=5.
        np.testing.assert_allclose(transform_points_mm([[1,2,3]],matrix,1.),[[7,6,12]])

    def test_degenerate_triangle_rejected(self):
        xyz,tris,offset,dst,weights=surface_fixture();tris[0]=[0,0,2]
        with self.assertRaisesRegex(ValueError,'DEGENERATE'):
            prepare_surface(xyz,tris,offset,dst,weights,source_id='x',source_role='PASSIVE',world_matrix=np.eye(4),unit_scale_mm=1.)

    def test_inconsistent_or_non_surface_csr_edge_is_rejected(self):
        xyz,tris,offset,dst,weights=surface_fixture();dst[0]=3;weights[0]=8.
        with self.assertRaises(ValueError):
            prepare_surface(xyz,tris,offset,dst,weights,source_id='x',source_role='PASSIVE',world_matrix=np.eye(4),unit_scale_mm=1.)

    def test_analysis_copy_drops_zero_area_faces_with_explicit_remap(self):
        from dsg.ios_surface import sanitize_surface_arrays
        xyz,tris,offset,dst,weights=surface_fixture();bad=np.vstack((tris,[[0,0,1]]))
        clean,offset2,dst2,length2,remap=sanitize_surface_arrays(xyz,bad,offset,dst,weights)
        self.assertEqual(remap.tolist(),[0,1,-1]);self.assertEqual(len(clean),2)
        self.assertEqual(len(bad),3)

if __name__=='__main__':unittest.main()
