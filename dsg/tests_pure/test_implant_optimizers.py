import unittest
import numpy as np
from dsg.implant_optimization import pose_matrix,search_position,search_size

class Optimizers(unittest.TestCase):
    def test_position_holds_shape_and_pivot_and_limits(self):
        base=np.eye(4);base[:3,3]=(0,0,-5);pivot=np.zeros(3)
        calls=[]
        def evaluate(matrix,asset=None):
            calls.append(matrix.copy());assert asset is None
            x=matrix[0,3];safe=x<.8
            return {'admissible':safe,'score':1.-abs(x-.5),'support_fraction':1.-abs(x-.5)}
        result=search_position(evaluate,base,pivot,max_shift_mm=1.,max_tilt_deg=0,budget=70)
        self.assertEqual(result['status'],'PROPOSAL')
        self.assertGreater(result['best']['evaluation']['score'],result['baseline']['evaluation']['score'])
        for matrix in calls:
            self.assertTrue(np.allclose(matrix[:3,:3],base[:3,:3]))
            self.assertLessEqual(np.linalg.norm(matrix[:3,3]-base[:3,3]),1.+1e-8)
        self.assertTrue(np.array_equal(base[:3,3],(0,0,-5)))

    def test_rotations_pivot_about_platform(self):
        base=np.eye(4);base[2,3]=-5
        result=pose_matrix(base,(0,0,0),(0,0,0,7,0))
        self.assertTrue(np.allclose(result@np.array([0,0,5,1]),[0,0,0,1]))
        self.assertTrue(np.allclose(result[:3,:3].T@result[:3,:3],np.eye(3)))

    def test_constraints_cannot_be_offset_by_score(self):
        result=search_position(lambda matrix,asset=None:{'admissible':False,'score':1e9},np.eye(4),(0,0,0),budget=20)
        self.assertEqual(result['status'],'NO_FEASIBLE')
        self.assertIsNone(result['best'])

    def test_no_improvement_keeps_original(self):
        r=search_position(lambda matrix,asset=None:{'admissible':True,'score':1.},np.eye(4),(0,0,0),budget=20)
        self.assertEqual(r['status'],'NO_IMPROVEMENT')

    def test_budget_and_invalid_parameters(self):
        count=[]
        search_position(lambda matrix,asset=None:count.append(1) or {'admissible':True,'score':0},np.eye(4),(0,0,0),budget=11)
        self.assertLessEqual(len(count),11)
        for value in (float('nan'),-1):
            with self.assertRaises(ValueError):search_position(lambda *a:None,np.eye(4),(0,0,0),max_shift_mm=value)

    def test_size_uses_catalogue_and_keeps_platform_axis(self):
        base=np.eye(4);base[2,3]=-5
        catalogue=[{'id':str(n),'family':'A','diameter_mm':n,'length_mm':10.,'platform_local_mm':[0,0,5],
                    'vertices_path':'v.npy','faces_path':'f.npy','reference':'IFU test'} for n in (3.,4.)]
        calls=[]
        def evaluate(matrix,asset=None):
            calls.append((matrix.copy(),asset))
            return {'admissible':True,'score':asset['diameter_mm']}
        result=search_size(evaluate,catalogue,'A',base,(0,0,0),current_id='3.0')
        self.assertEqual(result['best']['asset']['id'],'4.0')
        for matrix,asset in calls:
            self.assertTrue(np.array_equal(matrix[:3,:3],base[:3,:3]))
            self.assertTrue(np.allclose(matrix@np.r_[asset['platform_local_mm'],1],[0,0,0,1]))
        self.assertEqual(len(calls),2)

    def test_size_missing_or_invalid_catalogue(self):
        self.assertEqual(search_size(lambda *a:None,[],'A',np.eye(4),(0,0,0))['status'],'NO_CATALOG')
        with self.assertRaises(ValueError):search_size(lambda *a:None,[{'id':'fake'}],'A',np.eye(4),(0,0,0))

    def test_catalogue_cannot_be_scaled_or_reflected(self):
        for scale in (2.,-1.):
            pose=np.eye(4);pose[0,0]=scale
            with self.assertRaises(ValueError):search_size(lambda *a:None,[],'A',pose,(0,0,0))

    def test_uncertain_geometry_is_not_a_valid_candidate(self):
        def uncertain(*args,**kwargs):raise ValueError('unverifiable')
        r=search_position(uncertain,np.eye(4),(0,0,0),budget=12)
        self.assertEqual(r['status'],'NO_FEASIBLE')
        self.assertGreater(r['rejected'],0)

if __name__=='__main__':unittest.main()
