"""Exercise the real engine API used by the immediate-route button."""
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
import bpy
parent = Path(sys.argv[sys.argv.index('--') + 1]).resolve()
sys.path.insert(0, str(parent))
import dsg
dsg.register()
core, dicom_module = dsg.core, dsg.dicom_module

class ImmediateGateTests(unittest.TestCase):
    def setUp(self):
        bpy.context.scene['DSG_route_step'] = 'CBCT_READY'
        bpy.context.scene.dicom_wizard_pro.volume_loaded = True
        dicom_module.RUNTIME.update_lock = False
        self.loaded = patch.object(dicom_module.RUNTIME, 'is_loaded', return_value=True)
        self.busy = patch.object(dicom_module, 'semantic_workflow_busy', return_value=False)
        self.loaded.start()
        self.busy.start()
    def tearDown(self):
        self.loaded.stop()
        self.busy.stop()
    def test_ready_totalseg_enables_immediate_route(self):
        bpy.context.scene.dicom_wizard_pro.ai_segmentation_engine = 'TOTALSEG'
        ready, reason = core._immediate_route_readiness(bpy.context)
        self.assertTrue(ready, reason)
        self.assertTrue(bpy.ops.dsg_suite.start_immediate_route.poll())
    def test_missing_umamba_reports_engine_error(self):
        bpy.context.scene.dicom_wizard_pro.ai_segmentation_engine = 'UMAMBA2'
        ready, reason = core._immediate_route_readiness(bpy.context)
        self.assertFalse(ready)
        self.assertIn('Linux/CUDA', reason)
        self.assertNotIn('attribute', reason)
    def test_toothseg_stays_blocked_without_jaw_capability(self):
        bpy.context.scene.dicom_wizard_pro.ai_segmentation_engine = 'TOOTHSEG'
        ready, reason = core._immediate_route_readiness(bpy.context)
        self.assertFalse(ready)
        self.assertIn('maxila/mandíbula', reason)

try:
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ImmediateGateTests))
    if not result.wasSuccessful():
        raise AssertionError('Immediate-route regression')
finally:
    dsg.unregister()
