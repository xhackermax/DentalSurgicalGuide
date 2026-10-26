import unittest
from dsg import optimizer_profile
class LengthPolicy(unittest.TestCase):
    def test_threshold(self):
        from dsg.sinus_policy import permitted_invasion
        self.assertEqual(permitted_invasion(8),2.)
        self.assertEqual(permitted_invasion(9.99),2.)
        self.assertEqual(permitted_invasion(10),0.)
        self.assertEqual(permitted_invasion(14),0.)
        self.assertEqual(permitted_invasion(8,.5),.5)
        for length in [0,-1,float('nan'),float('inf'),None]:
            with self.assertRaises(ValueError):permitted_invasion(length)
    def test_zero_limit_never_labels_positive_penetration_safe(self):
        from dsg.danger_zones import classify,BLOCK
        self.assertEqual(classify('sinus',.001,None,0)[0],BLOCK)
        self.assertEqual(classify('sinus',2.001,None,2)[0],BLOCK)
        from dsg.danger_zones import ALERT
        self.assertEqual(classify('sinus',.01,None,2)[0],ALERT)
