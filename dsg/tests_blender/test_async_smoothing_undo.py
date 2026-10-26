import sys,tempfile,json,os,time
from pathlib import Path
import bpy,numpy as np
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import dsg
if not hasattr(bpy.types.Scene,'dsg_cbct_dental'):dsg.register()
from dsg import workflow_history as history,cbct_post_smoothing as post,alignment_module as alignment
class FinishedWorker:
    returncode=0
    def poll(self):return 0
class RunningWorker:
    returncode=None
    def poll(self):return self.returncode
    def terminate(self):self.returncode=-15
    def wait(self,timeout):return self.returncode
with tempfile.TemporaryDirectory() as td:
    os.environ['DSG_HISTORY_ROOT']=td
    mesh=bpy.data.meshes.new('UndoToothMesh')
    mesh.from_pydata([(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)],[],[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)])
    obj=bpy.data.objects.new('UndoTooth',mesh);bpy.context.scene.collection.objects.link(obj)
    obj['DSG_tooth_instance']=True;obj['DSG_universal_label']=8;obj['DSG_fdi_number']=11
    bpy.context.preferences.edit.use_global_undo=True
    bpy.ops.ed.undo_push(message='Before async smoothing')
    source_hash=post.mesh_hash(mesh);raw=alignment._mesh_graph_from_objects([obj]).points.copy()
    history.begin(bpy.context,'Suavizar dientes');snapshot=post.snapshot_object(obj)
    root=Path(td);v,f=post.mesh_arrays(mesh);np.save(root/'v.npy',v*.95);np.save(root/'f.npy',f)
    result={'status':'OK','mode':'VISUAL','teeth':[{'label':8,'fdi':11,'status':'READY','vertices_path':str(root/'v.npy'),'faces_path':str(root/'f.npy')}]}
    (root/'result.json').write_text(json.dumps(result))
    post._JOB={'scene':bpy.context.scene,'snapshots':[snapshot],'root':td,'log':None,'started':time.monotonic(),'process':FinishedWorker(),'signature':''}
    assert post._poll() is None and post.active(bpy.context.scene)
    assert history.undo_previous(bpy.context)=={'FINISHED'}
    obj=bpy.data.objects['UndoTooth']
    assert post.mesh_hash(obj.data)==source_hash and not post.active(bpy.context.scene)
    np.testing.assert_array_equal(alignment._mesh_graph_from_objects([obj]).points,raw)
    assert obj['DSG_fdi_number']==11
    # Undo cannot leave a pending process holding invalidated Blender ID pointers.
    process=RunningWorker()
    post._JOB={'scene':bpy.context.scene,'snapshots':[post.snapshot_object(obj)],'root':td,'log':None,'started':time.monotonic(),'process':process,'signature':''}
    bpy.context.scene['pending']=True;bpy.ops.ed.undo_push(message='Pending')
    history.undo_previous(bpy.context)
    assert not post.busy() and process.returncode==-15
    assert post.mesh_hash(bpy.data.objects['UndoTooth'].data)==source_hash
os.environ.pop('DSG_HISTORY_ROOT',None)
print('ASYNC_SMOOTHING_UNDO_PASS',flush=True)
