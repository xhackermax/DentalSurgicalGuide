import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("installer_under_test", ROOT / "segmentation_install_worker.py")
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
from installation_lock import installation_lock, installation_running

class InstallerTests(unittest.TestCase):
    def test_dependency_repair_keeps_tested_cuda_wheel(self):
        with tempfile.TemporaryDirectory() as tmp:
            req = {'runtime_root': tmp, 'site_packages': tmp + '/site', 'torch_variant': 'cu126'}
            with patch.object(worker, '_run') as run:
                worker._pip(req, 'nnunetv2')
            command = run.call_args.args[0]
            self.assertIn('--constraint', command)
            constraint = Path(command[command.index('--constraint') + 1]).read_text()
            self.assertIn('torch==2.14.1+cu126', constraint)
            self.assertIn('torchvision==0.29.1+cu126', constraint)
            self.assertIn('https://download.pytorch.org/whl/cu126', command)

    def test_missing_dicom_is_reported_even_when_engines_succeed(self):
        with tempfile.TemporaryDirectory() as tmp:
            req = {'runtime_root': tmp, 'site_packages': tmp + '/site', 'engine': 'ALL', 'dicom_vendor_dir': tmp + '/vendor'}
            with patch.object(worker, 'prepare_dicom', side_effect=RuntimeError('codec missing')), patch.object(worker, 'prepare_compute'), patch.object(worker, 'install_totalseg'), patch.object(worker, 'install_toothseg'), patch.object(worker, 'install_umamba2'):
                worker._install_request(req)
            status = json.loads((Path(tmp) / 'install_status.json').read_text())
            self.assertEqual(status['phase'], 'PARTIAL')
            self.assertEqual(status['detail']['components']['DICOM']['status'], 'ERROR')
            self.assertIn('codec missing', status['error'])

    def test_concurrent_installer_is_blocked_and_lock_released(self):
        with tempfile.TemporaryDirectory() as tmp:
            with installation_lock(tmp):
                self.assertTrue(installation_running(tmp))
                with self.assertRaisesRegex(RuntimeError, "en curso"):
                    with installation_lock(tmp):
                        self.fail("Second installer acquired the same runtime")
            self.assertFalse(installation_running(tmp))

    def test_ready_toothseg_reuses_models_without_pip_or_download(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repos/ToothSeg"
            repo.mkdir(parents=True)
            (repo / ".dsg_commit").write_text("test")
            (root / "site/torch").mkdir(parents=True)
            (root / "site/nnunetv2").mkdir()
            for token in ("Dataset121", "Dataset123"):
                p = root / "models" / token / "fold_5/checkpoint_final.pth"
                p.parent.mkdir(parents=True)
                p.write_bytes(b"0" * 1_000_000)
            req = {"runtime_root": tmp, "repos_root": str(root / "repos"), "site_packages": str(root / "site"), "toothseg_results": str(root / "models"), "toothseg_commit": "test"}
            with patch.object(worker, "_verify_runtime"), patch.object(worker, "_pip") as pip, patch.object(worker, "_download") as download:
                worker.install_toothseg(req)
                pip.assert_not_called()
                download.assert_not_called()

    @unittest.skipUnless(sys.platform == "win32", "Windows-specific unsupported kernels")
    def test_umamba_failure_is_reported_without_mutating_shared_packages(self):
        with tempfile.TemporaryDirectory() as tmp:
            req = {"runtime_root": tmp, "repos_root": tmp + "/repos", "site_packages": tmp + "/site", "umamba2_models": tmp + "/models", "umamba2_commit": "test", "engine": "UMAMBA2"}
            with patch.object(worker, "_github_snapshot"), patch.object(worker, "_pip") as pip:
                with self.assertRaisesRegex(RuntimeError, "Windows"):
                    worker.install_umamba2(req)
                pip.assert_not_called()

    def test_all_install_reports_partial_when_one_engine_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            req = {"runtime_root": tmp, "site_packages": tmp + "/site", "engine": "ALL"}
            request = Path(tmp) / "request.json"
            request.write_text(json.dumps(req))
            with patch.object(sys, "argv", ["installer", str(request)]), patch.object(worker, "install_totalseg"), patch.object(worker, "install_toothseg"), patch.object(worker, "install_umamba2", side_effect=RuntimeError("unsupported")):
                worker.main()
            status = json.loads((Path(tmp) / "install_status.json").read_text())
            self.assertEqual(status["phase"], "PARTIAL")
            self.assertFalse(status["running"])
            self.assertEqual(status["detail"]["engines"]["TOOTHSEG"]["status"], "READY")
            self.assertEqual(status["detail"]["engines"]["UMAMBA2"]["status"], "ERROR")

if __name__ == "__main__":
    unittest.main()
