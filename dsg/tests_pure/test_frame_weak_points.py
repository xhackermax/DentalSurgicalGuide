import unittest
import numpy as np
from dsg import frame_weak_points as weak


def u_frame(step=1.0):
    """Open-ended U closed by a back bar: two long straight sides, rounded front."""
    pts = []
    for y in np.arange(0, 30, step):              # left side, straight
        pts.append((-15.0, 30.0 - y, 0.0))
    for a in np.linspace(np.pi, 2 * np.pi, 31)[:-1]:   # front arch
        pts.append((15 * np.cos(a), 15 * np.sin(a), 0.0))
    for y in np.arange(0, 30, step):              # right side, straight
        pts.append((15.0, y, 0.0))
    for x in np.arange(15, -15, -step):           # back bar closes the loop: two sharp corners
        pts.append((x, 30.0, 0.0))
    return np.asarray(pts, float)


class WeakPoints(unittest.TestCase):
    def test_square_corners_are_found(self):
        sq = [(x, 0, 0) for x in range(0, 20)] + [(20, y, 0) for y in range(0, 20)] + \
             [(20 - x, 20, 0) for x in range(0, 20)] + [(0, 20 - y, 0) for y in range(0, 20)]
        kinds = weak.candidates(np.asarray(sq, float), closed=True)
        corners = [i for i, k, _s in kinds if k == 'CORNER']
        self.assertEqual(len(corners), 4)
        straights = [i for i, k, _s in kinds if k == 'STRAIGHT']
        self.assertEqual(len(straights), 4)

    def test_far_corners_and_long_runs_win_and_sleeve_is_excluded(self):
        pts = u_frame()
        sleeve = ((0.0, -15.0, 0.0), 3.85)          # sleeve at the front of the arch
        chosen = weak.select(pts, [sleeve], count=3)
        self.assertEqual(len(chosen), 3)
        for c in chosen:
            self.assertGreater(c['distance_mm'], 3.85 + weak.SLEEVE_EXCLUSION_MM)
        # The best points are the far back corners / straight sides, not the front.
        self.assertTrue(all(c['point'][1] > 0 for c in chosen))
        spacing = min(np.linalg.norm(a['point'] - b['point']) for i, a in enumerate(chosen) for b in chosen[i + 1:])
        self.assertGreaterEqual(spacing, weak.MIN_SPACING_MM)

    def test_supports_are_not_weak(self):
        pts = u_frame()
        sleeve = ((0.0, -15.0, 0.0), 3.85)
        free = weak.select(pts, [sleeve], count=1)[0]
        clamped = weak.select(pts, [sleeve], supports=[free['point']], count=1)[0]
        self.assertGreater(np.linalg.norm(clamped['point'] - free['point']), weak.SUPPORT_EXCLUSION_MM)



class MechanicalWeakPoints(unittest.TestCase):
    def test_largest_deflection_is_chosen_first(self):
        pts = u_frame()
        sleeve = ((0.0, -15.0, 0.0), 3.85)
        disp = np.zeros(len(pts))
        target = 15                               # a point on the straight left side
        disp[target] = 1.0
        disp[target - 3:target + 4] = np.maximum(disp[target - 3:target + 4], 0.6)
        chosen = weak.select(pts, [sleeve], count=2, displacement=disp, bending=np.zeros(len(pts)))
        self.assertEqual(chosen[0]['index'], target)
        self.assertEqual(chosen[0]['kind'] if chosen[0]['kind'] != 'STRAIGHT' else 'MECHANICAL', 'MECHANICAL')


class Stiffening(unittest.TestCase):
    def test_greedy_takes_best_gain_then_completes(self):
        pts = np.array([[x, 0, 0] for x in range(0, 60, 2)], float)
        # displacement falls most with a link at x=40, then x=10 (spacing ok)
        def disp(chosen):
            d = 1.0
            for i in chosen:
                x = pts[i][0]
                d *= 0.5 if x == 40 else (0.7 if x == 10 else 0.98)
            return d
        picks = weak.greedy_by_stiffening(pts, list(range(len(pts))), disp, count=2)
        self.assertEqual([pts[i][0] for i, _d, _g in picks], [40, 10])
        self.assertAlmostEqual(picks[1][1], 0.35)


if __name__ == '__main__':
    unittest.main()
