"""Atomic perimeter FEM loop, including rollback and four-edge connectivity."""
import unittest
import numpy as np
from dsg import frame_fem_core as fem
from dsg.frame_perimeter_fem import append_perimeter_loop, InvalidPerimeterLoop


class PerimeterTests(unittest.TestCase):
    def setUp(self):
        self.nodes=[
            fem.Node([0,0,0],[True]*6,"P1"),
            fem.Node([2,0,0],[True]*6,"P2"),
            fem.Node([2,2,0],[True]*6,"P3"),
            fem.Node([0,2,0],[True]*6,"P4"),
        ]
        self.elements=[]
        self.template=fem.BeamElement(0,1,0.9,tag="FRAME",locked_radius=True,
                                       prunable=False,render=True)
        self.paths=[
            [[0,0,0],[1,0,0],[2,0,0]],
            [[2,0,0],[2,1,0],[2,2,0]],
            [[2,2,0],[1,2,0],[0,2,0]],
            [[0,2,0],[0,1,0],[0,0,0]],
        ]

    def assemble(self):
        return append_perimeter_loop(self.nodes,self.elements,(0,1,2,3),
                                     self.paths,radius_mm=0.9,template=self.template)

    def test_complete_square_loop_contributes_nominal_beam_volume(self):
        result=self.assemble()
        self.assertTrue(result.is_closed)
        self.assertEqual(len(result.edges),4)
        self.assertEqual(len(result.beam_indices),8)
        self.assertAlmostEqual(result.length_mm,8)
        self.assertEqual(len(self.nodes),8)
        self.assertEqual(len(self.elements),8)
        self.assertTrue(all(x.locked_radius and not x.prunable for x in self.elements))
        self.assertTrue(all(x.tag.startswith("FRAME_PERIMETER_E") for x in self.elements))
        self.assertFalse(result.support_contact_calibrated)

    def test_bad_last_edge_rolls_back_entire_network(self):
        self.paths[-1]=[[0,2,0],[0,2,0],[0,0,0]]
        with self.assertRaises(InvalidPerimeterLoop):
            self.assemble()
        self.assertEqual(len(self.nodes),4)
        self.assertEqual(self.elements,[])

    def test_wrong_support_order_fails_before_modifying(self):
        with self.assertRaises(InvalidPerimeterLoop):
            append_perimeter_loop(self.nodes,self.elements,(0,1,2,2),
                                  self.paths,radius_mm=1,template=self.template)
        self.assertEqual(len(self.nodes),4)

    def test_last_perimeter_member_connects_p4_to_p1(self):
        loop=self.assemble()
        last=loop.edges[-1]
        self.assertEqual(last["support_from"],3)
        self.assertEqual(last["support_to"],0)

    def test_deterministic(self):
        a=self.assemble().length_mm
        self.setUp()
        b=self.assemble().length_mm
        self.assertEqual(a,b)




class PerimeterSupportCountTests(unittest.TestCase):
    def test_five_supports_close_the_loop(self):
        pts=[[0,0,0],[2,0,0],[3,1.5,0],[2,3,0],[0,3,0]]
        nodes=[fem.Node(p,[True]*6,f"P{i+1}") for i,p in enumerate(pts)]
        elements=[]
        template=fem.BeamElement(0,1,0.9,tag="FRAME",locked_radius=True,prunable=False,render=True)
        paths=[[pts[i],list((np.array(pts[i])+np.array(pts[(i+1)%5]))/2),pts[(i+1)%5]] for i in range(5)]
        loop=append_perimeter_loop(nodes,elements,(0,1,2,3,4),paths,radius_mm=0.9,template=template)
        self.assertEqual(len(loop.edges),5)
        self.assertEqual(loop.edges[-1]["support_from"],4)
        self.assertEqual(loop.edges[-1]["support_to"],0)

    def test_path_count_must_match_supports(self):
        pts=[[0,0,0],[2,0,0],[2,2,0]]
        nodes=[fem.Node(p,[True]*6,"P") for p in pts]
        template=fem.BeamElement(0,1,0.9,tag="FRAME",locked_radius=True,prunable=False,render=True)
        with self.assertRaises(InvalidPerimeterLoop):
            append_perimeter_loop(nodes,[],(0,1,2),[[pts[0],pts[1]]],radius_mm=0.9,template=template)


if __name__ == '__main__':
    unittest.main()
