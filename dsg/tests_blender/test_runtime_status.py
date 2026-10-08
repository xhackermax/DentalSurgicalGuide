"""Regression checks against misleading complete-DICOM and CUDA indicators."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

parent = Path(sys.argv[sys.argv.index('--') + 1]).resolve()
sys.path.insert(0, str(parent))
from dsg import runtime_bootstrap as runtime, segmentation_engines as engines

class RuntimeStatusTests(unittest.TestCase):
    def test_mini_reader_does_not_mean_full_runtime_ready(self):
        with patch.object(runtime.dicom_module, 'dicom_preflight_report', return_value={'standard_cbct_ready': False}), patch.object(runtime.dicom_module, 'load_numpy', return_value=object()), patch.object(runtime.dicom_module, 'load_pydicom', return_value=object()):
            result = runtime.component_status()
            self.assertTrue(result['dicom_reader'])
            self.assertFalse(result['base_required_ready'])
            self.assertFalse(result['all_required_ready'])

    def test_nvidia_driver_alone_does_not_mean_cuda_runtime(self):
        with patch.object(engines, '_nvidia_driver_present', return_value=True), patch.object(engines, 'runtime_compute_status', create=True, return_value={'cuda': False, 'device': 'CPU'}):
            self.assertEqual(runtime.component_status()['device'], 'CPU')

if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(RuntimeStatusTests))
    if not result.wasSuccessful():
        raise AssertionError('Runtime status regression')
