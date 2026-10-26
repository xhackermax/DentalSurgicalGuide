import unittest
import numpy as np
from dsg import cbct_pipeline_worker as worker
from dsg.pipeline_core import Labelmap

class UpperLabelsTests(unittest.TestCase):
    def test_sinus_classes_are_preserved_instead_of_discarded(self):
        raw=np.array([[[1,5,6]]],dtype=np.uint8)
        labels,_=worker._translate_totalseg(np,raw,{1:'upper_right_central_incisor_fdi11',5:'left_maxillary_sinus',6:'right_maxillary_sinus'})
        self.assertEqual(labels.tolist(),[[[8,56,57]]])
        parsed=Labelmap.parse(labels,labels.shape,(1.,1.,1.),'TOTALSEG')
        self.assertIn(56,parsed.counts)
    def test_auxiliary_nasal_labels_do_not_overwrite_teeth_or_bone(self):
        from dsg.cbct_upper_cavities import merge_nasal
        primary=np.array([[[8,54,0,0]]],dtype=np.uint8)
        nasal=np.array([[[15,14,15,14]]],dtype=np.uint8)
        merged=merge_nasal(primary,nasal,{14:'nasal_cavity_right',15:'nasal_cavity_left'})
        self.assertEqual(merged.tolist(),[[[8,54,58,59]]])
        self.assertEqual(primary.tolist(),[[[8,54,0,0]]])

if __name__=='__main__':unittest.main()
