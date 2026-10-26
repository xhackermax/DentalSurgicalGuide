"""One improvement action, once per segmentation, never in the next step."""
import sys
import time
from pathlib import Path

import bpy

sys.path.insert(0, sys.argv[sys.argv.index('--') + 1])
import dsg
dsg.register()
from dsg import core, cbct_dental_module as dental, cbct_post_smoothing as post


class Layout:
    def __init__(self):
        self.operators = []
        self.properties = []

    def operator(self, identifier, **kwargs):
        self.operators.append(identifier)
        return self

    def prop(self, value, name, **kwargs):
        self.properties.append(name)
        return self

    def __getattr__(self, name):
        return lambda *args, **kwargs: self


def layouts():
    primary, dicom, alignment = Layout(), Layout(), Layout()
    dental.draw_surface_smoothing(primary, bpy.context)
    dental.draw_review(dicom, bpy.context)
    dental.draw_alignment_handoff(alignment, bpy.context)
    return primary, dicom, alignment


try:
    for obj in list(bpy.context.scene.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    scene = bpy.context.scene
    scene[core.SUITE_STAGE_KEY] = core.STAGE_DICOM
    scene[core.ROUTE_STEP_KEY] = 'IMMEDIATE_FDI_REVIEW'
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=1)
    obj = bpy.context.object
    obj.name = dental.TOOTH_OBJECT_PREFIX + '11'
    obj['DSG_tooth_instance'] = True
    obj['DSG_universal_label'] = 1
    obj['DSG_fdi_number'] = 11
    obj['DSG_cbct_spacing_zyx_mm'] = [.2,.2,.2]
    scene.dsg_cbct_dental.ready = True
    raw = obj.data
    action = 'dsg.finish_segmented_teeth'
    obsolete = {'dsg.cbct_post_smooth_teeth', 'dsg.voxel_remesh_segmented',
                'dsg.cbct_improve_geometry', 'dsg.voxel_remesh_restore',
                'dsg.cbct_post_smooth_report', 'dsg.cbct_toggle_surface_smoothing'}
    primary, dicom, alignment = layouts()
    all_actions = primary.operators + dicom.operators + alignment.operators
    assert all_actions.count(action) == 1, 'Improvement is duplicated or not unified'
    assert not obsolete.intersection(all_actions), 'Separate anatomy-improvement controls remain'
    assert not {'surface_finish_mode', 'voxel_remesh_size'}.intersection(primary.properties)
    assert bpy.ops.dsg.finish_segmented_teeth() == {'FINISHED'}
    deadline = time.monotonic() + 60
    while post.busy() and time.monotonic() < deadline:
        post._poll()
        time.sleep(.03)
    assert not post.busy(), 'Improvement worker timed out'
    from dsg.blender import segmentation_finish as finish
    assert scene.get(finish.DONE), str(scene.get(post.STATUS))
    assert post.source_mesh(obj) == raw, 'Numerical alignment lost the original CBCT reference'
    assert obj.get('DSG_fdi_number') == 11
    assert action not in layouts()[0].operators, 'Successful action remains available for duplicate application'
    finish.reset(scene)
    for step, stage in [('IMMEDIATE_SELECT_TEETH', core.STAGE_DICOM),
                        ('IMMEDIATE_ARCH_REVIEW', core.STAGE_DICOM),
                        ('ALIGNMENT', core.STAGE_ALIGNMENT), ('DSG', core.STAGE_GUIDE)]:
        scene[core.ROUTE_STEP_KEY] = step
        scene[core.SUITE_STAGE_KEY] = stage
        assert action not in layouts()[0].operators, ('Improvement leaks into next step', step)
    scene[core.ROUTE_STEP_KEY] = 'IMMEDIATE_FDI_REVIEW'
    scene[core.SUITE_STAGE_KEY] = core.STAGE_DICOM
    assert layouts()[0].operators.count(action) == 1, 'New segmentation does not reset the one-shot action'
    before = obj.data
    assert bpy.ops.dsg.finish_segmented_teeth() == {'FINISHED'}
    scene[core.SUITE_STAGE_KEY] = core.STAGE_ALIGNMENT
    scene[core.ROUTE_STEP_KEY] = 'ALIGNMENT'
    post._poll()
    assert not post.busy() and obj.data == before, 'Advancing did not cancel safely'
    # Simple arches use the same single action without inventing tooth/FDI IDs.
    for key in ('DSG_tooth_instance', 'DSG_universal_label', 'DSG_fdi_number'):
        obj.pop(key, None)
    obj.name = 'Upper arch'
    scene['DSG_simple_upper_object'] = obj.name
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=1, location=(3,0,0))
    lower = bpy.context.object
    lower.name = 'Lower arch'
    lower['DSG_cbct_spacing_zyx_mm'] = [.2,.2,.2]
    scene['DSG_simple_lower_object'] = lower.name
    scene[core.SUITE_STAGE_KEY] = core.STAGE_DICOM
    scene[core.ROUTE_STEP_KEY] = 'SIMPLE_REVIEW'
    finish.reset(scene)
    assert layouts()[0].operators.count(action) == 1
    assert bpy.ops.dsg.finish_segmented_teeth() == {'FINISHED'}
    deadline = time.monotonic() + 60
    while post.busy() and time.monotonic() < deadline:
        post._poll()
        time.sleep(.03)
    assert scene.get(finish.DONE) and not post.busy()
    assert 'DSG_universal_label' not in obj and 'DSG_fdi_number' not in lower
    assert action not in layouts()[0].operators
    print('SINGLE_SEGMENTATION_IMPROVEMENT_PASS: one owner, real worker, one-shot, next-step hidden, raw reference, cancel', flush=True)
finally:
    post.cancel()
    dsg.unregister()
