import unittest
import numpy as np
from dsg.blender.surface_clearance_bounds import classify

class DistanceBoundsTests(unittest.TestCase):
    def test_nearest_face_interior_instead_of_only_vertices(self):
        # Every triangle vertex is distant; the closest point is in its middle.
        triangle=np.array([[[-5,-5,0],[5,-5,0],[0,5,0]]],dtype=float)
        query=lambda point:float(np.linalg.norm(point-[0,0,1]))
        self.assertTrue(all(query(point)>2 for point in triangle[0]))
        result=classify(triangle,query,2.)
        self.assertEqual(result['status'],'BUFFER_INVADED')
        self.assertLess(result['upper_mm'],2.)
        self.assertLessEqual(result['lower_mm'],1.)
    def test_safe_diagonal_euclidean_gap_not_square_cylinder_corner(self):
        triangle=np.array([[[1.8,1.8,0],[1.81,1.8,0],[1.8,1.81,0]]])
        result=classify(triangle,lambda p:float(np.linalg.norm(p)),2.)
        self.assertEqual(result['status'],'SAFE')
        self.assertGreater(result['lower_mm'],2.)
        self.assertLessEqual(result['lower_mm'],np.sqrt(2)*1.8)
    def test_threshold_uncertainty_blocks_instead_of_false_clear(self):
        triangle=np.array([[[0,0,0],[.01,0,0],[0,.01,0]]])
        result=classify(triangle,lambda p:2.,2.)
        self.assertEqual(result['status'],'LIMIT')
    def test_invalid_geometry_or_failed_query_never_pass(self):
        triangle=np.array([[[0,0,0],[1,0,0],[0,1,0]]])
        with self.assertRaises(ValueError):classify(triangle,lambda p:float('nan'),2.)
        with self.assertRaises(ValueError):classify(np.full((1,3,3),float('nan')),lambda p:4.,2.)

if __name__=='__main__':unittest.main()
