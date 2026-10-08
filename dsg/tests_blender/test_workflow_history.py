"""Real native undo restores mesh identity, FDI and external semantic/mask state."""
import sys,tempfile,json,os
from pathlib import Path
import bpy,numpy as np
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import dsg
dsg.register()
from dsg import workflow_history as history,dicom_module as dicom,cbct_post_smoothing as post
with tempfile.TemporaryDirectory() as td:
    os.environ['DSG_HISTORY_ROOT']=td
    scene=bpy.context.scene;scene['history_test']=0
    dicom.RUNTIME.volume=np.zeros((5,5,5),np.int16);dicom.RUNTIME.dims_zyx=(5,5,5)
    dicom.RUNTIME.semantic_labels=np.ones((5,5,5),np.uint8)
    dicom.RUNTIME.semantic_model_kind='universal';dicom.RUNTIME.semantic_source_signature=dicom._semantic_source_signature()
    original_signature=dicom.RUNTIME.semantic_source_signature
    dicom.RUNTIME.segmentations={'TEETH':{'positive':{2,5},'negative':{9},'mask':np.ones((3,3,3),bool),'origin_zyx':(1,1,1),'stale':False}}
    history.begin(bpy.context,'Initial')
    first=scene[history.STATE_KEY]
    bpy.ops.ed.undo_push(message='Initial')
    scene['history_test']=1
    dicom.RUNTIME.semantic_labels[0,0,0]=9
    dicom.RUNTIME.semantic_source_signature='modified'
    dicom.RUNTIME.segmentations['TEETH']['positive'].add(7)
    dicom.RUNTIME.segmentations['TEETH']['mask'][1,1,1]=False
    history.commit(bpy.context,'Changed')
    second=scene[history.STATE_KEY]
    bpy.ops.ed.undo_push(message='Changed')
    assert first!=second and Path(first).is_file() and Path(second).is_file()
    bpy.ops.ed.undo()
    assert bpy.context.scene['history_test']==0
    assert dicom.RUNTIME.semantic_source_signature==original_signature
    assert dicom.RUNTIME.semantic_labels[0,0,0]==1
    assert dicom.RUNTIME.segmentations['TEETH']['positive']=={2,5}
    assert dicom.RUNTIME.segmentations['TEETH']['mask'][1,1,1]
    # A persisted stage remains restorable after the runtime cache is lost.
    dicom.RUNTIME.semantic_labels=None
    history.restore_runtime(bpy.context.scene,force=True)
    assert dicom.RUNTIME.semantic_labels[0,0,0]==1
    assert isinstance(dicom.RUNTIME.semantic_labels,np.memmap)
    assert bpy.context.preferences.edit.undo_steps==32
    count=len(list(Path(td).rglob('*.npy')))
    history.commit(bpy.context,'Same arrays')
    assert len(list(Path(td).rglob('*.npy')))==count,'Unchanged arrays duplicated'
    # Archive fallback restores the full Blender scene, not just external labels.
    history.restore_checkpoint(bpy.context,second)
    assert bpy.context.scene['history_test']==1
    assert dicom.RUNTIME.semantic_labels[0,0,0]==9
    assert dicom.RUNTIME.segmentations['TEETH']['positive']=={2,5,7}
    dicom.RUNTIME.volume=None;dicom.RUNTIME.semantic_labels=None;dicom.RUNTIME.segmentations.clear()
    history._ARRAY_CACHE.clear()
    import gc;gc.collect()
os.environ.pop('DSG_HISTORY_ROOT',None)
print('WORKFLOW_HISTORY_PASS',flush=True)
