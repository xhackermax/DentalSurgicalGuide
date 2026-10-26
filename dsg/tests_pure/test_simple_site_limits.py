import importlib.util, pathlib, unittest
import numpy as np

spec = importlib.util.spec_from_file_location(
    'simple_site_limits', pathlib.Path(__file__).resolve().parents[1] / 'blender' / 'simple_site_limits.py')
ssl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ssl)


def _crown(cx, width=7.0, bl=9.0, z0=0.0, z1=7.0, n=600, seed=0):
    rng = np.random.default_rng(seed)
    return np.c_[rng.uniform(cx - width / 2, cx + width / 2, n), rng.uniform(-bl / 2, bl / 2, n), rng.uniform(z0, z1, n)]


class SimpleSiteLimitsTest(unittest.TestCase):
    def setUp(self):
        self.removed = _crown(0.0)
        self.ios = np.r_[_crown(-7.2, seed=1), _crown(7.2, seed=2), _crown(0.0, 7.0, 9.0, -6, -1, seed=3)]

    def test_gap_is_the_removed_crown_mesiodistal_width(self):
        frame = ssl.gap_frame(self.removed, self.ios, (0, 0, -1))
        self.assertIsNotNone(frame)
        self.assertGreater(abs(frame['e1'][0]), 0.95)        # mesio-distal along x
        self.assertAlmostEqual(frame['hi'] - frame['lo'], 7.0, delta=0.5)
        self.assertGreater(frame['axis'][2], 0)               # oriented occlusally

    def test_slabs_are_closed_outward_boxes_outside_the_gap(self):
        frame = ssl.gap_frame(self.removed, self.ios, (0, 0, 1))
        boxes = ssl.slabs(frame)
        self.assertEqual(len(boxes), 2)
        for vertices, faces, point, normal in boxes:
            self.assertGreater(float((frame['center'] - point) @ normal), 0)   # normal faces the gap
            centroid = vertices.mean(axis=0)
            self.assertTrue(np.all((vertices - point) @ normal <= 1e-6))       # box lies behind its plane
            volume = sum(np.dot(vertices[a] - centroid, np.cross(vertices[b] - centroid, vertices[c] - centroid))
                         for a, b, c in faces) / 6.0
            self.assertGreater(volume, 0)
            proj = (vertices - frame['center']) @ frame['e1']
            self.assertTrue(np.all(proj >= frame['hi'] + ssl.ROOT_OUTSET_MM - 1e-6) or
                            np.all(proj <= frame['lo'] - ssl.ROOT_OUTSET_MM + 1e-6))
            # The boxes reach far apically from the crown.
            self.assertLess(((vertices - frame['center']) @ frame['axis']).min(), frame['t_cer'] - 20)

    def test_no_crown_no_frame(self):
        self.assertIsNone(ssl.gap_frame(np.zeros((5, 3)), self.ios, (0, 0, 1)))


if __name__ == '__main__':
    unittest.main()
