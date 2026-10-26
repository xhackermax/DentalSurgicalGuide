"""Frame embed prediction: smooth line, ≥2 mm after the Boolean, 30–45 % embed."""
import unittest

import numpy as np

from dsg.blender import frame_embed as fe
from dsg.blender import organic_curve as oc


def _height(x, y):
    theta = np.arctan2(y / 18.0, x / 25.0)
    return 1.0 * np.cos(theta * 22) + 0.6 * np.cos(theta * 44 + 0.7) + 0.25 * np.sin(np.hypot(x, y) * 3)


def _scene():
    points = []
    for t in np.linspace(0, 2 * np.pi, 1400, endpoint=False):
        for w in np.linspace(-5, 5, 41):
            x, y = (25 + w) * np.cos(t), (18 + w * 0.7) * np.sin(t)
            points.append((x, y, _height(x, y)))
    points = np.array(points)
    eps = 1e-3
    gx = (_height(points[:, 0] + eps, points[:, 1]) - _height(points[:, 0] - eps, points[:, 1])) / (2 * eps)
    gy = (_height(points[:, 0], points[:, 1] + eps) - _height(points[:, 0], points[:, 1] - eps)) / (2 * eps)
    normals = np.c_[-gx, -gy, np.ones(len(points))]
    normals /= np.linalg.norm(normals, axis=1)[:, None]
    t = np.linspace(0, 2 * np.pi, 600, endpoint=False)
    route = np.c_[25 * np.cos(t), 18 * np.sin(t)]
    route = np.c_[route, _height(route[:, 0], route[:, 1])]
    return points, normals, route


def _bending(route, step):
    z = route[:, 2]
    second = np.roll(z, -1) - 2 * z + np.roll(z, 1)
    return float(np.sqrt(np.mean((second / step ** 2) ** 2)))


class FrameEmbedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.points, cls.normals, cls.route = _scene()
        cls.smooth, _ = oc.smooth_route(cls.route, (0, 0, 1), 3.0)
        cls.step = float(np.mean(np.linalg.norm(np.roll(cls.smooth, -1, axis=0) - cls.smooth, axis=1)))
        cls.fixed, cls.factor, cls.stats = fe.solve(cls.smooth, cls.points, cls.normals, 3.0, cls.step)

    def test_limits_hold_after_predicted_boolean(self):
        self.assertEqual(self.stats['status'], 'OK')
        self.assertGreaterEqual(self.stats['min_thickness_mm'], fe.MIN_THICKNESS_MM - fe.TOLERANCE_MM)
        self.assertLessEqual(self.stats['embed_max_fraction'], fe.EMBED_MAX_FRACTION + 0.01)
        self.assertGreaterEqual(self.stats['support_min_fraction'], fe.EMBED_MIN_FRACTION - 0.01)
        self.assertGreater(self.stats['thin_stations_before'], 0, 'fixture must start with thin sections')

    def test_line_stays_smooth_no_rolls(self):
        raw = _bending(self.route, self.step)
        self.assertLess(_bending(self.smooth, self.step), raw / 8.0)
        self.assertLess(_bending(self.fixed, self.step), raw / 8.0, 'correction brought back the rolls')

    def test_smoothing_stays_inside_the_tube(self):
        _, deviation = oc.smooth_route(self.route, (0, 0, 1), 3.0)
        self.assertLessEqual(deviation, 0.45 * 3.0 + 1e-6)


if __name__ == '__main__':
    unittest.main()
