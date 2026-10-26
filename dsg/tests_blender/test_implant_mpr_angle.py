"""Continuous per-plane MPR angle preserves implant pose and long-axis section."""
import math,sys
from unittest.mock import patch
import bpy
from mathutils import Vector
sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import dsg
dsg.register()
from dsg import guide_module as g
from dsg.blender import implant_plane as m,safety_volume as safety
try:
    safety.unregister()
    m.register()
    implants=[];planes=[]
    with patch.object(m,'refresh',return_value=True):
        for index in range(2):
            bpy.ops.mesh.primitive_cube_add(size=2,location=(index*10.,0,0))
            obj=bpy.context.object;obj.name=g.IMPLANT_PREFIX+f'AngleTest{index}';obj.rotation_euler=(.2,.3,.4)
            implants.append(obj);planes.append(m.create(bpy.context,obj))
    before=[obj.matrix_world.copy() for obj in implants]
    initial=planes[0].matrix_basis.copy();other=planes[1].matrix_basis.copy()
    for degrees in (-180,-45,0,37,90,180):
        planes[0].dsg_implant_mpr_angle=math.radians(degrees)
        bpy.context.view_layer.update()
        axis=(implants[0].matrix_world.to_3x3()@Vector((0,0,1))).normalized()
        plane_axis=(planes[0].matrix_world.to_3x3()@Vector((0,1,0))).normalized()
        assert abs(axis.dot(plane_axis))>.99999,'Angle removed long axis from MPR'
        assert (planes[0].matrix_world.translation-implants[0].matrix_world.translation).length<1e-5
        assert all(obj.matrix_world==matrix for obj,matrix in zip(implants,before)),'Angle moved implant'
        assert planes[1].matrix_basis==other,'Angle changed another implant plane'
    planes[0].dsg_implant_mpr_angle=0.
    assert all(abs(planes[0].matrix_basis[r][c]-initial[r][c])<1e-6 for r in range(4) for c in range(4))
    planes[0].dsg_implant_mpr_angle=math.radians(37)
    assert planes[0].name in m.STATE['pending'],'Angle did not queue radiographic reslice'
    assert bpy.app.timers.is_registered(m._refresh_pending)
    import tempfile
    from pathlib import Path
    name=planes[0].name
    with tempfile.TemporaryDirectory(prefix='DSG_MPR_ANGLE_TEST_') as folder:
        file=Path(folder)/'angle.blend'
        bpy.ops.wm.save_as_mainfile(filepath=str(file))
        bpy.ops.wm.open_mainfile(filepath=str(file))
        restored=bpy.data.objects[name]
        assert abs(restored.dsg_implant_mpr_angle-math.radians(37))<1e-6,'Saved MPR angle was lost'
    print('IMPLANT_MPR_ANGLE_PASS: continuous +/-180deg, independent planes, implant pose fixed, axis in section, reset and queued image refresh',flush=True)
finally:dsg.unregister()
