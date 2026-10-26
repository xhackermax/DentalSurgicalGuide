"""Regression: SIMPLE uses the same ITK model-grid reconstruction as teeth."""
import sys,types,unittest
from pathlib import Path
import numpy as np
from scipy import ndimage
from skimage.measure import marching_cubes
root=Path(__file__).resolve().parents[1]
pkg=types.ModuleType('dsg');pkg.__path__=[str(root)];sys.modules['dsg']=pkg
from dsg import organic_teeth as organic

class ArchReconstructionTests(unittest.TestCase):
    def test_hollow_arch_preserves_cavity_and_separate_components(self):
        shape=np.array([80]*3);spacing=np.array([.2]*3)
        low,ratio=organic.model_grid(shape,spacing)
        z,y,x=np.indices(low)
        radius=np.sqrt((z-19)**2+(y-19)**2+(x-19)**2)
        mask=((radius<9)&(radius>5)) | (((z-5)**2+(y-5)**2+(x-5)**2)<4)
        cells=[np.rint(np.arange(n)*r).astype(int) for n,r in zip(shape,ratio)]
        labels=mask[np.ix_(*cells)].astype(np.uint8)
        before=labels.copy()
        def xyz(zyx):return (np.asarray(zyx)*spacing)[:,::-1]
        native,faces,*_=marching_cubes(labels,.5)
        v,f,stats=organic.organic_tooth(labels,1,spacing,to_display=xyz,source_xyz=xyz(native),surface_kind='ARCH')
        self.assertTrue(np.array_equal(labels,before))
        self.assertTrue(stats['closed'])
        self.assertEqual(stats['algorithm'],organic.ALGORITHM)
        self.assertEqual(stats['surface_kind'],'ARCH')
        self.assertEqual(stats['neighbour_teeth'],[])
        self.assertGreaterEqual(stats['kept_components'],3) # outer shell, cavity shell, detached part
        self.assertLess(abs(stats['delta_vs_voxel_count_percent']),3)
        self.assertEqual(stats['inner_shells_removed'],0)
        centre=xyz(np.array([[19,19,19]])/ratio)[0]
        self.assertGreater(np.linalg.norm(v-centre,axis=1).min(),2)
        self.assertGreater(stats['distance_to_source_max_mm'],.05)
        self.assertLessEqual(stats['distance_to_source_max_mm'],1)
        print('ARCH_MODEL_GRID_PASS',stats)

if __name__=='__main__':unittest.main()
