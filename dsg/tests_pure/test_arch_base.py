"""The closing lid keeps the U shape of the arch and has a rounded edge."""
import importlib.util
import pathlib
import unittest

import numpy as np

_PATH = pathlib.Path(__file__).resolve().parents[1] / 'blender' / 'arch_base.py'
_SPEC = importlib.util.spec_from_file_location('arch_base', _PATH)
arch_base = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(arch_base)


def horseshoe(samples=1600, outer=25.0, inner=15.0, noise=0.15, seed=3):
    """Closed U outline (outer arc, end cap, inner arc back, end cap)."""
    rng = np.random.default_rng(seed)
    t = np.linspace(0.0, np.pi, samples // 2)
    outer_arc = np.column_stack([outer * np.cos(t), outer * np.sin(t)])
    inner_arc = np.column_stack([inner * np.cos(t[::-1]), inner * np.sin(t[::-1])])
    outline = np.vstack([outer_arc, inner_arc])
    outline += rng.normal(0.0, noise, outline.shape)
    return outline


class ArchBaseTests(unittest.TestCase):
    def setUp(self):
        uv = horseshoe()
        height = -3.0 + 0.8 * np.sin(np.linspace(0, 12 * np.pi, len(uv)))
        self.collar = np.column_stack([uv, height])
        self.axis_u = np.array([1.0, 0.0, 0.0])
        self.axis_v = np.array([0.0, 1.0, 0.0])
        self.direction = np.array([0.0, 0.0, 1.0])

    def test_lid_follows_the_u(self):
        rings, info = arch_base.plan(self.collar, self.direction, self.axis_u, self.axis_v,
                                     base_plane=2.0, fillet=1.5, smoothing_length=1.0)
        self.assertIsNotNone(rings, info)
        lid = rings[-1][:, :2]
        self.assertTrue(arch_base.is_simple(lid))
        u_area = 0.5 * np.pi * (25.0 ** 2 - 15.0 ** 2)
        hull_area = 0.5 * np.pi * 25.0 ** 2
        area = abs(arch_base.signed_area(lid))
        # Lid is the U shrunk by the rounded edge, far from the full plate.
        perimeter = np.pi * 25.0 + np.pi * 15.0 + 2 * 10.0
        expected = u_area - 1.5 * perimeter
        self.assertAlmostEqual(area, expected, delta=0.08 * expected)
        self.assertLess(area, 0.6 * hull_area)
        self.assertTrue(np.allclose(rings[-1][:, 2], 2.0))

    def test_rounded_edge_is_quarter_circle(self):
        rings, _info = arch_base.plan(self.collar, self.direction, self.axis_u, self.axis_v,
                                      base_plane=2.0, fillet=1.5, smoothing_length=1.0)
        fillet = rings[-arch_base.FILLET_RINGS - 1:]
        knee, lid = fillet[0], fillet[-1]
        inset = np.linalg.norm(lid[:, :2] - knee[:, :2], axis=1)
        self.assertTrue(np.allclose(inset, 1.5, atol=1e-6))
        heights = [float(r[0, 2]) for r in fillet]
        self.assertTrue(all(b > a for a, b in zip(heights, heights[1:])))

    def test_rejects_base_too_close(self):
        rings, reason = arch_base.plan(self.collar, self.direction, self.axis_u, self.axis_v,
                                       base_plane=-1.0, fillet=1.5, smoothing_length=1.0)
        self.assertIsNone(rings)
        self.assertEqual(reason, 'base_plane_too_close')

    def test_simple_check_detects_crossing(self):
        bow = np.array([[0, 0], [1, 1], [1, 0], [0, 1]], dtype=float)
        self.assertFalse(arch_base.is_simple(bow))
        square = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=float)
        self.assertTrue(arch_base.is_simple(square))


if __name__ == '__main__':
    unittest.main()
