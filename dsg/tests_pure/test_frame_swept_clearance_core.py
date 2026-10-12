"""Conservative swept-envelope tests: lumen, caps, variable radius and proof bound."""
import math
import unittest
from dsg.frame_swept_clearance_core import (
    SphereKeepOut, CylinderKeepOut, InvalidClearanceGeometry,
    check_swept_tube_clearance,
)


class SweptClearanceTests(unittest.TestCase):
    def setUp(self):
        self.cyl=CylinderKeepOut("S1_LUMEN",(0,0,0),(0,0,1),1,3)

    def test_tube_passes_beside_cylinder_with_proven_clearance(self):
        r=check_swept_tube_clearance([[3,0,-1],[3,0,1]],[0.5,0.5],[self.cyl])
        self.assertTrue(r.clear)
        self.assertEqual(r.status,"CLEAR_FOR_DECLARED_ZONES_ONLY")
        self.assertGreater(r.conservative_min_clearance_mm,0)
        self.assertFalse(r.whole_anatomy_validated)

    def test_centerline_outside_but_tube_overlaps_lumen(self):
        r=check_swept_tube_clearance([[1.3,0,-1],[1.3,0,1]],[0.5,0.5],[self.cyl])
        self.assertFalse(r.clear)
        self.assertEqual(r.status,"INTERSECTION")

    def test_centerline_directly_crosses_lumen(self):
        r=check_swept_tube_clearance([[-2,0,0],[2,0,0]],[0.2,0.2],[self.cyl])
        self.assertFalse(r.clear)
        self.assertEqual(r.status,"INTERSECTION")

    def test_height_finite_cylinder_end_cap(self):
        r=check_swept_tube_clearance([[0,0,5],[0,0,6]],[0.5,0.5],[self.cyl])
        self.assertTrue(r.clear)
        self.assertGreater(r.conservative_min_clearance_mm,1)

    def test_radius_interpolation_detects_terminal_collision(self):
        r=check_swept_tube_clearance([[2,0,-1],[2,0,1]],[0.3,1.2],[self.cyl])
        self.assertFalse(r.clear)
        self.assertEqual(r.status,"INTERSECTION")

    def test_sphere_keepout(self):
        sphere=SphereKeepOut("TOOTH_PROTECTED",(0,0,0),1.0)
        r=check_swept_tube_clearance([[-2,0,0],[2,0,0]],[0.5,0.5],[sphere])
        self.assertFalse(r.clear)

    def test_uncertainty_fail_closed_if_sampling_too_coarse(self):
        sphere=SphereKeepOut("TINY",(0,0,0),0.1)
        r=check_swept_tube_clearance([[0,0.65,-1],[0,0.65,1]],
                    [0.4,0.4],[sphere],sample_spacing_mm=2.0)
        self.assertFalse(r.clear)
        self.assertEqual(r.status,"UNVERIFIED_NEAR_BOUNDARY")
        self.assertGreater(r.minimum_sampled_clearance_mm,0)

    def test_unsafe_axis_and_sample_limits(self):
        with self.assertRaisesRegex(InvalidClearanceGeometry,"ZERO_AXIS"):
            check_swept_tube_clearance([[3,0,0],[4,0,0]],[0.1,0.1],
                [CylinderKeepOut("BAD",(0,0,0),(0,0,0),1,3)])
        with self.assertRaisesRegex(InvalidClearanceGeometry,"TOO_MANY_SAMPLES"):
            check_swept_tube_clearance([[3,0,0],[4,0,0]],[0.1,0.1],
                [self.cyl],sample_spacing_mm=0.01,max_samples=50)

    def test_deterministic_for_same_inputs(self):
        args=([[2,0,0],[2,0,3]],[0.5,0.5],[self.cyl])
        self.assertEqual(check_swept_tube_clearance(*args),
                         check_swept_tube_clearance(*args))

    def test_no_zone_never_implies_whole_anatomy_validated(self):
        r=check_swept_tube_clearance([[0,0,0],[2,0,0]],[0.5,0.5],[])
        self.assertTrue(r.clear)
        self.assertEqual(r.declared_zone_count,0)
        self.assertFalse(r.whole_anatomy_validated)


if __name__=="__main__":
    unittest.main()
