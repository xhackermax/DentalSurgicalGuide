import unittest
from unittest.mock import patch
import numpy as np
from dsg import section_optimizer as sections
from dsg.implant_platforms import platform_class, NARROW, STANDARD, WIDE


class Platforms(unittest.TestCase):
    def test_classes(self):
        self.assertEqual(platform_class({'diameter_mm': 3.5}), NARROW)
        self.assertEqual(platform_class({'diameter_mm': 3.75}), STANDARD)
        self.assertEqual(platform_class({'diameter_mm': 4.25}), STANDARD)
        self.assertEqual(platform_class({'diameter_mm': 4.5}), WIDE)
        self.assertEqual(platform_class({'diameter_mm': 4.2, 'platform': 'SP'}), STANDARD)
        self.assertEqual(platform_class({'diameter_mm': 3.3, 'platform': 'RN'}), STANDARD)
        self.assertEqual(platform_class({'diameter_mm': 4.8, 'platform': 'EV 4.8'}), WIDE)
        self.assertEqual(platform_class({'diameter_mm': 3.0, 'platform': 'MV'}), NARROW)

    def test_one_proposal_per_platform(self):
        class Field:
            base = np.eye(4); origin = np.zeros(3); frame = np.eye(3); summary = {}
            def reference(self, x, y): return {'height_mm': 0., 'spread_mm': 0., 'samples': 16}
            def assess(self, d, l, p): return {'admissible': True, 'section_hard_ok': True, 'score': 1.,
                                               'section_fit_fraction': 1., 'section_anchor_mm': 5.}
        def asset(d, l): return dict(id=f'{d}x{l}', family='T', diameter_mm=d, length_mm=l, platform_local_mm=[0, 0, l / 2],
                                     vertices_path='v', faces_path='f', reference='t', dimension_only=True)
        catalogue = [asset(d, l) for d in (3.5, 4.0, 5.0) for l in (8.5, 10, 13)]
        request = {'settings': {'max_shift_mm': 0., 'max_depth_mm': 1.5}, 'family': 'T', 'catalogue': catalogue}
        fits = {(3.5, 13), (3.5, 10), (3.5, 8.5), (4.0, 10), (4.0, 8.5)}   # wide never fits
        def exact(field, evaluator, matrix, a):
            ok = (a['diameter_mm'], a['length_mm']) in fits
            return {'admissible': ok, 'score': 1., 'reason': '' if ok else 'Raíz vecina',
                    'violations': [] if ok else [{'code': 'STRUCTURE'}]}
        with patch.object(sections, 'exact_section_evaluation', side_effect=exact):
            out = sections.search_sections(request, Field(), None)
        by = out['by_platform']
        self.assertEqual(by[NARROW]['best']['asset']['id'], '3.5x13')
        self.assertEqual(by[STANDARD]['best']['asset']['id'], '4.0x10')
        self.assertIsNone(by[WIDE]['best'])
        self.assertEqual(by[WIDE]['reason'], 'Raíz vecina')
        self.assertEqual(out['best']['asset']['id'], '3.5x13')

    def test_narrow_never_impossible_when_standard_fits(self):
        """Containment: a narrower, not-longer size fits where a wider one fits."""
        class Field:
            base = np.eye(4); origin = np.zeros(3); frame = np.eye(3); summary = {}
            def reference(self, x, y): return {'height_mm': 0., 'spread_mm': 0., 'samples': 16}
            def assess(self, d, l, p): return {'admissible': True, 'section_hard_ok': True, 'score': 1.,
                                               'section_fit_fraction': 1., 'section_anchor_mm': 5.}
        def asset(d, l): return dict(id=f'{d}x{l}', family='T', diameter_mm=d, length_mm=l, platform_local_mm=[0, 0, l / 2],
                                     vertices_path='v', faces_path='f', reference='t', dimension_only=True)
        catalogue = ([asset(3.3, l) for l in (8, 10, 11.5, 13, 14, 16)]
                     + [asset(4.1, l) for l in (8, 10, 12, 14, 16)])
        request = {'settings': {'max_shift_mm': 0., 'max_depth_mm': 1.5}, 'family': 'T', 'catalogue': catalogue}
        # Standard reaches 4.1x10 within the budget (16,14,12,10); the narrow
        # budget (4) stops at 3.3x11.5 and never reaches 3.3x10.
        fits = {(4.1, 10), (4.1, 8), (3.3, 10), (3.3, 8)}
        def exact(field, evaluator, matrix, a):
            ok = (a['diameter_mm'], a['length_mm']) in fits
            return {'admissible': ok, 'score': 1., 'reason': '' if ok else 'Conducto',
                    'violations': [] if ok else [{'code': 'STRUCTURE'}]}
        with patch.object(sections, 'exact_section_evaluation', side_effect=exact):
            out = sections.search_sections(request, Field(), None, verification_budget=4)
        by = out['by_platform']
        self.assertIsNotNone(by[NARROW]['best'])
        self.assertEqual(by[NARROW]['best']['asset']['id'], '3.3x10')
        self.assertEqual(by[NARROW].get('contained_in'), '4.1x10')
        self.assertEqual(by[STANDARD]['best']['asset']['id'], '4.1x10')


if __name__ == '__main__':
    unittest.main()
