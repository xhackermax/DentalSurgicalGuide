"""Run in Blender with -- /path/to/addon-parent; no neural inference."""
import sys
import tempfile
import unittest
import shutil
from pathlib import Path

parent = Path(sys.argv[sys.argv.index("--") + 1]).resolve() if "--" in sys.argv else Path(__file__).resolve().parents[2]
sys.path.insert(0, str(parent))
from dsg import segmentation_engines as engines

class CheckpointTests(unittest.TestCase):
    def test_checkpoint_beyond_windows_path_limit_is_detected(self):
        with tempfile.TemporaryDirectory(dir=parent, prefix="long_path_test_") as tmp:
            base = Path(tmp)
            model = base / "Dataset121_Teeth" / ("model_" + "x" * 100) / "fold_5"
            extended = Path("\\\\?\\" + str(model)) if sys.platform == "win32" else model
            extended.mkdir(parents=True)
            cp = extended / "checkpoint_final.pth"
            cp.write_bytes(b"0" * 1_000_000)
            self.assertGreater(len(str(model / cp.name)), 260)
            try:
                ok, path = engines._contains_checkpoint(base, dataset_tokens=("dataset121",))
                self.assertTrue(ok, "Blender failed to detect an installed model at a long Windows path")
                self.assertTrue(path.endswith("checkpoint_final.pth"))
            finally:
                # Blender itself cannot clean the long path without a prefix.
                assert base.resolve().is_relative_to(parent)
                shutil.rmtree("\\\\?\\" + str(base) if sys.platform == "win32" else base)

    def test_truncated_checkpoint_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=parent) as tmp:
            cp = Path(tmp) / "checkpoint_final.pth"
            cp.write_bytes(b"partial")
            self.assertEqual(engines._contains_checkpoint(Path(tmp)), (False, ""))

    def test_wrong_dataset_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=parent) as tmp:
            cp = Path(tmp) / "checkpoint_final.pth"
            cp.write_bytes(b"0" * 1_000_000)
            self.assertEqual(engines._contains_checkpoint(Path(tmp), dataset_tokens=("dataset123",)), (False, ""))

if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(CheckpointTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise AssertionError("Engine checkpoint regression tests failed")
