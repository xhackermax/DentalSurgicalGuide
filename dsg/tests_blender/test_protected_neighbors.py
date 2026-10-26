"""Extraction roles, chosen root visibility, preserved nerves and hidden checks."""
import sys
from unittest.mock import patch
import bpy

sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import dsg
dsg.register()
from dsg import core,guide_module as g,cbct_dental_module as dental,dicom_module as dicom
from dsg.blender import protected_neighbors as n, safety_volume as safety

try:
    safety.unregister()
    scene = bpy.context.scene
    scene.dsg_suite_settings.workflow_route = 'IMMEDIATE'
    scene[core.SUITE_STAGE_KEY] = core.STAGE_GUIDE
    scene[core.IMMEDIATE_FDIS_KEY] = '[36]'
    scene['DSG_active_arch'] = 'MANDIBLE'
    for obj in list(scene.objects):
        bpy.data.objects.remove(obj,do_unlink=True)
    bpy.ops.mesh.primitive_cube_add(size=10)
    scene.dsg_props.model_obj = bpy.context.object
    teeth = {}
    for fdi,x in [(35,1.4),(36,0),(37,20)]:
        bpy.ops.mesh.primitive_cube_add(size=.3,location=(x,0,-3))
        obj = bpy.context.object
        obj.name = dental.TOOTH_OBJECT_PREFIX+str(fdi)
        obj['DSG_tooth_instance'] = True
        obj['DSG_fdi_number'] = fdi
        teeth[fdi] = obj
    nerves = []
    for suffix,x in [('Left',20),('Right',30)]:
        bpy.ops.mesh.primitive_cube_add(size=.3,location=(x,0,-4))
        obj = bpy.context.object
        obj.name = dicom.NAME_DICOM_MANDIBULAR_CANAL+'_'+suffix
        obj.hide_set(True)
        nerves.append(obj)
    implant = bpy.data.objects.new(g.IMPLANT_PREFIX+'NeighborTest',g.make_cylinder_mesh('Implant',1,10,verts=32))
    scene.collection.objects.link(implant)
    implant['DSG_target_fdi'] = 36
    scene.dsg_props.implant_obj = implant
    with patch.object(g,'_workflow_requirement_report',side_effect=lambda context,step,scene=None:{'ok':True,'target':step}):
        scene.dsg_props.current_step = g.STEP_IMPLANT
        n.sync(bpy.context)
        assert not teeth[36].hide_get(), 'Tooth to extract must be visible before the virtual extraction'
        from dsg.blender import virtual_extraction as ve
        scene[ve.DONE] = '[36]'
        assert n.needs_sync(bpy.context)
        n.sync(bpy.context)
        assert not n.needs_sync(bpy.context), 'sync is not idempotent (redraw loop risk)'
        assert n.kept(scene) == set(), 'Neighbours must not appear until the clinician chooses them'
        assert teeth[35].hide_get() and teeth[37].hide_get()
        assert bpy.ops.dsg.all_protected_neighbors() == {'FINISHED'}
        assert n.kept(scene) == {35,37}
        assert not teeth[35].hide_get() and not teeth[37].hide_get()
        assert teeth[35].show_in_front and teeth[37].show_in_front
        assert teeth[36].hide_get() and teeth[36]['DSG_neighbor_role'] == 'BOOLEAN_EXTRACTION'
        assert all(not obj.hide_get() for obj in nerves)
        assert all(obj.show_in_front for obj in nerves)
        assert bpy.ops.dsg.toggle_protected_neighbor(fdi=35) == {'FINISHED'}
        assert n.kept(scene) == {37} and teeth[35].hide_get()
        assert teeth[35] in safety.obstacles(scene,implant), 'Hidden root lost its safety protection'
        assert teeth[36] not in safety.obstacles(scene,implant), 'Extraction target incorrectly treated as conserved root'
        assert all(obj in safety.obstacles(scene,implant) for obj in nerves)
        bpy.context.view_layer.update()
        assert teeth[35].name in safety.contacts(bpy.context,implant), 'Invisible neighbouring root was not checked'
        assert bpy.ops.dsg.all_protected_neighbors() == {'FINISHED'}
        assert not teeth[35].hide_get()
        assert bpy.ops.dsg.clear_protected_neighbors() == {'FINISHED'}
        assert n.kept(scene) == set() and teeth[35].hide_get() and teeth[37].hide_get()
        assert teeth[35] in safety.obstacles(scene,implant), 'QUITAR DIENTES VECINOS disabled the safety check'
        try:
            bpy.ops.dsg.toggle_protected_neighbor(fdi=36)
            raise AssertionError('Extraction target was allowed in the conserved selection')
        except RuntimeError:
            pass
        assert scene[core.IMMEDIATE_FDIS_KEY] == '[36]', 'Selecting neighbours changed the extraction FDI'
    print('PROTECTED_NEIGHBORS_PASS: separate roles, persistent choice, visible roots, bilateral canals, hidden collision checks',flush=True)
finally:
    dsg.unregister()
