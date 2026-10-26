"""Transient Windows reader locks must never cancel geometric generation."""
import importlib.util,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('status_worker',Path(__file__).resolve().parents[1]/'generative_frame_worker.py')
worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)

class WorkerStatusTests(unittest.TestCase):
 def test_progress_recovers_after_transient_lock(self):
  with tempfile.TemporaryDirectory() as folder:
   target=Path(folder)/'progress.json';original=Path.replace;calls=[]
   def replace(path,dest):
    calls.append(1)
    if len(calls)<3:raise PermissionError('reader temporarily owns file')
    return original(path,dest)
   with patch.object(Path,'replace',replace),patch.object(worker.time,'sleep'):
    self.assertTrue(worker.write_json_atomic(target,{'text':'avance'},best_effort=True))
   self.assertEqual(len(calls),3)
   self.assertEqual(json.loads(target.read_text(encoding='utf-8')),{'text':'avance'})
 def test_progress_lock_does_not_abort_calculation_or_destroy_old_status(self):
  with tempfile.TemporaryDirectory() as folder:
   target=Path(folder)/'progress.json';target.write_text('{"text":"anterior"}',encoding='utf-8')
   with patch.object(Path,'replace',side_effect=PermissionError('locked')),patch.object(worker.time,'sleep'):
    self.assertFalse(worker.write_json_atomic(target,{'text':'siguiente'},best_effort=True))
   self.assertEqual(json.loads(target.read_text(encoding='utf-8')),{'text':'anterior'})
   self.assertTrue(worker.write_json_atomic(target,{'text':'terminado'},best_effort=True))
 def test_result_write_failure_remains_an_error(self):
  with tempfile.TemporaryDirectory() as folder:
   with patch.object(Path,'replace',side_effect=PermissionError('locked')),patch.object(worker.time,'sleep'):
    with self.assertRaises(PermissionError):worker.write_json_atomic(Path(folder)/'result.json',{'ok':True})
 @unittest.skipUnless(sys.platform=='win32','Windows file sharing semantics')
 def test_actual_windows_reader_lock(self):
  import ctypes
  from ctypes import wintypes
  kernel=ctypes.WinDLL('kernel32',use_last_error=True)
  kernel.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
  kernel.CreateFileW.restype=wintypes.HANDLE
  kernel.CloseHandle.argtypes=[wintypes.HANDLE]
  with tempfile.TemporaryDirectory() as folder:
   target=Path(folder)/'progress.json';target.write_text('{}',encoding='utf-8')
   handle=kernel.CreateFileW(str(target),0x80000000,1|2,None,3,0x80,None)
   self.assertNotEqual(handle,ctypes.c_void_p(-1).value)
   try:
    with patch.object(worker.time,'sleep'):
     self.assertFalse(worker.write_json_atomic(target,{'text':'blocked'},best_effort=True))
   finally:kernel.CloseHandle(handle)
   self.assertTrue(worker.write_json_atomic(target,{'text':'ready'},best_effort=True))
   self.assertEqual(json.loads(target.read_text(encoding='utf-8')),{'text':'ready'})

if __name__=='__main__':unittest.main()
