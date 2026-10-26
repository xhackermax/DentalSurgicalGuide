"""Real Blender curve sweep, 2mm halo and full-body collision protection."""
import sys
from pathlib import Path
import numpy as np
import bpy
from mathutils import Vector, Matrix

sys.path.insert(0, sys.argv[sys.argv.index('--')+1])
import dsg
dsg.register()
from dsg import core, guide_module as g, cbct_dental_module as dental, dicom_module
from dsg.blender import safety_volume as safety

try:
    safety.unregister()
    scene = bpy.context.scene
    scene.dsg_suite_settings.workflow_route = core.ROUTE_SIMPLE
    scene[core.SUITE_STAGE_KEY] = core.STAGE_GUIDE
    scene.dsg_props.current_step = g.STEP_IMPLANT
    for obj in list(scene.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    angles = np.linspace(0,2*np.pi,120,endpoint=False)
    points = [Vector((10*np.cos(a),7*np.sin(a),.2*np.sin(3*a))) for a in angles]
    anchors = [list(points[i]) for i in (0,17,43,78)]
    frame = g.build_surface_poly_tube_mesh(bpy.context,points,.5, name='Test organic frame',anchors=anchors)
    assert frame['DSG_frame_visible_sweep'] == 'ADAPTIVE_CENTRIPETAL_CATMULL_BEZIER_V2'
    assert frame['DSG_frame_uniform_radius_mm'] == .5
    assert frame['DSG_frame_curve_max_deviation_mm'] <= .04
    report = g.get_mesh_solid_report(frame)
    assert report.get('solid'), report
    # Mesh loops retain a full circular section at every Bezier control.
    coords = np.asarray([tuple(v.co) for v in frame.data.vertices])
    for a in anchors:
        distances = np.linalg.norm(coords-np.asarray(a),axis=1)
        assert np.sum(abs(distances-.5) < .001) >= 8, 'Tube radius was thinned at a user anchor'
    # Exercise the real surface-route adapter, rather than only a prepared loop.
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=10)
    surface = bpy.context.object
    clicked = [Vector((8*np.cos(a),8*np.sin(a),6)) for a in (0,1.3,3.,4.8)]
    route, stats = g.build_surface_intrinsic_frame_path(bpy.context,surface,clicked,Vector((0,0,1)),frame_radius_mm=.5)
    assert route and not stats.get('euclidean_fallback'), stats
    routed = g.build_surface_poly_tube_mesh(bpy.context,route,.5,name='Surface organic frame',anchors=stats['resolved_anchor_points'])
    assert g.get_mesh_solid_report(routed).get('solid')
    implant = bpy.data.objects.new(g.IMPLANT_PREFIX+'Test', g.make_cylinder_mesh('Implant fixture',1,10,verts=32))
    scene.collection.objects.link(implant)
    scene.dsg_props.implant_obj = implant
    halo = g.create_implant_safety_halo(bpy.context,scene.dsg_props,implant)
    volume = bpy.data.objects[halo['DSG_hidden_safety_volume_name']]
    assert abs(max(v.co.z for v in halo.data.vertices)-min(v.co.z for v in halo.data.vertices)-2) < 1e-6
    assert volume['height_mm'] >= 10 and volume.hide_get() and volume.hide_render
    assert (halo.matrix_world.translation-g.get_implant_platform_center_world(scene.dsg_props,implant)).length < 1e-6
    bpy.ops.mesh.primitive_cube_add(size=.3,location=(1.4,0,-3))
    tooth = bpy.context.object
    tooth.name = dental.TOOTH_OBJECT_PREFIX+'12'
    tooth['DSG_tooth_instance'], tooth['DSG_fdi_number'] = True,12
    bpy.context.view_layer.update()
    assert tooth.name in safety.contacts(bpy.context,implant), 'Hidden axial section missed a segmented tooth'
    tooth.location.x = 20
    bpy.context.view_layer.update()
    assert not safety.contacts(bpy.context,implant)
    # Nerve contact occurs far below the short visible halo.
    bpy.ops.mesh.primitive_cube_add(size=.3,location=(1.4,0,-4))
    nerve = bpy.context.object
    nerve.name = dicom_module.NAME_DICOM_MANDIBULAR_CANAL
    bpy.context.view_layer.update()
    assert nerve.name in safety.contacts(bpy.context,implant)
    nerve.location.x = 20
    bpy.context.view_layer.update()
    # A second real implant is an obstacle too, even when its axis is tilted.
    second = bpy.data.objects.new(g.IMPLANT_PREFIX+'Other',g.make_cylinder_mesh('Other mesh',1,8,verts=32))
    scene.collection.objects.link(second)
    second.location = (2,0,0)
    second.rotation_euler.y = .2
    bpy.context.view_layer.update()
    assert second.name in safety.contacts(bpy.context,implant)
    bpy.data.objects.remove(second,do_unlink=True)
    scene.dsg_props.model_obj = frame
    safety.remember(implant)
    safe_pose = implant.matrix_world.copy()
    implant.location.x = 20
    bpy.context.view_layer.update()
    scene.dsg_props.current_step = g.STEP_IMPLANT
    safety.update(scene,bpy.context.evaluated_depsgraph_get())
    assert implant.location.x == 20, 'Editing pose was unexpectedly rolled back'
    bpy.context.view_layer.update()
    controller = bpy.data.objects.new('Test emergence controller',None)
    scene.collection.objects.link(controller)
    implant.parent = controller
    implant.matrix_world = safe_pose
    safety.remember(implant)
    controller.location.x = 20
    bpy.context.view_layer.update()
    safety.update(scene,bpy.context.evaluated_depsgraph_get())
    assert controller.location.x == 20, 'Emergence controller movement was rolled back'
    controller.location.x = 0
    implant.matrix_world = safe_pose
    bpy.context.view_layer.update()
    class Reporter:
        def report(self, level, message):
            self.message = message
    reporter = Reporter()
    nerve.location.x = 1.4
    bpy.context.view_layer.update()
    assert not safety.gate(bpy.context,reporter) and nerve.name in reporter.message
    safety.register()
    assert safety.update in bpy.app.handlers.depsgraph_update_post
    safety.unregister()
    assert safety.update not in bpy.app.handlers.depsgraph_update_post
    print('ORGANIC_FRAME_SAFETY_PASS: real sweep, manifold, full radius at anchors, 2mm halo, hidden tooth/nerve contacts, editable poses and confirmation gate',flush=True)
finally:
    dsg.unregister()
