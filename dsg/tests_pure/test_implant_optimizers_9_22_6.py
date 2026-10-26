"""9.22.6: implant-frame search, depth limit, noise threshold, size identity and policy."""
import unittest
import numpy as np
from dsg.implant_optimization import pose_matrix,search_position,search_size

def rot_x(deg):
    a=np.radians(deg);m=np.eye(4);m[1:3,1:3]=[[np.cos(a),-np.sin(a)],[np.sin(a),np.cos(a)]];return m

def row(ident,d,l):
    return dict(id=ident,family='T',diameter_mm=d,length_mm=l,platform_local_mm=[0,0,l/2],vertices_path='v',faces_path='f',reference='t')

class Position(unittest.TestCase):
    def test_depth_is_fixed_by_default_even_if_deeper_scores_better(self):
        calls=[]
        def evaluate(m,asset=None):
            calls.append(m.copy());return {'admissible':True,'score':1.-.5*m[2,3]}
        r=search_position(evaluate,np.eye(4),(0,0,0),max_shift_mm=1.,max_tilt_deg=0.)
        self.assertTrue(all(abs(m[2,3])<1e-9 for m in calls),'Axial movement explored with depth locked')
        self.assertEqual(r['status'],'NO_IMPROVEMENT')

    def test_depth_limit_is_separate_and_respected(self):
        r=search_position(lambda m,asset=None:{'admissible':True,'score':1.-m[2,3]},np.eye(4),(0,0,0),max_shift_mm=1.,max_tilt_deg=0.,max_depth_mm=.5)
        self.assertEqual(r['status'],'PROPOSAL')
        self.assertAlmostEqual(r['best']['parameters'][2],-.5)
        self.assertLessEqual(abs(r['best']['matrix'][2][3]),.5+1e-9)

    def test_shift_is_expressed_in_implant_frame(self):
        base=rot_x(30.);axis=base[:3,2]
        p=pose_matrix(base,(0,0,0),(0,0,-1,0,0))
        self.assertTrue(np.allclose(p[:3,3],-axis))
        lateral=pose_matrix(base,(0,0,0),(0,1,0,0,0))[:3,3]
        self.assertAlmostEqual(float(lateral@axis),0.)

    def test_noise_level_gain_keeps_original(self):
        r=search_position(lambda m,asset=None:{'admissible':True,'score':1.+.0011*m[0,3]},np.eye(4),(0,0,0),max_tilt_deg=0.)
        self.assertEqual(r['status'],'NO_IMPROVEMENT')
        self.assertEqual(r['best']['parameters'],[0.]*5)

    def test_smallest_movement_among_near_best(self):
        # Plateau beyond x>=.25: every pose there is equivalent; the closest wins.
        r=search_position(lambda m,asset=None:{'admissible':True,'score':1. if m[0,3]>=.25-1e-9 else 0.},np.eye(4),(0,0,0),max_shift_mm=1.,max_tilt_deg=0.)
        self.assertEqual(r['status'],'PROPOSAL')
        self.assertAlmostEqual(r['best']['parameters'][0],.25)

    def test_infeasible_original_still_gets_proposal(self):
        r=search_position(lambda m,asset=None:{'admissible':m[0,3]>.4,'score':.5},np.eye(4),(0,0,0),max_tilt_deg=0.)
        self.assertEqual(r['status'],'PROPOSAL');self.assertGreater(r['best']['parameters'][0],.4)

class Size(unittest.TestCase):
    rows=[row('a',3.5,10),row('b',4.,10),row('c',4.5,8.5)]
    ok=staticmethod(lambda m,asset=None:{'admissible':True,'score':{'a':3.,'b':2.,'c':1.}[asset['id']]})

    def test_current_recognised_by_dimensions(self):
        r=search_size(self.ok,self.rows,'T',np.eye(4),(0,0,0),current={'diameter_mm':4.,'length_mm':10.})
        self.assertEqual(r['status'],'NO_IMPROVEMENT');self.assertEqual(r['baseline_match'],'DIMENSIONS')
        r=search_size(self.ok,self.rows,'T',np.eye(4),(0,0,0),current={'diameter_mm':3.5,'length_mm':10})
        self.assertEqual(r['status'],'PROPOSAL');self.assertEqual(r['best']['asset']['id'],'b')

    def test_current_recognised_by_id(self):
        r=search_size(self.ok,self.rows,'T',np.eye(4),(0,0,0),current_id='c')
        self.assertEqual(r['baseline_match'],'ID');self.assertEqual(r['status'],'PROPOSAL')

    def test_support_policy(self):
        r=search_size(self.ok,self.rows,'T',np.eye(4),(0,0,0),policy='SUPPORT')
        self.assertEqual(r['best']['asset']['id'],'a');self.assertEqual(r['status'],'COMPARISON')

    def test_caps_bound_the_proposal(self):
        r=search_size(self.ok,self.rows,'T',np.eye(4),(0,0,0),max_diameter_mm=4.)
        self.assertEqual(r['best']['asset']['id'],'b');self.assertEqual(r['capped'],1)
        r=search_size(self.ok,self.rows,'T',np.eye(4),(0,0,0),current={'diameter_mm':4.5,'length_mm':8.5},max_diameter_mm=4.)
        self.assertEqual(r['status'],'PROPOSAL','An over-cap current implant must not block a capped proposal')
        self.assertEqual(r['best']['asset']['id'],'b')
        with self.assertRaises(ValueError):search_size(self.ok,self.rows,'T',np.eye(4),(0,0,0),policy='X')

if __name__=='__main__':unittest.main()
