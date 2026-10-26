"""Survey-line undercut fill (9.23.7): horizontal retention, no fins, no needles."""
import importlib.util
import pathlib
import sys
import types
import unittest

import numpy as np

for name in ('bpy', 'mathutils'):
    if name not in sys.modules:
        module = types.ModuleType(name)
        if name == 'mathutils':
            module.Vector = object
        sys.modules[name] = module

_PATH = pathlib.Path(__file__).resolve().parents[1] / 'blender' / 'undercut_fill.py'
_SPEC = importlib.util.spec_from_file_location('undercut_fill_under_test', _PATH)
uf = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(uf)


def tooth_ring(n=21, crown=4, ring=3):
    """Square crown in the centre, shadow ring of ``ring`` cells around it."""
    c = n // 2
    mask = np.zeros((n, n), dtype=bool)
    crown_cells = np.zeros_like(mask)
    crown_cells[c - crown:c + crown + 1, c - crown:c + crown + 1] = True
    outer = np.zeros_like(mask)
    outer[c - crown - ring:c + crown + ring + 1, c - crown - ring:c + crown + ring + 1] = True
    mask = outer & ~crown_cells
    underside = np.where(mask, 5.0, 0.0)       # bulge underside, hides the gap
    surface = np.where(mask, 1.0, 0.0)         # tooth/gingiva below the gap
    reach = np.full((n, n), np.inf)            # open air: the guide reaches anywhere
    reach[crown_cells] = -np.inf               # through the crown the guide is blocked
    return mask, underside, surface, reach, crown_cells


class Retention(unittest.TestCase):
    def test_erodes_only_from_the_guide_side(self):
        mask, under, surf, reach, crown = tooth_ring()
        before = mask.copy()
        removed = uf.erode_open_side(mask, under, surf, reach, 1)
        # outer ring removed, the cells touching the crown stay filled
        self.assertTrue(removed.any())
        touching_crown = before & uf._dilate(crown, 1)
        self.assertTrue(mask[touching_crown].all())
        self.assertFalse((removed & touching_crown).any())

    def test_retention_grows_with_depth(self):
        counts = []
        for steps in (1, 2):
            mask, under, surf, reach, _crown = tooth_ring()
            counts.append(int(uf.erode_open_side(mask, under, surf, reach, steps).sum()))
        self.assertLess(counts[0], counts[1])

    def test_retention_steps(self):
        self.assertEqual(uf.retention_steps(0.0, 0.1), 0)
        self.assertEqual(uf.retention_steps(0.1, 0.1), 1)
        self.assertEqual(uf.retention_steps(0.3, 0.1), 3)


class Geometry(unittest.TestCase):
    def grid(self, n):
        return {'u0': 0.0, 'v0': 0.0, 'cell': 0.1, 'nu': n, 'nv': n,
                'axis': (0.0, 0.0, 1.0), 'e1': (1.0, 0.0, 0.0), 'e2': (0.0, 1.0, 0.0)}

    def test_roof_never_lifted_by_a_tall_neighbour(self):
        mask = np.zeros((4, 4), dtype=bool)
        mask[1, 1] = mask[2, 1] = True
        tops = np.zeros((4, 4))
        bottoms = np.zeros((4, 4))
        tops[1, 1], tops[2, 1] = 1.0, 10.0
        vertices, faces = uf.slab_geometry(mask, tops, bottoms, self.grid(4))
        top_heights = vertices[: len(vertices) // 2, 2]
        # the low column's roof stays at its own height (no fin at 5.5 mm)
        self.assertAlmostEqual(float(np.min(top_heights)), 1.0)
        self.assertLessEqual(int((top_heights > 1.0 + 1e-9).sum()), 2)

    def test_needles_dropped_and_gaps_bridged(self):
        mask = np.zeros((12, 12), dtype=bool)
        mask[2, 2] = True                       # isolated needle
        mask[4:10, 5] = True                    # two parallel needles one
        mask[4:10, 7] = True                    # empty column apart
        tops = np.where(mask, 2.0, 0.0)
        bottoms = np.where(mask, 0.0, 0.0)
        under = tops.copy()
        surf = bottoms.copy()
        dropped = uf.clean_mask(mask, tops, bottoms, under, surf)
        self.assertTrue(dropped[2, 2])
        self.assertFalse(mask[2, 2])
        self.assertTrue(mask[5:9, 6].all())     # bridged into one wall
        self.assertAlmostEqual(float(tops[6, 6]), 2.0)

    def test_slab_is_closed(self):
        mask = np.zeros((8, 8), dtype=bool)
        mask[2:6, 2:5] = True
        tops = np.where(mask, 2.0, 0.0)
        bottoms = np.zeros((8, 8))
        vertices, faces = uf.slab_geometry(mask, tops, bottoms, self.grid(8))
        edges = {}
        for face in faces:
            for a, b in zip(face, face[1:] + face[:1]):
                key = (min(a, b), max(a, b))
                edges[key] = edges.get(key, 0) + 1
        self.assertTrue(all(count == 2 for count in edges.values()))


if __name__ == '__main__':
    unittest.main()
