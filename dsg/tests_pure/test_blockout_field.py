"""Retention fill is continuous: no pits, no holes, never inward."""
import importlib.util
import pathlib
import unittest

import numpy as np

_PATH = pathlib.Path(__file__).resolve().parents[1] / 'blender' / 'blockout_field.py'
_SPEC = importlib.util.spec_from_file_location('blockout_field', _PATH)
field = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(field)


def grid(n):
    index = np.arange(n * n).reshape(n, n)
    horizontal = np.column_stack([index[:, :-1].ravel(), index[:, 1:].ravel()])
    vertical = np.column_stack([index[:-1, :].ravel(), index[1:, :].ravel()])
    return np.vstack([horizontal, vertical])


class BlockoutFieldTests(unittest.TestCase):
    def setUp(self):
        self.n = 20
        self.edges = grid(self.n)
        hits = np.zeros((self.n, self.n))
        hits[5:15, 5:15] = 1.0          # blocked zone, 1 mm under the bulge
        hits[9, 9] = 0.0                # ray slipped between triangles
        hits[12, 12] = -1.0             # noisy normal inside the zone
        hits[:, :2] = -1.0              # faces away: must never move
        self.hits = hits.ravel()

    def shift(self, retention=0.1):
        return field.blockout_shift(self.hits, retention, self.edges, min_hit=0.02).reshape(self.n, self.n)

    def test_measured_vertices_keep_exact_fill(self):
        shift = self.shift()
        measured = self.hits.reshape(self.n, self.n) > 0
        self.assertTrue(np.allclose(shift[measured], 0.9))
        # tooth-wall-like vertices on the zone edge are never lifted
        self.assertTrue(np.all(shift[:, :2] == 0.0))

    def test_slipped_ray_is_not_a_pit(self):
        self.assertGreaterEqual(self.shift()[9, 9], 0.85)

    def test_noisy_normal_inside_zone_is_not_a_pit(self):
        self.assertAlmostEqual(self.shift()[12, 12], 0.9, places=6)

    def test_border_ramps_instead_of_step(self):
        row = self.shift()[10]
        outside = row[2:5]
        self.assertTrue(np.all(np.diff(outside) > 0))   # rises towards the zone
        self.assertLess(row[4], 0.9)

    def test_vertices_facing_away_never_move(self):
        self.assertTrue(np.all(self.shift()[:, :2] == 0.0))

    def test_live_change_matches_rebuild(self):
        before, after = self.shift(0.1), self.shift(0.2)
        self.assertTrue(np.allclose((after - before)[5:15, 5:15][self.hits.reshape(self.n, self.n)[5:15, 5:15] > 0], -0.1))
        self.assertTrue(np.all(after <= before + 1e-12))

    def test_too_far_hits_are_bounded(self):
        hits = np.zeros(self.n * self.n)
        hits[:] = 0.0
        hits[0] = 50.0  # surface far above: fill may not reach it
        hits[1] = 1.0
        shift = field.blockout_shift(hits, 0.1, self.edges, max_hit=10.0)
        self.assertLessEqual(shift[0], 49.9 + 1e-9)


if __name__ == '__main__':
    unittest.main()
