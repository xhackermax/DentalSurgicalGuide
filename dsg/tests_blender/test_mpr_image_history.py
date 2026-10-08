"""Generated MPR rasters restore with the stage, including archived recovery."""
import bpy,sys,tempfile,os,gc
import numpy as np
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import dsg
dsg.register()
from dsg import workflow_history as h,dicom_module as dicom
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
    os.environ['DSG_HISTORY_ROOT']=td
    if not bpy.data.objects.get('Cube'):
        bpy.ops.mesh.primitive_cube_add();bpy.context.object.name='Cube'
    image=dicom._get_image('DICOM_Test_history',4,4)
    dicom._set_image_pixels(image,np.full((4,4),.2,np.float32))
    material=dicom._get_plane_material('MPR_history_material',image)
    bpy.data.objects['Cube'].data.materials.clear();bpy.data.objects['Cube'].data.materials.append(material)
    h.begin(bpy.context,'First slice');first=bpy.context.scene[h.STATE_KEY]
    dicom._set_image_pixels(image,np.full((4,4),.8,np.float32))
    h.commit(bpy.context,'Second slice');second=bpy.context.scene[h.STATE_KEY]
    bpy.ops.ed.undo_push(message='Second slice')
    assert h.undo_previous(bpy.context)=={'FINISHED'}
    def pixels():return np.asarray(bpy.data.images['DICOM_Test_history'].pixels[:]).reshape(4,4,4)[...,0]
    assert np.allclose(pixels(),.2,atol=.003),'Native undo kept the wrong MPR pixels'
    h.restore_checkpoint(bpy.context,second)
    assert np.allclose(pixels(),.8,atol=.003),'Archived recovery lost generated image data'
    h.restore_checkpoint(bpy.context,first)
    assert np.allclose(pixels(),.2,atol=.003)
    dicom.RUNTIME.volume=None;dicom.RUNTIME.semantic_labels=None;dicom.RUNTIME.segmentations.clear();h._ARRAY_CACHE.clear();gc.collect()
os.environ.pop('DSG_HISTORY_ROOT',None)
print('MPR_IMAGE_HISTORY_PASS',flush=True)
