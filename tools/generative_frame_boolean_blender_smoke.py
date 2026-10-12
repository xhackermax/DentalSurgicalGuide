"""Real Blender 5.2.2 Boolean guide smoke: synthetic 1- and 2-sleeve parts.

Use ACTUAL Blender mesh Booleans, not mock bpy and not synthetic only-NumPy
triangles. Fully isolated from clinical operators and patient projects.
All dimensional assertions here are TEST FIXTURES, not clinical thresholds.
The ray-grid is sampled diagnostics, not a certified full drill-path proof.
"""
import math
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

import addon_utils
import bpy
from mathutils import Vector
from dsg.guide_export.blender_adapter import mesh_arrays


def add_cylinder(name, center, radius, height, *, vertices=96):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=vertices, radius=radius, depth=height,
        location=tuple(center),
    )
    obj=bpy.context.object
    obj.name=name
    return obj


def add_member(name, start, end, radius):
    a=Vector(start); b=Vector(end)
    delta=b-a
    if delta.length<1e-5:
        raise AssertionError("Degenerate synthetic connector")
    obj=add_cylinder(name,(a+b)*0.5,radius,delta.length,vertices=48)
    obj.rotation_euler=delta.to_track_quat('Z','Y').to_euler()
    return obj


def boolean_apply(base, operand, mode):
    assert base.type=='MESH' and operand.type=='MESH'
    bpy.ops.object.select_all(action='DESELECT')
    base.select_set(True)
    bpy.context.view_layer.objects.active=base
    mod=base.modifiers.new('Synthetic_'+mode,'BOOLEAN')
    mod.operation=mode
    mod.solver='EXACT'
    mod.object=operand
    result=bpy.ops.object.modifier_apply(modifier=mod.name)
    assert result=={'FINISHED'},f'Blender Boolean {mode}: {result}'
    bpy.data.objects.remove(operand,do_unlink=True)
    assert len(base.modifiers)==0
    return base


def build_synthetic_guide(number_of_sleeves, *, drill=True, add_connector=True):
    assert number_of_sleeves in (1,2)
    centers=(0.,) if number_of_sleeves==1 else (-7.,7.)
    outer_radius=3.3
    inner_radius=2.1
    guide=None
    for i, x in enumerate(centers):
        # Do not rely on UNION to join disjoint bodies. In the two-sleeve
        # fixture, install the shared perimeter member before the second
        # sleeve, creating a genuinely overlapping continuous union.
        if i==1 and add_connector:
            bridge=add_member('Synthetic_perimeter',
                              (centers[0],3.08,0),(centers[1],3.08,0),0.9)
            guide=boolean_apply(guide,bridge,'UNION')
        tube=add_cylinder(f'Synthetic_sleeve_{i}',(x,0,0),outer_radius,7.)
        guide=tube if guide is None else boolean_apply(guide,tube,'UNION')
    if add_connector:
        for i,x in enumerate(centers):
            side=1 if x>=0 else -1
            member=add_member(
                f'Synthetic_reinforcement_{i}',
                (x+side*2.9,0,0),(x+side*7.8,0,0),
                1.1)
            guide=boolean_apply(guide,member,'UNION')
    # Final Boolean bore always occurs AFTER unioning the terminal outer weld.
    if drill:
        for i,x in enumerate(centers):
            cutter=add_cylinder(f'Synthetic_final_drill_{i}',
                                (x,0,0),inner_radius,10.)
            guide=boolean_apply(guide,cutter,'DIFFERENCE')
    guide.name=f'DSG_Synthetic_Guide_{number_of_sleeves}'
    return guide,centers,inner_radius


def sampled_bore_and_wall(guide,centers,expected_inner_radius):
    """Sample finished geometry's axial lumen + first outer shell wall.

    This rejects uncut bores and simple obstructing plugs. It is NOT a
    continuous certification of all solid regions, drill instruments,
    insertion constraints or wall minima outside sampled ray directions.
    """
    grid=[]
    world=guide.matrix_world.copy()
    to_local=world.inverted_safe()
    for cx in centers:
        for z in (-2.4,-1.2,0.,1.2,2.4):
            for k in range(24):
                theta=2*math.pi*k/24
                direct=Vector((math.cos(theta),math.sin(theta),0.))
                axis_point=Vector((cx,0,z))
                # Object.ray_cast accepts OBJECT-LOCAL coordinates. The
                # synthetic two-sleeve base is translated (-7 mm), so
                # treating world points as local created a false clearance
                # failure even though the actual Boolean was correct.
                local_start=to_local @ axis_point
                local_dir=(to_local.to_3x3() @ direct).normalized()
                hit,local_position,_,_=guide.ray_cast(
                    local_start,local_dir,distance=12.)
                if not hit:
                    return False,{'reason':'NO_INNER_FACE','center':cx,'z':z,'angle':k}
                position=world @ local_position
                bore_radius=float((position-axis_point).length)
                if not (expected_inner_radius-0.14 <= bore_radius
                        <= expected_inner_radius+0.14):
                    return False,{'reason':'BORE_NOT_CLEAR_OR_OVERSIZED',
                                  'radius_mm':bore_radius,'center':cx,'z':z,'angle':k}
                # If an inside wall is found, follow the ray until we hit the
                # outer surface. This is an independent sampled wall diagnostic.
                next_origin=position+direct*0.025
                found,local_out,_,_=guide.ray_cast(
                    to_local @ next_origin,local_dir,distance=7.)
                if not found:
                    return False,{'reason':'NO_OUTER_WALL','center':cx,'z':z,'angle':k}
                wall_mm=float(((world @ local_out)-next_origin).length)
                if wall_mm<0.65:
                    return False,{'reason':'SAMPLED_WALL_TOO_THIN',
                                  'wall_mm':wall_mm,'center':cx,'z':z,'angle':k}
                grid.append((round(bore_radius,3),round(wall_mm,3)))
    return True,{'sampled_rays':len(grid),'minimum_sampled_wall_mm':min(w for _,w in grid),
                 'maximum_bore_deviation_mm':max(abs(r-expected_inner_radius) for r,_ in grid)}


def cleanup_synthetic_scene():
    bpy.ops.object.select_all(action='DESELECT')
    for obj in tuple(bpy.data.objects):
        bpy.data.objects.remove(obj,do_unlink=True)
    assert not bpy.data.objects[:], 'Synthetic fixture left Blender objects'


def main():
    assert bpy.app.version[:2]==(5,2),bpy.app.version
    bpy.ops.wm.read_factory_settings(use_empty=True)
    assert addon_utils.enable('dsg',default_set=True) is not None
    for nsleeves in (1,2):
        observations=[]
        for iteration in (0,1):
            guide,centers,bore=build_synthetic_guide(nsleeves)
            verts,faces=mesh_arrays(guide)
            assert len(faces)>=96 and len(verts)>=96, 'No evaluated Boolean result'
            success,stats=sampled_bore_and_wall(guide,centers,bore)
            assert success,f'Boolean failed for {nsleeves} sleeves: {stats}'
            assert stats['sampled_rays']==120*nsleeves,stats
            observations.append(stats)
            print('Synthetic',nsleeves,'sleeves, iteration',iteration,stats)
            cleanup_synthetic_scene()
        assert observations[0]==observations[1], 'Repeated Boolean output differs'

    # Negative control: the model without the final drilling operation must
    # not be reported as having an open sleeve lumen.
    guide,centers,bore=build_synthetic_guide(1,drill=False)
    success,stats=sampled_bore_and_wall(guide,centers,bore)
    assert not success and stats['reason']=='BORE_NOT_CLEAR_OR_OVERSIZED',stats
    cleanup_synthetic_scene()

    addon_utils.disable('dsg',default_set=True)
    print('GF3 REAL BLENDER BOOLEAN PASS: 1/2 sleeve weld->union->bore->sampled-wall'
          ' repeated + undrilled negative control, no clinical approval')


if __name__=='__main__':
    main()
