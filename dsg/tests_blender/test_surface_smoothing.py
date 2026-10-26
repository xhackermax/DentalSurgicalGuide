"""User display choice must be reversible and leave IOS registration unchanged."""
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import bpy
import numpy as np

parent = Path(sys.argv[sys.argv.index('--') + 1]).resolve()
sys.path.insert(0, str(parent))
import dsg
dsg.register()
dental = dsg.cbct_dental_module
alignment = dsg.alignment_module

class LayoutRecorder:
    def __init__(self):
        self.operators = []

    def operator(self, identifier, **kwargs):
        self.operators.append(identifier)
        return SimpleNamespace()

    def __getattr__(self, name):
        return lambda *args, **kwargs: self

class SurfaceSmoothingTests(unittest.TestCase):
    def setUp(self):
        self.objects = []
        for fdi in (11, 21):
            mesh = bpy.data.meshes.new('SmoothingTest')
            mesh.from_pydata([(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(2,1,1),(-1,1,1)], [], [(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)])
            mesh.update()
            obj = bpy.data.objects.new(dental.dental_assets.object_name(fdi, 'TOOTH'), mesh)
            obj['DSG_tooth_instance'] = True
            obj['DSG_fdi_number'] = fdi
            obj['DSG_cbct_spacing_zyx_mm'] = [.2,.2,.2]
            bpy.context.scene.collection.objects.link(obj)
            self.objects.append(obj)
        self.before = [np.array([tuple(v.co) for v in o.data.vertices]) for o in self.objects]
        self.assertEqual(len(dental.dentition_objects(bpy.context)), 2)

    def tearDown(self):
        for obj in self.objects:
            mesh = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        bpy.context.scene.pop('DSG_cbct_visual_smoothing_enabled', None)
        bpy.context.scene.pop(dsg.core.ROUTE_STEP_KEY, None)
        bpy.context.scene.pop(dsg.core.SUITE_STAGE_KEY, None)

    def test_button_toggles_all_teeth_without_editing_source(self):
        self.assertTrue(hasattr(dental, 'DSG_OT_CBCTToggleSurfaceSmoothing'), 'Missing user smoothing button')
        for enabled in (True, False, True):
            self.assertEqual(bpy.ops.dsg.cbct_toggle_surface_smoothing(), {'FINISHED'})
            self.assertEqual(bool(bpy.context.scene['DSG_cbct_visual_smoothing_enabled']), enabled)
            for obj, before in zip(self.objects, self.before):
                mods = [m for m in obj.modifiers if m.name == dental.ALIGNMENT_VISUAL_SMOOTH_MODIFIER]
                self.assertEqual(len(mods), 1)
                self.assertEqual(mods[0].show_viewport, enabled)
                np.testing.assert_array_equal(np.array([tuple(v.co) for v in obj.data.vertices]), before)

    def test_alignment_review_respects_user_disabled_choice(self):
        bpy.context.scene['DSG_cbct_visual_smoothing_enabled'] = False
        target = self.objects[0]
        target['dental_suite_alignment_reference'] = True
        alignment._clinical_cbct_review_objects(bpy.context, target)
        self.assertTrue(all((mod:=o.modifiers.get(dental.ALIGNMENT_VISUAL_SMOOTH_MODIFIER)) is None or not mod.show_viewport for o in self.objects), 'Alignment overrode the user display choice')

    def test_alignment_handoff_keeps_user_enabled_choice(self):
        bpy.context.scene['DSG_cbct_visual_smoothing_enabled'] = True
        dental.set_dentition_alignment_visual_smoothing(bpy.context, True)
        alignment._disable_clinical_cbct_review_smoothing(bpy.context)
        self.assertTrue(all(o.modifiers[dental.ALIGNMENT_VISUAL_SMOOTH_MODIFIER].show_viewport for o in self.objects), 'Handoff discarded the user display choice')

    def test_registration_uses_original_points_with_visual_smoothing(self):
        original = alignment._mesh_graph_from_objects(self.objects).points.copy()
        dental.set_dentition_alignment_visual_smoothing(bpy.context, True)
        bpy.context.view_layer.update()
        graph = alignment._mesh_graph_from_objects(self.objects)
        np.testing.assert_allclose(graph.points, original, atol=1e-9, rtol=0, err_msg='Display smoothing altered the IOS mathematical target')

    def test_display_composite_keeps_original_registration_points(self):
        obj = self.objects[0]
        obj['DSG_alignment_duplicate_composite'] = True
        obj['dental_suite_alignment_reference_quality'] = 'ALL_SEGMENTED_DUPLICATE_COMPOSITE'
        obj['DSG_alignment_dental_vertex_count'] = 8
        original = alignment._extract_world_mesh_graph(obj).points.copy()
        dental.set_alignment_visual_smoothing(obj, True)
        bpy.context.view_layer.update()
        np.testing.assert_allclose(alignment._extract_world_mesh_graph(obj).points, original, atol=1e-9, rtol=0)

    def test_button_updates_visible_alignment_composite(self):
        self.assertTrue(hasattr(dental, 'DSG_OT_CBCTToggleSurfaceSmoothing'))
        composite = bpy.data.objects.new('AlignmentTestComposite', self.objects[0].data.copy())
        composite['DSG_alignment_duplicate_composite'] = True
        composite['DSG_cbct_spacing_zyx_mm'] = [.2,.2,.2]
        bpy.context.scene.collection.objects.link(composite)
        self.objects.append(composite)
        self.assertEqual(bpy.ops.dsg.cbct_toggle_surface_smoothing(), {'FINISHED'})
        self.assertTrue(composite.modifiers[dental.ALIGNMENT_VISUAL_SMOOTH_MODIFIER].show_viewport)
        self.assertEqual(bpy.ops.dsg.cbct_toggle_surface_smoothing(), {'FINISHED'})
        self.assertFalse(composite.modifiers[dental.ALIGNMENT_VISUAL_SMOOTH_MODIFIER].show_viewport)

    def test_main_workflow_exposes_improvement_only_in_immediate_review(self):
        # MEJORAR DIENTES (dsg.finish_segmented_teeth) replaced the separate
        # smoothing button; it belongs to the first review only
        # (dsg/docs/MEJORA_UNICA_DIENTES.md).
        action = 'dsg.finish_segmented_teeth'
        for stage, step, expected in ((dsg.core.STAGE_DICOM, 'IMMEDIATE_FDI_REVIEW', 1), (dsg.core.STAGE_ALIGNMENT, 'ALIGNMENT', 0)):
            bpy.context.scene[dsg.core.ROUTE_STEP_KEY] = step
            bpy.context.scene[dsg.core.SUITE_STAGE_KEY] = stage
            layout = LayoutRecorder()
            with patch.object(dsg.core, 'patient_folder', return_value='Test'), patch.object(dsg.core, 'infer_stage', return_value=stage), patch.object(dsg.core, 'clinical_route', return_value=dsg.core.ROUTE_IMMEDIATE), patch.object(dsg.dicom_module.RUNTIME, 'is_loaded', return_value=True):
                dsg.core.DSG_SUITE_PT_Main.draw(SimpleNamespace(layout=layout), bpy.context)
            self.assertEqual(layout.operators.count(action), expected, f'Improvement button count in {step}')
            self.assertNotIn('dsg.cbct_post_smooth_teeth', layout.operators, f'Obsolete smoothing button visible in {step}')

try:
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(SurfaceSmoothingTests))
    if not result.wasSuccessful():
        raise AssertionError('Surface smoothing regressions')
finally:
    dsg.unregister()
