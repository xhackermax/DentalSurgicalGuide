import sys,unittest,tempfile,json
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from dsg.pipeline_core import ContractError,VolumeInput,Labelmap,ResultManifest,RunTrace

class ContractsTests(unittest.TestCase):
    def volume(self):return VolumeInput.parse(np.zeros((4,5,6),np.int16),np.ones(4),np.zeros(4),(4,5,6),(.2,.3,.4))
    def test_import_without_blender(self):self.assertNotIn('bpy',sys.modules)
    def test_valid_volume_keeps_array_identity(self):
        v=self.volume();self.assertEqual(v.data.shape,(4,5,6));self.assertEqual(v.units,'STORED_CALIBRATED')
    def test_dimensions_spacing_and_calibration_fail_at_input(self):
        for dims,spacing,slopes in [((4,5,7),(.2,.3,.4),np.ones(4)),((4,5,6),(.2,float('nan'),.4),np.ones(4)),((4,5,6),(.2,.3,.4),np.ones(3))]:
            with self.assertRaises(ContractError):VolumeInput.parse(np.zeros((4,5,6)),slopes,np.zeros(4),dims,spacing)
    def test_compatibility_labels_preserve_bones_and_fdi(self):
        v=self.volume();data=np.zeros(v.data.shape,np.uint8);data[0]=1;data[1]=32;data[2]=53;data[3]=54
        result=Labelmap.parse(data,v.dims,v.spacing_zyx,'FAKE')
        self.assertIs(result.data,data);self.assertEqual(result.fdis,frozenset({18,48}));self.assertEqual(result.counts[53],30)
    def test_empty_wrong_dtype_unknown_and_shape_fail(self):
        v=self.volume()
        for data in [np.zeros(v.dims,np.uint8),np.ones(v.dims,np.float32),np.full(v.dims,99,np.uint8),np.ones((1,2,3),np.uint8)]:
            with self.assertRaises(ContractError):Labelmap.parse(data,v.dims,v.spacing_zyx,'FAKE')
    def test_manifest_schema_and_run_match(self):
        valid={'schema_version':1,'run_id':'test-run','status':'OK','normalized_labels_path':'private.npy','labelmap_contract':{'dims_zyx':[4,5,6],'dtype':'uint8','labels':[1,53]}}
        self.assertEqual(ResultManifest.parse(valid,'test-run').payload,valid)
        for change in [{'schema_version':99},{'run_id':'another-run'},{'labelmap_contract':{}},{'status':'invalid'}]:
            with self.assertRaises(ContractError):ResultManifest.parse({**valid,**change},'test-run')
    def test_trace_error_fallback_and_privacy(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'diagnostic.json';trace=RunTrace(path,'test-run','9.10.11','TOTALSEG',{'dims_zyx':[4,5,6],'spacing_zyx':[.2,.3,.4]})
            trace.start('input');trace.start('engine');trace.fallback('gpu','cpu','CUDA runtime error')
            trace.fail(ContractError('labelmap','no produjo dientes',patient_name='SECRET',source_path='C:/patient/SECRET.dcm'))
            doc=json.loads(path.read_text());self.assertEqual(doc['status'],'ERROR');self.assertEqual(doc['stages'][-1]['status'],'ERROR')
            self.assertNotIn('SECRET',path.read_text());self.assertEqual(len(doc['fallbacks']),1)
    def test_trace_success_records_timing(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'diagnostic.json';trace=RunTrace(path,'test-run','9.10.11','FAKE',{})
            trace.start('input');trace.start('labelmap');trace.finish()
            doc=json.loads(path.read_text());self.assertEqual(doc['status'],'OK');self.assertTrue(all(s['duration_s']>=0 for s in doc['stages']))
if __name__=='__main__':unittest.main(verbosity=2)
