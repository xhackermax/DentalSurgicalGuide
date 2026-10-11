"""Sleeve junction tolerance: no false preBoolean rejection and no phantom approval."""
import unittest
import numpy as np
from dsg.frame_sleeve_junction_core import preflight_sleeve_junction, InvalidSleeveJunction


def sleeve(sid, center=(0.,0.,0.)):
    return {"id":sid,"center":center,"axis":(0,0,1),
            "inner_radius_mm":2.1,"outer_radius_mm":3.,
            "height_mm":7.,"lumen_keep_out":True}


class JunctionTests(unittest.TestCase):
    def test_legitimate_outer_weld_is_provisional_not_cleared_for_clinical_use(self):
        # Ø2.5 mm reinforcement touches the sleeve wall, preBoolean may overlap lumen.
        path=[[7,0,0],[5,0,0],[3.03,0,0]]
        r=preflight_sleeve_junction(path,[1.25]*3,[sleeve("S1")],
                                    target_sleeve_id="S1",maximum_deferred_tip_mm=2.1)
        self.assertTrue(r.candidate_admissible)
        self.assertEqual(r.status,"OUTER_WALL_WELD_DEFERRED_TO_POST_BOOLEAN")
        self.assertTrue(r.post_boolean_lumen_validation_required)
        self.assertFalse(r.final_lumen_clear)
        self.assertFalse(r.whole_anatomy_validated)

    def test_interior_lumen_crossing_before_weld_is_rejected(self):
        # Traverses center and approaches the opposing outer wall.
        path=[[-7,0,0],[-5,0,0],[0,0,0],[3,0,0]]
        r=preflight_sleeve_junction(path,[0.8]*4,[sleeve("S1")],
                                    target_sleeve_id="S1",maximum_deferred_tip_mm=1.)
        self.assertFalse(r.candidate_admissible)
        self.assertIn("UPSTREAM_TARGET",r.status)

    def test_other_sleeves_are_never_exempted(self):
        path=[[7,0,0],[5,0,0],[3,0,0]]
        s=[sleeve("S1"),sleeve("S2",center=(5,0,0))]
        r=preflight_sleeve_junction(path,[1.25]*3,s,
                                    target_sleeve_id="S1",maximum_deferred_tip_mm=2.1)
        self.assertFalse(r.candidate_admissible)
        self.assertIn("NON_TARGET_LUMEN",r.status)

    def test_unknown_target_or_invalid_endpoint_fails_closed(self):
        path=[[7,0,0],[5,0,0],[3,0,0]]
        with self.assertRaisesRegex(InvalidSleeveJunction,"UNMAPPED"):
            preflight_sleeve_junction(path,[1]*3,[sleeve("S1")],target_sleeve_id="S2")
        with self.assertRaisesRegex(InvalidSleeveJunction,"OUTER_WALL"):
            preflight_sleeve_junction([[7,0,0],[5,0,0],[1,0,0]],[1]*3,[sleeve("S1")],
                                      target_sleeve_id="S1")

    def test_too_large_exemption_is_never_allowed(self):
        with self.assertRaisesRegex(InvalidSleeveJunction,"UNBOUNDED"):
            preflight_sleeve_junction([[7,0,0],[3,0,0]],[1,1],[sleeve("S1")],
                                      target_sleeve_id="S1",maximum_deferred_tip_mm=2.6)

    def test_too_short_route_fails(self):
        with self.assertRaisesRegex(InvalidSleeveJunction,"UNBOUNDED"):
            preflight_sleeve_junction([[3.5,0,0],[3,0,0]],[1,1],[sleeve("S1")],
                                      target_sleeve_id="S1",maximum_deferred_tip_mm=2.0)

    def test_nonfinite_geometry_fails_closed(self):
        with self.assertRaises(InvalidSleeveJunction):
            preflight_sleeve_junction([[float("nan"),0,0],[3,0,0]],[1,1],
                                      [sleeve("S1")],target_sleeve_id="S1")

    def test_determinism(self):
        kwargs=dict(target_sleeve_id="S1",maximum_deferred_tip_mm=2.1)
        a=preflight_sleeve_junction([[7,0,0],[3,0,0]],[1,1],[sleeve("S1")],**kwargs)
        b=preflight_sleeve_junction([[7,0,0],[3,0,0]],[1,1],[sleeve("S1")],**kwargs)
        self.assertEqual(a,b)


if __name__=="__main__":
    unittest.main()
