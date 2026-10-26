import unittest
import numpy as np
from dsg.ios_surface import SurfaceAnchor,GenerationConfig
from dsg.geodesic_router import CandidatePath
from dsg.frame_generator import FramePerimeter,SleevePort,select_frame_anchor_pairs,build_frame_graph,validate_connectivity


def anchor(label,component=0):return SurfaceAnchor(label,'surface',0,(1.,0.,0.),component,'FRAME')


class FrameTests(unittest.TestCase):
    def fixture(self):
        anchors=tuple(anchor('P'+str(i+1)) for i in range(4))
        perimeter=FramePerimeter('frame',np.array([[0,0,0],[20,0,0],[20,20,0],[0,20,0]],float),anchors,'original-digest')
        ports=(SleevePort('S_LEFT','S1',anchor('S_LEFT'),(8.,0.,0.)),SleevePort('S_RIGHT','S1',anchor('S_RIGHT'),(12.,0.,0.)))
        return perimeter,ports,anchors

    def test_square_selects_both_far_corners_even_at_supports(self):
        perimeter,ports,anchors=self.fixture()
        pairs=select_frame_anchor_pairs(perimeter,ports,anchors,GenerationConfig())
        starts={p.start.id for p in pairs[:4]}
        self.assertEqual(starts,{'P3','P4'})

    def test_perimeter_digest_unchanged(self):
        perimeter,ports,anchors=self.fixture();before=perimeter.points_mm.copy()
        graph=build_frame_graph(perimeter,(),GenerationConfig())
        np.testing.assert_array_equal(before,graph.perimeter.points_mm)
        self.assertEqual(graph.perimeter.geometry_hash,'original-digest')

    def test_five_supports_preserve_ids(self):
        perimeter,ports,anchors=self.fixture();fifth=anchor('P5')
        perimeter=FramePerimeter('frame',np.vstack((perimeter.points_mm,[-1,10,0])),anchors+(fifth,),'five')
        pairs=select_frame_anchor_pairs(perimeter,ports,anchors+(fifth,),GenerationConfig())
        self.assertIn('P5',{p.start.id for p in pairs})
        from dsg.frame_generator import perimeter_sleeve_topology
        topology=perimeter_sleeve_topology([a.id for a in anchors+(fifth,)],'S1')
        self.assertEqual([b['from'] for b in topology['branches']],['P1','P2','P3','P4','P5'])

    def test_projected_crossing_is_not_a_node(self):
        perimeter,_,_=self.fixture()
        paths=(CandidatePath('a','P1','S1',np.array([[0,0,0],[5,5,0],[10,10,0]]),(),14.,14.,'test',0),CandidatePath('b','P2','S2',np.array([[20,0,0],[5,5,3],[0,10,3]]),(),20.,20.,'test',0))
        graph=build_frame_graph(perimeter,paths,GenerationConfig())
        self.assertEqual(len(graph.members),2)
        self.assertEqual(len(graph.nodes),6)  # 4 perimeter nodes and 2 sleeve ports
        self.assertTrue(validate_connectivity(graph).valid)

    def test_orphan_branch_rejected(self):
        perimeter,_,_=self.fixture();path=CandidatePath('x','unknown','S1',np.array([[5,5,0],[8,8,0]]),(),4.,4.,'test',0)
        graph=build_frame_graph(perimeter,(path,),GenerationConfig())
        self.assertFalse(validate_connectivity(graph).valid)

    def test_sweep_never_creates_miter_spikes_at_dense_corners(self):
        from dsg.frame_generator import sweep_path_mesh
        points=np.array([[0,0,0],[1,0,0],[1,.01,0],[2,.01,0],[2,1,0]],float)
        vertices,faces=sweep_path_mesh(points,.5,12)
        self.assertEqual(len(vertices),len(points)*12+2)
        for i,point in enumerate(points):
            np.testing.assert_allclose(np.linalg.norm(vertices[i*12:(i+1)*12]-point,axis=1),.5,atol=1e-8)
        self.assertTrue(np.isfinite(vertices).all());self.assertEqual(faces.shape[1],3)

if __name__=='__main__':unittest.main()
