"""TDD: analytic contact penetration and retained-section geometry, no Blender."""
import math
import unittest

import numpy as np

from dsg.frame_contact_core import (
    ContactPolicy, NoFeasibleContact,
    circular_section_after_planar_cut, select_contact_section,
    estimate_contact_route,
)


def policy(**changes):
    data = dict(min_contact_width_mm=0.8, min_retained_area_ratio=0.65,
                min_bending_inertia_ratio=0.30,
                min_penetration_mm=0.01, max_penetration_mm=0.7)
    data.update(changes)
    return ContactPolicy(**data)


class ContactSectionTests(unittest.TestCase):
    def test_zero_depth_leaves_full_circle_without_contact(self):
        s = circular_section_after_planar_cut(1.0, 0.0)
        self.assertAlmostEqual(s.retained_area_mm2, math.pi)
        self.assertAlmostEqual(s.inertia_about_surface_tangent_mm4, math.pi / 4)
        self.assertEqual(s.contact_width_mm, 0.0)

    def test_half_circle_has_half_area_and_its_exact_centroid(self):
        s = circular_section_after_planar_cut(1.0, 1.0)
        self.assertAlmostEqual(s.retained_area_mm2, math.pi / 2)
        self.assertAlmostEqual(s.contact_width_mm, 2)
        self.assertAlmostEqual(s.centroid_from_center_mm, 4 / (3 * math.pi))
        self.assertAlmostEqual(s.inertia_about_surface_tangent_mm4,
                               math.pi / 8 - 8 / (9 * math.pi))
        self.assertAlmostEqual(s.inertia_about_surface_lateral_mm4, math.pi / 8)

    def test_exact_area_matches_independent_numerical_integration(self):
        r, p = 1.25, 0.45
        s = circular_section_after_planar_cut(r, p)
        ys = np.linspace(-r + p, r, 10001)
        widths = 2 * np.sqrt(np.maximum(0, r*r - ys*ys))
        ref_area = float(np.trapz(widths, ys))
        self.assertAlmostEqual(s.retained_area_mm2, ref_area, delta=0.0004)

    def test_contact_depth_is_shallowest_feasible(self):
        s = select_contact_section(1.25, policy())
        self.assertGreaterEqual(s.contact_width_mm, 0.8 - 1e-8)
        self.assertGreaterEqual(s.retained_area_ratio, 0.65)
        self.assertGreaterEqual(s.min_retained_bending_inertia_ratio, 0.30)
        shorter = circular_section_after_planar_cut(1.25, s.penetration_mm - 0.001)
        self.assertLess(shorter.contact_width_mm, 0.8)

    def test_contact_constraints_never_sacrifice_structure(self):
        with self.assertRaisesRegex(NoFeasibleContact, "INERTIA"):
            select_contact_section(1, policy(min_contact_width_mm=2.0,
                                             min_bending_inertia_ratio=0.9,
                                             max_penetration_mm=1.0))

    def test_no_solution_if_depth_is_too_shallow(self):
        with self.assertRaisesRegex(NoFeasibleContact, "DEPTH_LIMIT"):
            select_contact_section(1, policy(min_contact_width_mm=1.8,
                                             max_penetration_mm=0.1))

    def test_reject_unsupported_buried_circle(self):
        with self.assertRaises(ValueError):
            circular_section_after_planar_cut(1, 1.5)

    def test_nonfinite_and_invalid_inputs_rejected(self):
        with self.assertRaises(ValueError):
            circular_section_after_planar_cut(float("nan"), 0.1)
        with self.assertRaises(ValueError):
            select_contact_section(1, policy(min_retained_area_ratio=1.1))

    def test_increasing_penetration_reduces_remaining_bending_section(self):
        a = circular_section_after_planar_cut(1, 0.2)
        b = circular_section_after_planar_cut(1, 0.6)
        self.assertGreater(a.min_retained_bending_inertia_ratio,
                           b.min_retained_bending_inertia_ratio)
        self.assertLess(a.contact_width_mm, b.contact_width_mm)


class ContactRouteTests(unittest.TestCase):
    def test_route_is_offset_outward_and_integrals_use_surface_arclength(self):
        estimate = estimate_contact_route(
            [[0, 0, 0], [2, 0, 0]], [[0, 0, 1], [0, 0, 1]],
            [1, 1], policy())
        sec = estimate.sections[0]
        self.assertAlmostEqual(estimate.centerline_mm[0, 2], sec.center_offset_mm)
        self.assertAlmostEqual(estimate.estimated_contact_area_mm2, 2 * sec.contact_width_mm)
        self.assertAlmostEqual(estimate.estimated_retained_volume_mm3, 2 * sec.retained_area_mm2)
        self.assertLess(estimate.estimated_retained_volume_mm3, estimate.nominal_volume_mm3)

    def test_normal_orientation_flips_fail_closed(self):
        with self.assertRaisesRegex(NoFeasibleContact, "NORMAL_FLIP"):
            estimate_contact_route(
                [[0, 0, 0], [1, 0, 0]], [[0, 0, 1], [0, 0, -1]],
                [1, 1], policy())

    def test_infeasible_radius_does_not_produce_partial_route(self):
        with self.assertRaises(NoFeasibleContact):
            estimate_contact_route(
                [[0, 0, 0], [1, 0, 0]], [[0, 0, 1], [0, 0, 1]],
                [0.2, 1], policy())


if __name__ == "__main__":
    unittest.main()
