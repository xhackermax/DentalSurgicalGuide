"""Batch path agrees with the previous exact clipping calculation."""
import unittest
import numpy as np
from dsg.blender.cylinder_contact import intersects,clip_z

def reference(vertices,radius,half_height,epsilon=1e-6):
    r,h=radius+epsilon,half_height+epsilon
    poly=clip_z(np.asarray(vertices),h,True)
    if len(poly)<3:return False
    poly=clip_z(poly,-h,False)
    if len(poly)<3:return False
    xy=poly[:,:2];following=np.roll(xy,-1,axis=0);delta=following-xy
    t=np.clip(-np.sum(xy*delta,axis=1)/np.maximum(np.sum(delta*delta,axis=1),1e-20),0,1)
    nearest=xy+t[:,None]*delta
    if np.min(np.sum(nearest*nearest,axis=1))<=r*r:return True
    cross=xy[:,0]*following[:,1]-xy[:,1]*following[:,0]
    return bool(abs(float(np.sum(cross)))>epsilon and (np.all(cross>=-epsilon) or np.all(cross<=epsilon)))

class BatchCylinderTests(unittest.TestCase):
    def test_exact_agreement_caps_edges_interiors_degenerate_and_empty_batch(self):
        random=np.random.default_rng(9203)
        triangles=random.uniform(-6,6,(1000,3,3))
        triangles=np.concatenate((triangles,np.array([[[1,0,0]]*3,[[3,0,0]]*3,[[2,2,0],[3,2,0],[2,3,0]]])))
        for triangle in triangles:
            self.assertEqual(intersects(triangle,[[0,1,2]],1.,2.),reference(triangle,1.,2.))
        vertices=np.array([[20,20,20],[21,20,20],[20,21,20]])
        self.assertFalse(intersects(vertices,[[0,1,2]],1.,2.))
    def test_batch_matches_individual_hits(self):
        random=np.random.default_rng(92030)
        for _ in range(60):
            tris=random.normal(size=(12,3,3))*3
            expected=any(reference(t,1,2) for t in tris)
            self.assertEqual(intersects(tris.reshape(-1,3),np.arange(36).reshape(-1,3),1,2),expected)

if __name__=='__main__':unittest.main()
