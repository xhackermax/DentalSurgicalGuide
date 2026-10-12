"""Real Blender 5.2 Boolean test for research sleeve-to-reinforcement welds.

Creates synthetic 1-sleeve and 2-sleeve geometry, unions attached members,
drills final lumens via Blender EXACT and measures actual resulting mesh.
NO real dental data, clinical acceptance, STL, project writes or addon merge.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

import bpy
import numpy as np
from mathutils import Vector
from dsg.frame_sleeve_junction_core import preflight_sleeve_junction
from dsg.frame_boolean_section_core import (
    InvalidBooleanSection, measure_boolean_section,
)
from dsg.guide_export.blender_adapter import mesh_arrays


def cylinder(name, center, radius, height, axis=(0,0,1), sides=96):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=sides,radius=float(radius),depth=float(height),
        end_fill_type="NGON",location=center,
    )
    obj=bpy.context.object
    obj.name=name
    obj.rotation_mode="QUATERNION"
    obj.rotation_quaternion=Vector((0,0,1)).rotation_difference(Vector(axis))
    return obj


def beam(name, a, b, radius, sides=64):
    a=Vector(a); b=Vector(b); segment=b-a
    if segment.length<=1e-6:
        raise ValueError("synthetic zero-length member")
    return cylinder(name,(a+b)*0.5,radius,segment.length,axis=segment,sides=sides)


def apply_boolean(target, cutter, operation):
    bpy.ops.object.select_all(action="DESELECT")
    target.hide_set(False)
    target.select_set(True)
    bpy.context.view_layer.objects.active=target
    modifier=target.modifiers.new("DSG_TEST_"+operation,"BOOLEAN")
    modifier.operation=operation
    modifier.solver="EXACT"
    modifier.object=cutter
    result=bpy.ops.object.modifier_apply(modifier=modifier.name)
    if result!={'FINISHED'}:
        raise AssertionError(f"{operation} failed: {result}")
    bpy.data.objects.remove(cutter,do_unlink=True)


def record_sleeve(sid,center):
    return {"id":sid,"center":tuple(center),"axis":(0,0,1),
            "inner_radius_mm":2.1,"outer_radius_mm":3.,
            "height_mm":7.,"lumen_keep_out":True}


def check_final_lumens(guide,centers):
    vertices,triangles=mesh_arrays(guide)
    assert len(triangles)>100, "Boolean did not produce closed triangulated surface"
    # Check actual output, never nominal cylinders. The geometry is inside
    # the retained annular wall at +Y and the bore is provably empty at axis.
    for cx,cy,cz in centers:
        for z in (-1.7,0.31,1.6):
            probe=(cx,cy+2.55,cz+z)
            result=measure_boolean_section(
                vertices,triangles,(cx,cy,cz+z),(0,0,1),
                probe_point_mm=probe,
            )
            assert result.hole_count>=1,(cx,z,result)
            assert result.area_mm2>1.0,(cx,z,result)
            try:
                measure_boolean_section(
                    vertices,triangles,(cx,cy,cz+z),(0,0,1),
                    probe_point_mm=(cx,cy,cz+z),
                )
            except InvalidBooleanSection:
                pass
            else:
                raise AssertionError(f"Drill lumen {cx} is not empty at z={z}")
        # A tolerance accounts for tessellated round cutters. Any mesh vertex
        # in the protected inner core at sleeve height indicates obstruction.
        local=vertices-np.asarray((cx,cy,cz))
        radial=np.linalg.norm(local[:,:2],axis=1)
        impossible=(radial<2.1-0.025)&(abs(local[:,2])<3.5-0.025)
        assert not bool(np.any(impossible)),f"Solid remains inside lumen {cx}"
    return len(vertices),len(triangles)


def exercise(sleeve_count):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    centers=[(12.*i,0.,0.) for i in range(sleeve_count)]
    sleeves=[record_sleeve(f"S{i+1}",c) for i,c in enumerate(centers)]
    guide=cylinder("SyntheticOuterSleeve",centers[0],3.,7.)
    for center in centers[1:]:
        apply_boolean(guide,cylinder("OuterSleeve",center,3.,7.),"UNION")

    # Each outer-wall weld has preBoolean overlap but is permitted ONLY as
    # deferred to an actual subsequent postBoolean lumen check.
    for idx,(cx,cy,cz) in enumerate(centers):
        sign=-1 if idx==0 and sleeve_count>1 else 1
        if idx==0 and sleeve_count==1:
            sign=1
        outer=(cx+sign*3.03,cy,cz)
        origin=(cx+sign*7.5,cy,cz)
        check=preflight_sleeve_junction(
            [origin,outer],[1.25,1.25],sleeves,
            target_sleeve_id=f"S{idx+1}",
            maximum_deferred_tip_mm=2.1,
        )
        assert check.candidate_admissible,(idx,check)
        assert check.post_boolean_lumen_validation_required
        assert not check.final_lumen_clear
        # Continue the physical tube a little through outer wall so Boolean
        # UNION forms a merged junction rather than merely touching surfaces.
        end=(cx+sign*2.68,cy,cz)
        apply_boolean(guide,beam("Reinforcement",origin,end,1.25),"UNION")

    if sleeve_count==2:
        # A synthetic connected perimeter segment ensures one fused body.
        apply_boolean(guide,beam("FrameBridge",(2.7,1.1,0),(9.3,1.1,0),.85),"UNION")

    # The final *drilling* Boolean must reopen and preserve the sleeve lumen.
    for i,c in enumerate(centers):
        apply_boolean(guide,cylinder(f"DrillBore_{i}",c,2.1,9.),"DIFFERENCE")

    points,faces=check_final_lumens(guide,centers)
    assert not bool(guide.get("DSG_final_cut_completed",False)), (
        "Synthetic smoke must not mark a clinical guide approved"
    )
    bpy.data.objects.remove(guide,do_unlink=True)
    assert len(bpy.data.objects)==0, "Research smoke leaked Blender objects"
    print(f"PASS synthetic postBoolean sleeve welds={sleeve_count} mesh={points}v/{faces}t")


if __name__=="__main__":
    assert bpy.app.version[:2]==(5,2),bpy.app.version
    exercise(1)
    exercise(2)
    print("GF3 ONE/TWO-SLEEVE REAL BOOLEAN RESEARCH SMOKE: PASS")
