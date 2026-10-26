"""The tooth cutter always reaches the IOS surface (socket opens)."""
import importlib.util
import pathlib
import unittest

import numpy as np

_PATH = pathlib.Path(__file__).resolve().parents[1] / 'blender' / 'socket_reach.py'
_SPEC = importlib.util.spec_from_file_location('socket_reach', _PATH)
reach = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(reach)


def cylinder(radius, z0, z1, n=24, rings=12):
    angle = np.linspace(0, 2 * np.pi, n, endpoint=False)
    z = np.linspace(z0, z1, rings)
    return np.array([(radius * np.cos(a), radius * np.sin(a), h) for h in z for a in angle])


class SocketReachTests(unittest.TestCase):
    def setUp(self):
        self.tooth = cylinder(2.5, -14.0, 0.0)            # crown truncated at z=0
        xs, ys = np.meshgrid(np.linspace(-8, 8, 33), np.linspace(-8, 8, 33))
        self.surface = np.column_stack([xs.ravel(), ys.ravel(), np.full(xs.size, 2.0)])
        self.up = np.array([0.0, 0.0, 1.0])

    def test_short_tooth_is_extended_past_the_surface(self):
        shift, need = reach.plan_extension(self.tooth, self.surface, self.up)
        self.assertAlmostEqual(need, 3.0)                  # 2 mm gap + 1 mm clearance
        self.assertGreater((self.tooth[:, 2] + shift).max(), 2.0)

    def test_root_and_width_do_not_change(self):
        shift, _ = reach.plan_extension(self.tooth, self.surface, self.up)
        self.assertTrue(np.all(shift[self.tooth[:, 2] < -2.0] == 0.0))

    def test_tooth_that_already_pierces_is_untouched(self):
        surface = self.surface.copy()
        surface[:, 2] = -1.0
        shift, need = reach.plan_extension(self.tooth, surface, self.up)
        self.assertEqual(need, 0.0)
        self.assertTrue(np.all(shift == 0.0))

    def test_neighbours_outside_the_column_are_ignored(self):
        surface = np.vstack([self.surface, [[6.0, 0.0, 9.0]]])  # neighbour cusp, outside radius
        _shift, need = reach.plan_extension(self.tooth, surface, self.up)
        self.assertAlmostEqual(need, 3.0)


if __name__ == '__main__':
    unittest.main()
