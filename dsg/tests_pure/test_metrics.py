import unittest,tempfile,importlib.util
from pathlib import Path
root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('metrics',root/'tools/metrics.py');metrics=importlib.util.module_from_spec(spec);spec.loader.exec_module(metrics)
class MetricsTests(unittest.TestCase):
    def test_counts_nested_silent_catches_and_detects_regression(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'source.py';p.write_text('try:\n x=1\nexcept Exception:\n pass\n')
            before=metrics.scan(td);self.assertEqual(before['silent_except'],1)
            p.write_text(p.read_text()+'\ntry:\n x=2\nexcept Exception:\n pass\n')
            self.assertIn('silent_except',metrics.compare(metrics.scan(td),before))
    def test_missing_and_test_files_are_not_production_metrics(self):
        with tempfile.TemporaryDirectory() as td:
            test=Path(td)/'tests_pure/test.py';test.parent.mkdir();test.write_text('try:\n x=1\nexcept Exception:\n pass\n')
            self.assertEqual(metrics.scan(td)['broad_except'],0)
if __name__=='__main__':unittest.main(verbosity=2)
