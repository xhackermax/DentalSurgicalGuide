"""TDD for multi-station post-Boolean section profiles."""
import unittest
import math
import numpy as np
from dsg.frame_boolean_path_core import profile_boolean_path
from dsg.frame_boolean_section_core import InvalidBooleanSection


def cuboid(x0,x1,y0,y1,z0,z1):
    v=np.array([[x0,y0,z0],[x1,y0,z0],[x1,y1,z0],[x0,y1,z0],
                [x0,y0,z1],[x1,y0,z1],[x1,y1,z1],[x0,y1,z1]],float)
    quad=[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
    faces=[]
    for a,b,c,d in quad:faces.extend(((a,b,c),(a,c,d)))
    return v,np.asarray(faces,dtype=int)


class ProfileTests(unittest.TestCase):
    def test_known_rectangular_prism_constant_section(self):
        v,t=cuboid(-5,5,-1,1,-0.5,0.5)
        r=profile_boolean_path(v,t,[[-4,0,0],[0,0,0],[4,0,0]],
                               sample_count=7,nominal_radii_mm=[1,1,1])
        self.assertEqual(r.probe_count,7)
        self.assertEqual(len(r.stations),7)
        self.assertAlmostEqual(r.area_min_mm2,2)
        self.assertAlmostEqual(r.weak_inertia_min_mm4,2/12)
        self.assertAlmostEqual(r.stations[0].nominal_area_ratio,2/math.pi)
        self.assertAlmostEqual(r.arclength_mm,8)
        self.assertFalse(r.mechanical_fem_validated)
        self.assertFalse(r.retention_validated)

    def test_one_bad_sample_rejects_whole_profile(self):
        v,t=cuboid(-5,5,-1,1,-1,1)
        with self.assertRaisesRegex(InvalidBooleanSection,"BOOLEAN_PATH_SECTION_"):
            profile_boolean_path(v,t,[[-4,0,0],[0,0,0],[4,3,0]],sample_count=9)

    def test_open_mesh_fails_closed(self):
        v,t=cuboid(-5,5,-1,1,-1,1)
        with self.assertRaisesRegex(InvalidBooleanSection,"NON_MANIFOLD"):
            profile_boolean_path(v,t,[[-4,0,0],[4,0,0]],sample_count=3,triangles=t[:-1])

    def test_reference_radius_length_must_match_path(self):
        v,t=cuboid(-5,5,-1,1,-1,1)
        with self.assertRaisesRegex(ValueError,"REFERENCE_RADII"):
            profile_boolean_path(v,t,[[-4,0,0],[4,0,0]],nominal_radii_mm=[1,1,1])

    def test_sharp_reverse_turn_is_rejected(self):
        v,t=cuboid(-5,5,-1,1,-1,1)
        with self.assertRaisesRegex(InvalidBooleanSection,"SHARP_BEND"):
            profile_boolean_path(v,t,[[0,0,0],[2,0,0],[0.1,0,0]])

    def test_deterministic_station_count_and_values(self):
        v,t=cuboid(-5,5,-1,1,-1,1)
        kwargs=dict(sample_count=5)
        a=profile_boolean_path(v,t,[[-4,0,0],[4,0,0]],**kwargs)
        b=profile_boolean_path(v,t,[[-4,0,0],[4,0,0]],**kwargs)
        self.assertEqual(a,b)

    def test_hole_containing_path_point_is_rejected(self):
        ov,ot=cuboid(-5,5,-2,2,-2,2)
        iv,it=cuboid(-5,5,-0.5,0.5,-0.5,0.5)
        v=np.vstack((ov,iv)); t=np.vstack((ot,it+8))
        with self.assertRaisesRegex(InvalidBooleanSection,"VOID"):
            profile_boolean_path(v,t,[[-4,0,0],[4,0,0]],sample_count=3)

    def test_true_void_section_reports_subtracted_area(self):
        ov,ot=cuboid(-5,5,-2,2,-2,2)
        iv,it=cuboid(-5,5,-0.5,0.5,-0.5,0.5)
        v=np.vstack((ov,iv)); t=np.vstack((ot,it+8))
        profile=profile_boolean_path(v,t,[[-4,1,0],[4,1,0]],sample_count=3)
        self.assertAlmostEqual(profile.area_min_mm2,15)
        self.assertEqual(profile.stations[0].hole_count,1)


if __name__=="__main__":
    unittest.main()
