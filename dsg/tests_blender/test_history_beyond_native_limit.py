import sys,tempfile,os,json
from pathlib import Path
import bpy
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import dsg
if not hasattr(bpy.types.Scene,'dsg_cbct_dental'):dsg.register()
from dsg import workflow_history as history
with tempfile.TemporaryDirectory() as td:
    os.environ['DSG_HISTORY_ROOT']=td
    scene=bpy.context.scene;scene.pop(history.STATE_KEY,None);scene.pop(history.PROJECT_KEY,None)
    scene['undo_counter']=0
    history.begin(bpy.context,'Base')
    for i in range(1,36):
        bpy.context.scene['undo_counter']=i
        history.commit(bpy.context,str(i));bpy.ops.ed.undo_push(message=str(i))
    archive_count=0
    for expected in range(34,-1,-1):
        assert history.undo_previous(bpy.context)=={'FINISHED'}
        assert bpy.context.scene['undo_counter']==expected,(expected,bpy.context.scene['undo_counter'])
        if history._ARCHIVE_MODE:archive_count+=1
    assert archive_count>0
    assert bpy.context.preferences.edit.undo_steps==32
    assert len(list(Path(td).rglob('*.blend')))==36
    print('HISTORY_35_STEPS_PASS',archive_count,flush=True)
os.environ.pop('DSG_HISTORY_ROOT',None)
