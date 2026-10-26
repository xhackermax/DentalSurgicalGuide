import sys,json,tempfile,importlib.util,types,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root.parent))
from dsg.pipeline_core import ContractError
spec=importlib.util.spec_from_file_location('cbct_worker_under_test',root/'cbct_pipeline_worker.py')
worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)

class WorkerTraceTests(unittest.TestCase):
    def test_fake_engine_success_error_and_schema_failure(self):
        for bad in ('valid','empty','schema'):
            with self.subTest(bad=bad),tempfile.TemporaryDirectory() as td:
                job=Path(td);np.save(job/'volume.npy',np.zeros((8,8,8),np.int16));np.save(job/'slopes.npy',np.ones(8));np.save(job/'intercepts.npy',np.zeros(8))
                req={'schema_version':1 if bad!='schema' else 99,'run_id':'test-run','job_dir':td,'addon_dir':str(root),'diagnostic_path':str(job/'trace.json'),
                     'engine':'TOTALSEG','volume_path':str(job/'volume.npy'),'slopes_path':str(job/'slopes.npy'),'intercepts_path':str(job/'intercepts.npy'),
                     'dims_zyx':[8,8,8],'spacing_zyx':[.3,.3,.3],'source_signature':'PRIVATE_PATIENT_SIGNATURE','engine_site_paths':[]}
                request=job/'request.json';request.write_text(json.dumps(req))
                labels=np.zeros((8,8,8),np.uint8)
                if bad=='valid':labels[1:3,1:3,1:3]=1;labels[5:7,5:7,5:7]=9
                fake_nib=types.ModuleType('nibabel');fake_nib.Nifti1Image=lambda data,affine:types.SimpleNamespace(shape=data.shape);fake_nib.save=lambda image,path:None
                fake_torch=types.ModuleType('torch');fake_torch.set_num_threads=lambda n:None;fake_torch.cuda=types.SimpleNamespace(is_available=lambda:False)
                fake_tasks=types.ModuleType('dsg.cbct_pipeline_tasks')
                fake_tasks.run_teeth_task=lambda req,status:{'prepared_meshes':{'18':{'fake':True},'21':{'fake':True}},'elapsed_s':.1}
                with patch.dict(sys.modules,{'nibabel':fake_nib,'torch':fake_torch,'dsg.cbct_pipeline_tasks':fake_tasks}),patch.object(worker,'infer_totalseg',return_value=(labels,{'capabilities':['TEETH'],'inference_s':.01})),patch.object(sys,'argv',['worker',str(request)]):
                    if bad=='valid':worker.run_request()
                    else:
                        with self.assertRaises(ContractError):worker.run_request()
                diagnostic=json.loads((job/'trace.json').read_text())
                self.assertNotIn('PRIVATE_PATIENT_SIGNATURE',(job/'trace.json').read_text())
                self.assertNotIn(td,(job/'trace.json').read_text())
                if bad=='valid':
                    self.assertEqual(diagnostic['status'],'OK')
                    manifest=json.loads((job/'manifest.json').read_text());self.assertEqual(manifest['schema_version'],1);self.assertEqual(manifest['labelmap_contract']['fdis'],[18,21])
                else:self.assertEqual(diagnostic['status'],'ERROR')
    def test_totalseg_translation_rejects_negative_ids(self):
        with self.assertRaises(RuntimeError):worker._translate_totalseg(np,np.array([[[-1]]],np.int16),{1:'tooth_fdi11'})
    def test_orientation_failure_is_typed(self):
        with self.assertRaises(ContractError):worker._make_affine(np,(.2,.2,.2),np.zeros((3,3)),(0,0,0))
    def test_translation_preserves_valid_teeth_jaws_and_counts(self):
        raw=np.array([[[1,2],[3,0]]],np.uint8)
        labels,counts=worker._translate_totalseg(np,raw,{1:'upper_tooth_fdi11',2:'lower_jawbone',3:'upper_jawbone'})
        np.testing.assert_array_equal(labels,np.array([[[8,53],[54,0]]],np.uint8))
        self.assertEqual(counts,{'upper_tooth_fdi11':1,'lower_jawbone':1,'upper_jawbone':1})
if __name__=='__main__':unittest.main(verbosity=2)
