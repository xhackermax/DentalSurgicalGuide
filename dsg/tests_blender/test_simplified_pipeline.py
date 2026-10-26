"""Direct extraction selection, confirm transition and unified retention routing."""
import ast
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import bpy

sys.path.insert(0, sys.argv[sys.argv.index('--') + 1])
import dsg
dsg.register()
from dsg import core, cbct_dental_module as dental, guide_module as guide
from dsg.blender import retention_finish as finish

try:
    root = Path(dsg.__file__).parent
    # Inspect only the active draw functions, not retained legacy operators.
    source = (root / 'core.py').read_text('utf-8')
    tree = ast.parse(source)
    panel = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'DSG_SUITE_PT_Main')
    draw = next(n for n in panel.body if isinstance(n, ast.FunctionDef) and n.name == 'draw')
    ui = ast.get_source_segment(source, draw)
    assert 'DSG_SUITE_OT_ChangeRoute.bl_idname' not in ui
    assert 'DSG_SUITE_OT_BuildImmediateArchModels.bl_idname' not in ui
    assert 'FDI CORRECTO' not in ui and 'CONFIRMAR + ALINEAR' not in ui
    alignment = (root / '_alignment_parts/01_alignment_operators_ui.py').read_text('utf-8')
    assert 'operator("dicp.auto_detect"' not in alignment
    gui = (root / '_guide_parts/08_export_final_ui_registration.py').read_text('utf-8')
    for old in ('dsg.prepare_aligned_model', 'dsg.validate_blockout_seating', 'dsg.apply_selected_blockout_relief'):
        assert "'" + old + "'," not in gui, old
    assert gui.count('PREPARAR MODELO RETENTIVO') >= 4
    scene = bpy.context.scene
    for obj in list(scene.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    scene.dsg_suite_settings.workflow_route = core.ROUTE_IMMEDIATE
    scene[core.SUITE_STAGE_KEY] = core.STAGE_DICOM
    scene[core.ROUTE_STEP_KEY] = 'IMMEDIATE_FDI_REVIEW'
    for name, key, position in [('Test maxilla', 'DSG_maxilla_object', (0,0,0)),
                                ('Test mandible', 'DSG_mandible_object', (0,0,-4))]:
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, location=position)
        bpy.context.object.name = name
        scene[key] = name
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, location=(0,0,2))
    tooth = bpy.context.object
    tooth.name = dental.TOOTH_OBJECT_PREFIX + '11'
    tooth['DSG_tooth_instance'] = True
    tooth['DSG_fdi_number'] = 11
    tooth['DSG_universal_label'] = 1
    assert bpy.ops.dsg_suite.fix_immediate_extraction_selection() == {'FINISHED'}
    assert scene[core.ROUTE_STEP_KEY] == 'IMMEDIATE_SELECT_TEETH'
    assert core._immediate_extraction_fdis(scene) == [11]
    with patch.object(dental, 'upgrade_teeth_to_full_resolution', return_value={'elapsed_s':0}), \
         patch.object(core, '_export_object_to_patient'), \
         patch.object(core, '_auto_import_patient_ios', return_value=(False, 'fixture')):
        assert bpy.ops.dsg_suite.confirm_immediate_models() == {'FINISHED'}
    assert scene[core.ROUTE_STEP_KEY] == 'ALIGNMENT'
    assert core.infer_stage(scene) == core.STAGE_ALIGNMENT
    upper = bpy.data.objects[scene['DSG_immediate_upper_composite']]
    lower = bpy.data.objects[scene['DSG_immediate_lower_composite']]
    assert len(upper.data.polygons) == 20 and len(lower.data.polygons) == 20
    assert tooth.name in bpy.data.objects and tooth.hide_get()
    scene.dsg_suite_settings.workflow_route = core.ROUTE_SIMPLE
    # The unified command preserves local edits and stops on failed generation.
    calls = []
    ops = SimpleNamespace(
        prepare_aligned_model=Mock(side_effect=lambda: calls.append('generate') or {'FINISHED'}),
        validate_blockout_seating=Mock(side_effect=lambda: calls.append('audit') or {'FINISHED'}),
        apply_selected_blockout_relief=Mock(side_effect=lambda: calls.append('relief+audit') or {'FINISHED'}))
    with patch.object(finish, 'bpy', SimpleNamespace(data=bpy.data, ops=SimpleNamespace(dsg=ops))):
        blockout = bpy.data.objects.new(guide.BLOCKOUT_NAME, bpy.data.meshes.new('test blockout'))
        scene.collection.objects.link(blockout)
        blockout['DSG_seating_validation_status'] = 'PASSED'
        assert finish.run(SimpleNamespace(scene=scene, mode='OBJECT')) == {'FINISHED'}
        assert calls == ['generate'], 'Seating audit must run once (inside generation), not twice'
        blockout['DSG_seating_validation_status'] = 'REVIEW'
        assert finish.run(SimpleNamespace(scene=scene, mode='OBJECT')) == {'CANCELLED'}
        calls.clear()
        assert finish.run(SimpleNamespace(scene=scene, mode='EDIT_MESH', edit_object=blockout)) == {'FINISHED'}
        assert calls == ['relief+audit'], 'Local correction was overwritten by regeneration'
        calls.clear()
        ops.prepare_aligned_model.side_effect = lambda: {'CANCELLED'}
        assert finish.run(SimpleNamespace(scene=scene, mode='OBJECT')) == {'CANCELLED'}
        assert calls == [], 'A failed generation continued into seating validation'
    print('SIMPLIFIED_PIPELINE_PASS: removed UI, fixed FDI, real arch builds, confirm transition, unified retention dispatch', flush=True)
finally:
    dsg.unregister()
