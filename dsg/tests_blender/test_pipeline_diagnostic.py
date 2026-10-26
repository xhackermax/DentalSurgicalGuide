import bpy,sys,json,tempfile,gc
from types import SimpleNamespace
from pathlib import Path
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import dsg
dsg.register()
from dsg import cbct_pipeline_client as client
from dsg.pipeline_core import RunTrace
with tempfile.TemporaryDirectory() as td:
    path=Path(td)/'diagnostic.json'
    trace=RunTrace(path,'test-run',dsg.DSG_VERSION_STR,'FAKE',{'dims_zyx':[8,8,8],'spacing_zyx':[.3,.3,.3]})
    trace.start('input');trace.finish()
    original=client._JOB.copy()
    client._JOB.update(diagnostic_path=str(path),run_id='test-run')
    # Background Blender has no OS clipboard. Exercise the real registered
    # operator method with a buffer; foreground verification covers OS clipboard.
    wm=SimpleNamespace(clipboard='')
    operator=SimpleNamespace(report=lambda level,message:None)
    assert dsg.cbct_dental_module.DSG_OT_CopyPipelineDiagnostic.is_registered
    assert dsg.cbct_dental_module.DSG_OT_CopyPipelineDiagnostic.execute(operator,SimpleNamespace(window_manager=wm))=={'FINISHED'}
    copied=json.loads(wm.clipboard)
    assert copied['run_id']=='test-run' and copied['status']=='OK'
    assert td not in wm.clipboard
    client.cleanup_artifacts()
    assert json.loads(client.diagnostic_text())['status']=='OK','Cleanup removed the run record'
    client._JOB.clear();client._JOB.update(original)
print('PIPELINE_DIAGNOSTIC_PASS',flush=True)
