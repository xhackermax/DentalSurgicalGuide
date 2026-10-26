"""Executable fail-closed FEM candidate preflight with real geometry kernels.

Uses AST-isolated Blender adapter but TRUE sleeve/cylinder sweep algorithms.
No patient fixtures, no false claims of post-Boolean qualification.
"""
import ast
import math
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from dsg import frame_swept_clearance_core as swept
from dsg import frame_sleeve_junction_core as junction


class MockVec:
    def __init__(self, values):
        self.arr=np.asarray(values,dtype=float)
    def __sub__(self,other):
        return MockVec(self.arr-other.arr)
    @property
    def length(self):
        return float(np.linalg.norm(self.arr))
    def dot(self,other):
        return float(self.arr@other.arr)


class FakeObj(dict):
    type="MESH"
    name="IrrigationProtected"


def sleeve(sid,center):
    return dict(id=sid,center=list(center),axis=[0,0,1],
                inner_radius_mm=2.1,outer_radius_mm=3.0,
                height_mm=7.0,lumen_keep_out=True)


def make_fn(objects,mesh_bvh=None):
    source=Path(__file__).resolve().parents[1]/"frame_structural.py"
    tree=ast.parse(source.read_text("utf-8"))
    fn=next(f for f in tree.body if isinstance(f,ast.FunctionDef)
            and f.name=="_validate_fem_candidate_sweep")
    module=ast.Module(body=[fn],type_ignores=[])
    ast.fix_missing_locations(module)
    env=dict(
        bpy=SimpleNamespace(data=SimpleNamespace(objects=objects)),
        np=np,math=math,Vector=MockVec,
        swept_clearance=swept,sleeve_junction=junction,
        guide_module=SimpleNamespace(
            _build_world_surface_bvh=lambda ctx,obj:mesh_bvh),
    )
    exec(compile(module,str(source),"exec"),env)
    return env[fn.name]


def model(start,end,extra_sleeves=(),radius=1.25):
    sleeves=[sleeve("S1",(0,0,0)),*extra_sleeves]
    return dict(
        frame_context=dict(sleeves=sleeves),
        sleeve_records=[dict(id=s["id"],attachment_nodes=[1] if
                             s["id"]=="S1" else [10+i]) for i,s in enumerate(sleeves)],
        nodes=[SimpleNamespace(xyz=np.array(start)),SimpleNamespace(xyz=np.array(end))],
        elements=[SimpleNamespace(i=0,j=1,radius_mm=radius,
                                  active=True,render=True,virtual=False,tag="TEST")],
    )


class ClinicalSweepPreflightTests(unittest.TestCase):
    result=SimpleNamespace(active_elements=(0,))

    def test_outer_sleeve_weld_is_deferred_not_clinically_cleared(self):
        fn=make_fn([])
        report=fn(None,model([7,0,0],[3.03,0,0]),self.result)
        self.assertEqual(report["candidate_tubes"],1)
        self.assertFalse(report["post_boolean_lumen_validated"])
        self.assertFalse(report["clinical_acceptance"])
        self.assertEqual(report["drill_extension_zones"],2)

    def test_through_lumen_route_rejected_even_with_valid_terminal_attachment(self):
        fn=make_fn([])
        with self.assertRaisesRegex(RuntimeError,"TARGET_LUMEN"):
            fn(None,model([-7,0,0],[3.03,0,0],radius=.8),self.result)

    def test_other_sleeve_lumen_never_gets_terminal_exemption(self):
        fn=make_fn([])
        other=sleeve("S2",(5,0,0))
        with self.assertRaisesRegex(RuntimeError,"TARGET_LUMEN"):
            fn(None,model([9,0,0],[3.03,0,0],extra_sleeves=(other,)),self.result)

    def test_actual_irrigation_collision_fails_preflight(self):
        protected=FakeObj(DSG_irrigation_wall_confirmed=True)
        bvh=SimpleNamespace(find_nearest=lambda p:(p.arr,(0,0,1),0,0))
        with self.assertRaisesRegex(RuntimeError,"PROTECTED_OBJECT"):
            make_fn([protected],bvh)(
                None,model([7,0,0],[3.03,0,0]),self.result)

    def test_missing_protected_bvh_fails_before_curves_exist(self):
        protected=FakeObj(DSG_microscrew_confirmed=True)
        with self.assertRaisesRegex(RuntimeError,"BVH_UNAVAILABLE"):
            make_fn([protected],None)(
                None,model([7,0,0],[3.03,0,0]),self.result)

    def test_no_sleeve_records_never_defaults_to_safe(self):
        bad=model([7,0,0],[3.03,0,0])
        bad["sleeve_records"]=[]
        with self.assertRaisesRegex(RuntimeError,"MISSING_SLEEVE_RECORDS"):
            make_fn([])(None,bad,self.result)


if __name__=="__main__":
    unittest.main()
