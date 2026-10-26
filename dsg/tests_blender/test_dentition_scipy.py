"""Bounding boxes must load installed SciPy through the private DSG runtime."""
import sys
from pathlib import Path
import unittest
import bpy
import numpy as np
parent = Path(sys.argv[sys.argv.index('--') + 1]).resolve()
sys.path.insert(0, str(parent))
import dsg
dsg.register()

class DentitionRuntimeTests(unittest.TestCase):
    def test_private_scipy_finds_exact_label_bounding_box(self):
        labels = np.zeros((4, 6, 8), dtype=np.uint8)
        labels[1:3, 2:5, 3:7] = 2
        try:
            boxes = dsg.cbct_dental_module._bbox_slices(labels, 55)
        except RuntimeError as exc:
            self.fail(f'Installed SciPy is inaccessible to the immediate route: {exc}')
        self.assertEqual(boxes[1], (slice(1, 3), slice(2, 5), slice(3, 7)))
        self.assertIsNone(boxes[0])
        self.assertNotIn('torch', sys.modules, 'Bounding-box extraction must not import torch in Blender')

try:
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(DentitionRuntimeTests))
    if not result.wasSuccessful():
        raise AssertionError('Private SciPy regression')
finally:
    dsg.unregister()
