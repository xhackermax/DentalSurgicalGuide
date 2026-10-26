import unittest
from dsg.optimizer_profile import settings, margins
class MinimalProfileTests(unittest.TestCase):
 def test_fixed_search_and_no_implicit_regeneration(self):
  s=settings()
  self.assertEqual((s['combine_size_position'],s['size_policy']),(True,'LARGEST'))
  self.assertEqual((s['sinus_invasion_mm'],s['graft_gap_mm']),(2.,0.))
  self.assertEqual((s['max_diameter_mm'],s['max_length_mm']),(0.,0.))
  self.assertGreaterEqual(s['boundary_reserve_mm'],1.5)
  self.assertEqual(s['max_depth_mm'],1.5)
 def test_protected_floors_preserve_stricter_settings(self):
  self.assertEqual(margins(.1,.5,1.),dict(tooth=1.5,nerve=2.,implant=3.,cavity=0.))
  self.assertEqual(margins(2.,3.,4.),dict(tooth=2.,nerve=3.,implant=4.,cavity=0.))
 def test_settings_are_independent(self):
  a=settings();a['min_apical_mm']=0
  self.assertEqual(settings()['min_apical_mm'],3.)
if __name__=='__main__':unittest.main()
