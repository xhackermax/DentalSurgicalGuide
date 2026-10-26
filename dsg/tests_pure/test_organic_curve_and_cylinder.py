import unittest
import numpy as np

from dsg.blender.organic_curve import adaptive_controls, handles, evaluate
from dsg.blender.cylinder_contact import intersects


class OrganicGeometryTests(unittest.TestCase):
    def test_adaptive_curve_keeps_user_anchors_and_bounds_route_error(self):
        angles = np.linspace(0, 2*np.pi, 120, endpoint=False)
        raw = np.c_[10*np.cos(angles), 7*np.sin(angles), .2*np.sin(3*angles)]
        anchors = raw[[0,17,43,78]]
        p, left, right, stats = adaptive_controls(raw, anchors, spacing=1.2, tolerance=.10)
        for a in anchors:
            self.assertLess(np.min(np.linalg.norm(p-a, axis=1)), 1e-7)
        self.assertLessEqual(stats['max_route_deviation_mm'], .10)
        self.assertLess(stats['curve_length_mm'], 1.05*np.linalg.norm(np.diff(np.vstack((raw,raw[0])),axis=0),axis=1).sum())
        # Incoming/outgoing handles are collinear at every point, including seam.
        cross = np.cross(p-left, right-p)
        self.assertLess(np.max(np.linalg.norm(cross,axis=1)), 1e-9)
        self.assertTrue(np.all(np.sum((p-left)*(right-p),axis=1) >= 0))

    def test_nonuniform_centripetal_handles_interpolate_exact_endpoints(self):
        p = np.array([[0.,0,0],[1,0,0],[3,1,0],[0,3,0]])
        left, right = handles(p)
        for i in range(len(p)):
            samples = evaluate(p[i],right[i],left[(i+1)%4],p[(i+1)%4])
            np.testing.assert_allclose(samples[0],p[i])
            np.testing.assert_allclose(samples[-1],p[(i+1)%4])

    def test_cylinder_contacts_triangle_interior_not_just_vertices(self):
        # All triangle vertices outside radius; its interior crosses the axis.
        self.assertTrue(intersects([[-4,-4,4],[4,-4,4],[0,4,4]], [[0,1,2]], 1, 6))
        self.assertFalse(intersects([[-4,-4,8],[4,-4,8],[0,4,8]], [[0,1,2]], 1, 6))
        self.assertFalse(intersects([[3,0,-2],[4,0,0],[5,0,2]], [[0,1,2]], 1, 6))
        self.assertTrue(intersects([[1,0,-2],[1,1,0],[1,-1,2]], [[0,1,2]], 1, 6))

    def test_cylinder_clips_caps_before_radial_projection(self):
        self.assertFalse(intersects([[0,0,20],[4,0,0],[4,2,0]], [[0,1,2]], 1, 1))
        with self.assertRaises(ValueError):
            intersects([[0,0,float('nan')]], [[0,0,0]], 1, 1)


if __name__ == '__main__':
    unittest.main()
