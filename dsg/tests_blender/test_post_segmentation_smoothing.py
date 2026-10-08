"""Exercise mesh replacement/restore and raw ICP across a topology change."""
import sys,json,tempfile
from pathlib import Path
import bpy,numpy as np
parent=Path(sys.argv[sys.argv.index('--')+1]);sys.path.insert(0,str(parent))
import dsg
if not hasattr(bpy.types.Scene,'dsg_cbct_dental'):dsg.register()
from dsg import cbct_post_smoothing as post
from dsg import cbct_dental_module as dental,alignment_module as alignment
mesh=bpy.data.meshes.new('PostSmoothSource')
mesh.from_pydata([(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)],[],[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)])
obj=bpy.data.objects.new('PostSmoothTooth',mesh);bpy.context.scene.collection.objects.link(obj)
obj['DSG_tooth_instance']=True;obj['DSG_fdi_number']=11;obj['DSG_universal_label']=8
raw=alignment._mesh_graph_from_objects([obj]).points.copy();snapshot=post.snapshot_object(obj)
with tempfile.TemporaryDirectory() as td:
    root=Path(td);v=np.array([(-.9,-.9,-.9),(.9,-.9,-.9),(.9,.9,-.9),(-.9,.9,-.9),(-.9,-.9,.9),(.9,-.9,.9),(.9,.9,.9),(-.9,.9,.9)],np.float32)
    f=np.array([(0,3,2),(0,2,1),(4,5,6),(4,6,7),(0,1,5),(0,5,4),(1,2,6),(1,6,5),(2,3,7),(2,7,6),(3,0,4),(3,4,7)],np.int32)
    np.save(root/'v.npy',v);np.save(root/'f.npy',f)
    report={'label':8,'status':'READY','vertices_path':str(root/'v.npy'),'faces_path':str(root/'f.npy'),'method':'SURFACE_NETS_BOX','occupancy_consistency':1.0}
    assert post.apply_result(bpy.context.scene,[snapshot],{'teeth':[report]})['applied']==1
    assert obj.data!=mesh and obj.get(post.ORIGINAL_MESH)==mesh
    np.testing.assert_array_equal(alignment._mesh_graph_from_objects([obj]).points,raw)
    assert post.restore_originals(bpy.context.scene)==1 and obj.data==mesh
    assert post.apply_cached(bpy.context.scene,'VISUAL')==0, 'Cache from another mode was applied'
    assert obj.data==mesh
    obj['DSG_post_smooth_mode']='VISUAL'  # Leftover cache from a previous batch.
    assert post.apply_cached(bpy.context.scene,'VISUAL')==0, 'Partial cache from an older batch was applied'
    obj['DSG_post_smooth_mode']='CLEAN'
    assert post.apply_cached(bpy.context.scene)==1 and obj.data!=mesh
    post.restore_originals(bpy.context.scene)
    # A worker result must not overwrite a mesh edited while it was running.
    obj.data.vertices[0].co.x-=.2
    try:post.apply_result(bpy.context.scene,[snapshot],{'teeth':[report]})
    except RuntimeError:pass
    else:raise AssertionError('Stale worker accepted an edited tooth')
    assert obj.data==mesh
    obj.data.vertices[0].co.x+=.2
    assert post.apply_cached(bpy.context.scene)==1
    saved=root/'post_smoothing_test.blend';bpy.ops.wm.save_as_mainfile(filepath=str(saved))
    bpy.ops.wm.open_mainfile(filepath=str(saved))
    reloaded=bpy.data.objects['PostSmoothTooth'];original=reloaded.get(post.ORIGINAL_MESH)
    assert isinstance(original,bpy.types.Mesh) and reloaded.data!=original
    np.testing.assert_array_equal(alignment._mesh_graph_from_objects([reloaded]).points,raw)
    assert post.restore_originals(bpy.context.scene)==1 and reloaded.data==original
assert hasattr(bpy.ops.dsg,'cbct_post_smooth_teeth')
assert bpy.context.scene.dsg_cbct_dental.surface_finish_mode=='VISUAL'
print('POST_SEGMENTATION_SMOOTHING_PASS',flush=True)
