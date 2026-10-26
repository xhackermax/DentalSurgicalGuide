"""Simple arches must never be rebuilt using invented individual tooth labels."""
import sys
from pathlib import Path
from unittest.mock import patch
import bpy
sys.path.insert(0, sys.argv[sys.argv.index('--')+1])
import dsg
dsg.register()
from dsg.blender import segmentation_finish as finish
from dsg import cbct_post_smoothing as post, dicom_module as dicom
bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=16, radius=10)
obj=bpy.context.object
scene=bpy.context.scene
with patch.object(finish,'targets',return_value=[obj]), patch.object(finish,'in_scope',return_value=True), patch.object(dicom.RUNTIME.__class__,'is_loaded',return_value=True), patch.object(dicom,'get_cached_semantic_cbct_labels',return_value=object()), patch.object(post,'start',side_effect=lambda *a,**k: setattr(post,'_JOB',{})) as start:
    finish.start(bpy.context)
    assert start.call_args.args[1]=='VISUAL', 'Simple arches incorrectly use individual label reconstruction'
post._JOB=None
finish.rollback()
# No accepted surfaces must not consume the one-shot action.
finish.STATE.update(scene=scene,objects=[])
try:
    finish.complete({}, {'teeth':[{'status':'SKIPPED','fallback_reason':'sin cambio'}]})
except RuntimeError:
    pass
assert not scene.get(finish.DONE), 'Zero applied surfaces incorrectly marked complete'
finish.STATE.clear()
print('SIMPLE_FINISH_ROUTING_PASS')


# Run the real external worker on an irregular closed simple arch surrogate.
import time, json, numpy as np
obj['DSG_cbct_spacing_zyx_mm']=(.2,.2,.2)
for vertex in obj.data.vertices:
    vertex.co *= 1.0 + .012*np.sin(vertex.index*2.17)
obj.data.update()
original=obj.data
before=post.mesh_hash(original)
finish.reset(scene)
with patch.object(finish,'targets',return_value=[obj]), patch.object(finish,'in_scope',return_value=True), patch.object(dicom.RUNTIME.__class__,'is_loaded',return_value=True), patch.object(dicom,'get_cached_semantic_cbct_labels',return_value=object()):
    finish.start(bpy.context)
    deadline=time.monotonic()+90
    while post.busy() and time.monotonic()<deadline:
        post._poll()
        time.sleep(.1)
assert not post.busy(), 'Worker timed out'
assert scene.get(finish.DONE), str(scene.get(post.STATUS))
assert post.mesh_hash(obj.data)!=before, 'Geometry was not modified'
assert post.mesh_hash(post.source_mesh(obj))==before, 'Original geometry was lost'
v,f=post.mesh_arrays(original)
w,faces=post.mesh_arrays(obj.data)
assert np.array_equal(f,faces)
distance=np.linalg.norm(w-v,axis=1)
assert distance.max()<=.25001
print('SIMPLE_FINISH_REAL_WORKER_PASS',json.dumps({'vertices':len(v),'max_displacement_mm':float(distance.max()),'mean_displacement_mm':float(distance.mean()),'summary':scene[finish.SUMMARY]}))
# Individual segmented teeth retain their anatomical reconstruction route.
finish.reset(scene)
obj['DSG_tooth_instance']=True
obj['DSG_universal_label']=8
with patch.object(finish,'targets',return_value=[obj]), patch.object(finish,'in_scope',return_value=True), patch.object(dicom.RUNTIME.__class__,'is_loaded',return_value=True), patch.object(dicom,'get_cached_semantic_cbct_labels',return_value=object()), patch.object(post,'start',side_effect=lambda *a,**k: setattr(post,'_JOB',{})) as start:
    finish.start(bpy.context)
    assert start.call_args.args[1]=='ORGANIC'
post._JOB=None
finish.rollback()
print('INDIVIDUAL_TEETH_ROUTE_PRESERVED_PASS')

# Real SIMPLE metadata selects model-grid reconstruction, without tooth identity.
finish.reset(scene)
obj.pop('DSG_tooth_instance', None)
obj.pop('DSG_universal_label', None)
obj['DSG_simple_route']=True
obj['DSG_simple_arch']='UPPER'
with patch.object(finish,'targets',return_value=[obj]), patch.object(finish,'in_scope',return_value=True), patch.object(dicom.RUNTIME.__class__,'is_loaded',return_value=True), patch.object(dicom,'get_cached_semantic_cbct_labels',return_value=object()), patch.object(post,'start',side_effect=lambda *a,**k: setattr(post,'_JOB',{})) as start:
    finish.start(bpy.context)
    assert start.call_args.args[1]=='ORGANIC_ARCHES'
    assert obj.data == finish.STATE['objects'][0]['reference'], 'Upgrade used the previous visual finish as its source'
post._JOB=None
finish.rollback()
print('SIMPLE_SHARED_ITK_ROUTING_PASS')

# Old visual-only completion is upgradeable; missing source is an explicit failure.
scene[finish.DONE]=True
scene.pop(finish.METHOD,None)
with patch.object(finish,'targets',return_value=[obj]):
    assert not finish.done(bpy.context)
with patch.object(finish,'targets',return_value=[obj]), patch.object(finish,'in_scope',return_value=True), patch.object(dicom.RUNTIME.__class__,'is_loaded',return_value=True), patch.object(dicom,'get_cached_semantic_cbct_labels',return_value=None), patch.object(post,'start') as worker:
    try:
        finish.start(bpy.context)
        raise AssertionError('Simple arch silently fell back to visual smoothing')
    except RuntimeError as error:
        assert 'máscara original' in str(error)
    worker.assert_not_called()
assert not finish.STATE
print('SIMPLE_UPGRADE_AND_MISSING_MASK_PASS')
