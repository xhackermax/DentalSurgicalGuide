"""Actual closed-mesh planar slicing: solid bars, Boolean cavities, failures."""
import unittest
import math
import numpy as np

from dsg.frame_boolean_section_core import measure_boolean_section, InvalidBooleanSection


def cube(x0,x1,y0,y1,z0,z1):
    v=np.array([[x0,y0,z0],[x1,y0,z0],[x1,y1,z0],[x0,y1,z0],
                [x0,y0,z1],[x1,y0,z1],[x1,y1,z1],[x0,y1,z1]],float)
    quads=[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
    faces=[]
    for a,b,c,d in quads:faces.extend(((a,b,c),(a,c,d)))
    return v,np.array(faces,dtype=int)


def box_section(v,t,probe=(0,0,0),**kwargs):
    return measure_boolean_section(v,t,[0,0,0],[1,0,0],
                                   probe_point_mm=probe,**kwargs)


class BooleanSectionTests(unittest.TestCase):
    def test_full_square_prism_has_known_area_and_bending(self):
        v,t=cube(-2,2,-0.5,0.5,-0.5,0.5)
        a=box_section(v,t)
        self.assertAlmostEqual(a.area_mm2,1.0,places=8)
        self.assertAlmostEqual(a.principal_inertia_min_mm4,1/12,places=7)
        self.assertAlmostEqual(a.principal_inertia_max_mm4,1/12,places=7)
        self.assertEqual(a.hole_count,0)
        self.assertEqual(a.boundary_count,1)
        self.assertEqual(a.global_component_count,1)

    def test_asymmetric_rectangle_centroid_and_principal_inertias(self):
        v,t=cube(-2,2,-1,2,-0.5,0.5)
        a=box_section(v,t,probe=(0,0,0))
        self.assertAlmostEqual(a.area_mm2,3)
        self.assertAlmostEqual(a.principal_inertia_min_mm4,3/12,places=7)
        self.assertAlmostEqual(a.principal_inertia_max_mm4,9/4,places=7)

    def test_boolean_hole_subtracts_area_and_stiffness(self):
        outer,ot=cube(-2,2,-1,1,-1,1)
        inner,it=cube(-2,2,-0.5,0.5,-0.5,0.5)
        v=np.vstack((outer,inner))
        t=np.vstack((ot,it+8))
        a=box_section(v,t,probe=(0,0.75,0.75))
        self.assertAlmostEqual(a.area_mm2,3)
        self.assertAlmostEqual(a.principal_inertia_min_mm4,1.25,places=7)
        self.assertEqual(a.hole_count,1)
        self.assertEqual(a.boundary_count,2)
        with self.assertRaisesRegex(InvalidBooleanSection,"VOID"):
            box_section(v,t,probe=(0,0,0))

    def test_two_disconnected_bars_selects_probed_component_only(self):
        a,ta=cube(-2,2,-0.5,0.5,-0.5,0.5)
        b,tb=cube(-2,2,3,5,-0.5,0.5)
        sect=box_section(np.vstack((a,b)),np.vstack((ta,tb+8)),probe=(0,4,0))
        self.assertAlmostEqual(sect.area_mm2,2)
        self.assertEqual(sect.global_component_count,2)

    def test_open_mesh_fails_closed(self):
        v,t=cube(-2,2,-1,1,-1,1)
        with self.assertRaisesRegex(InvalidBooleanSection,"NON_MANIFOLD"):
            box_section(v,t[:-1])

    def test_coplanar_face_fails_closed(self):
        v,t=cube(0,2,-1,1,-1,1)
        with self.assertRaisesRegex(InvalidBooleanSection,"COPLANAR"):
            box_section(v,t)

    def test_probe_outside_solid_fails(self):
        v,t=cube(-2,2,-1,1,-1,1)
        with self.assertRaisesRegex(InvalidBooleanSection,"OUTSIDE"):
            box_section(v,t,probe=(0,5,5))

    def test_section_no_intersection_fails(self):
        v,t=cube(4,6,-1,1,-1,1)
        with self.assertRaisesRegex(InvalidBooleanSection,"NO_INTERSECTION"):
            box_section(v,t)

    def test_untouched_bounding_box_not_clinical_approval(self):
        v,t=cube(-2,2,-1,1,-1,1)
        self.assertEqual(box_section(v,t).backend,"ACTUAL_TRIANGULATED_BOOLEAN_MESH")


if __name__=="__main__":
    unittest.main()
