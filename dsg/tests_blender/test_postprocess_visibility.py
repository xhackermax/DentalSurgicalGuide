"""Postprocessing controls require completed segmentation output."""
import sys
from pathlib import Path
from unittest.mock import patch

import bpy

sys.path.insert(0, sys.argv[sys.argv.index('--') + 1])
import dsg

dsg.register()
from dsg import core, cbct_dental_module as dental, dicom_module as dicom


class Layout:
    def __init__(self):
        self.operators = []

    def operator(self, identifier, **kwargs):
        self.operators.append(identifier)
        return self

    def __getattr__(self, name):
        return lambda *args, **kwargs: self


def visible(segmentation_busy=False):
    layout = Layout()
    with patch.object(dicom, 'semantic_workflow_busy', return_value=segmentation_busy):
        dental.draw_surface_smoothing(layout, bpy.context)
    return set(layout.operators)


action = 'dsg.finish_segmented_teeth'
try:
    bpy.context.scene[core.SUITE_STAGE_KEY] = core.STAGE_DICOM
    bpy.context.scene[core.ROUTE_STEP_KEY] = 'IMMEDIATE_FDI_REVIEW'
    for obj in list(bpy.context.scene.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    assert not visible(), 'Controls visible before segmentation'
    mesh = bpy.data.meshes.new('Visibility mesh')
    mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    obj = bpy.data.objects.new('IOS only', mesh)
    bpy.context.scene.collection.objects.link(obj)
    assert not visible(), 'IOS alone must not expose segmentation controls'
    obj['DSG_tooth_instance'] = True
    obj['DSG_fdi_number'] = 11
    obj.name = dental.TOOTH_OBJECT_PREFIX + '11'
    assert not visible(True), 'Controls visible during segmentation with partial output'
    assert visible() == {action}, 'Unified action missing after tooth segmentation'
    del obj['DSG_tooth_instance']
    obj.name = 'Segmented upper arch'
    bpy.context.scene['DSG_simple_upper_object'] = obj.name
    bpy.context.scene[core.ROUTE_STEP_KEY] = 'SIMPLE_REVIEW'
    assert visible() == {action}, 'Arches need the same unified action'
    bpy.context.scene[core.ROUTE_STEP_KEY] = 'ALIGNMENT'
    assert not visible(), 'Action remains in the next step'
    bpy.context.scene[core.ROUTE_STEP_KEY] = 'SIMPLE_REVIEW'
    assert not visible(True), 'Arcade controls visible during segmentation'
    bpy.data.objects.remove(obj, do_unlink=True)
    assert not visible(), 'Controls remain after segmented objects are removed'
    print('POSTPROCESS_VISIBILITY_PASS: empty, IOS, partial, teeth, arches, removed', flush=True)
finally:
    dsg.unregister()
