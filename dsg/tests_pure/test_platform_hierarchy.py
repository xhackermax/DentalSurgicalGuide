import unittest
from unittest.mock import patch
import numpy as np
from dsg import implant_catalogues as cat, section_optimizer as sections
from dsg.implant_platforms import platform_class, NARROW, STANDARD, WIDE, ORDER


class HierarchyRows(unittest.TestCase):
    def test_wide_only_library_gets_narrow_and_standard_from_its_system(self):
        own = cat.rows('BTI_INT_UNIPLUS')
        rows = cat.hierarchy_rows('BTI_INT_UNIPLUS')
        self.assertEqual(rows[:len(own)], own)
        self.assertEqual({platform_class(r) for r in rows}, set(ORDER))
        extra = rows[len(own):]
        self.assertTrue(extra)
        for row in extra:
            self.assertEqual(row['family'], own[0]['family'])
            self.assertNotEqual(row['library_family'], own[0]['family'])
            self.assertNotEqual(platform_class(row), WIDE)

    def test_complete_library_is_unchanged(self):
        self.assertEqual(cat.hierarchy_rows('BTI_COREX'), cat.rows('BTI_COREX'))


class HierarchyInSearch(unittest.TestCase):
    def test_if_wide_fits_standard_and_narrow_are_reported(self):
        class Field:
            base = np.eye(4); origin = np.zeros(3); frame = np.eye(3); summary = {}
            def reference(self, x, y): return {'height_mm': 0., 'spread_mm': 0., 'samples': 16}
            def assess(self, d, l, p): return {'admissible': True, 'section_hard_ok': True, 'score': 1.,
                                               'section_fit_fraction': 1., 'section_anchor_mm': 5.}
        def asset(d, l): return dict(id=f'{d}x{l}', family='T', diameter_mm=d, length_mm=l, platform_local_mm=[0, 0, l / 2],
                                     vertices_path='v', faces_path='f', reference='t', dimension_only=True)
        catalogue = [asset(d, l) for d in (3.3, 4.0, 5.0) for l in (8.5, 10, 13)]
        request = {'settings': {'max_shift_mm': 0., 'max_depth_mm': 1.5}, 'family': 'T', 'catalogue': catalogue}
        # Only the wide 5 x 10 is checked admissible on its own; any size inside
        # it (narrower and not longer) fits at the same pose.
        def exact(field, evaluator, matrix, a):
            ok = a['diameter_mm'] <= 5.0 and a['length_mm'] <= 10
            return {'admissible': ok, 'score': 1., 'reason': '' if ok else 'Seno',
                    'violations': [] if ok else [{'code': 'STRUCTURE'}]}
        with patch.object(sections, 'exact_section_evaluation', side_effect=exact):
            by = sections.search_sections(request, Field(), None)['by_platform']
        self.assertEqual(by[WIDE]['best']['asset']['id'], '5.0x10')
        self.assertIsNotNone(by[STANDARD]['best'])
        self.assertIsNotNone(by[NARROW]['best'])


if __name__ == '__main__':
    unittest.main()
