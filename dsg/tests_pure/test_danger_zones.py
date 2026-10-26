"""Danger-zone rules: nasal never invaded, sinus up to 2 mm with alert."""
import importlib.util
import pathlib
import unittest

_PATH = pathlib.Path(__file__).resolve().parents[1] / 'danger_zones.py'
_SPEC = importlib.util.spec_from_file_location('danger_zones', _PATH)
dz = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(dz)


class DangerZoneRules(unittest.TestCase):
    def test_sinus_free(self):
        self.assertEqual(dz.classify('left_maxillary_sinus', 0.0, 3.2)[0], dz.SAFE)

    def test_sinus_invasion_within_limit_is_alert(self):
        status, message = dz.classify('right_maxillary_sinus', 1.4, None)
        self.assertEqual(status, dz.ALERT)
        self.assertIn('1.4', message)

    def test_sinus_exactly_two_mm_is_alert(self):
        self.assertEqual(dz.classify('right_maxillary_sinus', 2.0, None)[0], dz.ALERT)

    def test_sinus_beyond_two_mm_blocks(self):
        self.assertEqual(dz.classify('right_maxillary_sinus', 2.3, None)[0], dz.BLOCK)

    def test_sinus_limit_cannot_exceed_two_mm(self):
        self.assertEqual(dz.classify('left_maxillary_sinus', 2.6, None, sinus_max_mm=5.0)[0], dz.BLOCK)

    def test_nasal_any_invasion_blocks(self):
        self.assertEqual(dz.classify('nasal_cavity_left', 0.3, None)[0], dz.BLOCK)

    def test_nasal_close_is_alert(self):
        self.assertEqual(dz.classify('nasal_cavity_right', 0.0, 0.6)[0], dz.ALERT)

    def test_nasal_far_is_safe(self):
        self.assertEqual(dz.classify('nasal_cavity_right', 0.0, 4.0)[0], dz.SAFE)

    def test_surface_noise_is_not_invasion(self):
        self.assertEqual(dz.classify('nasal_cavity_left', 0.02, 0.0)[0], dz.ALERT)


if __name__ == '__main__':
    unittest.main()
