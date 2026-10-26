"""Diámetro/Longitud resize the planned implant in place, platform fixed."""
import sys
import bpy
from mathutils import Matrix, Vector

sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import dsg
dsg.register()
from dsg import guide_module as g

try:
    scene = bpy.context.scene
    props = scene.dsg_props
    for obj in list(scene.objects):
        bpy.data.objects.remove(obj,do_unlink=True)
    mesh = g.make_embedded_implant_mesh(g.IMPLANT_PREFIX+'Resize_Mesh',4.7,10.0)
    implant = bpy.data.objects.new(g.IMPLANT_PREFIX+'Resize',mesh)
    scene.collection.objects.link(implant)
    implant.matrix_world = Matrix.Translation((1,2,3)) @ Matrix.Rotation(.4,4,'X')
    implant['DSG_implant_diameter'], implant['DSG_implant_length'] = 4.7, 10.0
    bpy.context.view_layer.objects.active = implant
    bpy.context.view_layer.update()
    platform = g.get_implant_platform_center_world(props,implant).copy()
    props.current_step = g.STEP_IMPLANT
    props.implant_length = 13.0
    props.implant_diameter = 3.5
    bpy.context.view_layer.update()
    assert implant.name in bpy.data.objects, 'Resize must not delete the implant'
    assert abs(implant['DSG_implant_diameter']-3.5) < 1e-6 and abs(implant['DSG_implant_length']-13.0) < 1e-6
    xs = [v.co.x for v in implant.data.vertices]
    assert abs((max(xs)-min(xs))-3.5) < 1e-3
    assert (g.get_implant_platform_center_world(props,implant)-platform).length < 1e-4, 'Platform moved'
    print('IMPLANT_RESIZE_PASS: in-place diameter/length, platform fixed',flush=True)
finally:
    dsg.unregister()
