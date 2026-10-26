"""Blender-free regression for actual post-Boolean guide path profiles."""
import ast
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from dsg import frame_boolean_path_core as path_core
from dsg.frame_boolean_section_core import InvalidBooleanSection


def cuboid():
    v=np.asarray([[-5,-1,-1],[5,-1,-1],[5,1,-1],[-5,1,-1],
                  [-5,-1,1],[5,-1,1],[5,1,1],[-5,1,1]],float)
    q=[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
    triangles=[]
    for a,b,c,d in q:
        triangles.extend(((a,b,c),(a,c,d)))
    return v,np.asarray(triangles,dtype=int)


class Guide(dict):
    def __init__(self,final=True):
        super().__init__(DSG_final_cut_completed=final)
        self.name="DSG_Guide"
        self.type="MESH"


class BlenderPathAdapterTests(unittest.TestCase):
    def make(self,final=True):
        original=Guide(final)
        source=Path(__file__).resolve().parents[1]/"frame_structural.py"
        tree=ast.parse(source.read_text("utf-8"))
        func=next(x for x in tree.body if isinstance(x,ast.FunctionDef)
                  and x.name=="inspect_final_boolean_guide_path")
        mod=ast.Module(body=[func],type_ignores=[])
        ast.fix_missing_locations(mod)
        context=SimpleNamespace(scene=SimpleNamespace(dsg_props=object()))
        env={
            "bpy":SimpleNamespace(context=context),
            "guide_module":SimpleNamespace(
                get_active_guide_obj=lambda props:original,
                _valid_obj=lambda obj:obj is original),
            "boolean_paths":path_core,
        }
        exec(compile(mod,str(source),"exec"),env)
        calls=[]
        def arrays(obj):
            self.assertIs(obj,original)
            calls.append(obj)
            return cuboid()
        return env["inspect_final_boolean_guide_path"],context,calls,arrays

    def test_full_station_report_without_guide_mutation(self):
        fn,ctx,calls,arrays=self.make()
        report=fn(ctx,interior_centerline_mm=[[-4,0,0],[4,0,0]],
                  nominal_radii_mm=[1,1],sample_count=5,mesh_arrays_fn=arrays)
        self.assertEqual(len(calls),1)
        self.assertEqual(report["station_count"],5)
        self.assertAlmostEqual(report["area_min_mm2"],4)
        self.assertAlmostEqual(report["weak_inertia_min_mm4"],4/3)
        self.assertEqual(len(report["stations"]),5)
        self.assertFalse(report["geometry_mutated"])
        self.assertFalse(report["post_boolean_fem_validated"])
        self.assertFalse(report["retention_validated"])

    def test_no_final_cut_means_no_extraction(self):
        fn,ctx,calls,arrays=self.make(final=False)
        with self.assertRaisesRegex(RuntimeError,"REQUIRES_FINAL_GUIDE"):
            fn(ctx,interior_centerline_mm=[[-4,0,0],[4,0,0]],
               mesh_arrays_fn=arrays)
        self.assertFalse(calls)

    def test_surface_trace_outside_retained_solid_fails_closed(self):
        fn,ctx,calls,arrays=self.make()
        with self.assertRaises(InvalidBooleanSection):
            fn(ctx,interior_centerline_mm=[[-4,2,0],[4,2,0]],
               mesh_arrays_fn=arrays)


    def test_diagnostics_remain_visible_after_reinforcements_confirmed(self):
        root=Path(__file__).resolve().parents[1]
        tree=ast.parse((root/"_guide_parts/08_export_final_ui_registration.py")
                       .read_text("utf8"))
        helper=next(x for x in tree.body if isinstance(x,ast.FunctionDef)
                    and x.name=="_draw_geodesic_research_tools")
        draw=next(x for x in tree.body if isinstance(x,ast.FunctionDef)
                  and x.name=="_draw_step_reinforcement")
        calls=[
            x for x in ast.walk(draw)
            if isinstance(x,ast.Call) and isinstance(x.func,ast.Name)
            and x.func.id=="_draw_geodesic_research_tools"
        ]
        self.assertEqual(len(calls),2)
        self.assertTrue(any(isinstance(x,ast.Constant) and
                            x.value=="dsg.analyze_geodesic_groups"
                            for x in ast.walk(helper)))
        self.assertTrue(any(isinstance(x,ast.Constant) and
                            x.value=="dsg.preview_geodesic_frame_fem"
                            for x in ast.walk(helper)))

    def test_operator_is_registered_and_final_step_button_exists(self):
        root=Path(__file__).resolve().parents[1]
        tree=ast.parse((root/"frame_structural.py").read_text("utf8"))
        classes=next(x.value for x in tree.body if isinstance(x,ast.Assign)
                     and any(isinstance(target,ast.Name) and target.id=="_CLASSES"
                             for target in x.targets))
        self.assertIn("DSG_OT_InspectFinalBooleanPath",
                      [x.id for x in classes.elts])
        operator=next(x for x in tree.body if isinstance(x,ast.ClassDef)
                      and x.name=="DSG_OT_InspectFinalBooleanPath")
        self.assertTrue(any(isinstance(x,ast.Assign)
                            and any(isinstance(y,ast.Name) and y.id=="__annotations__"
                                    for y in x.targets)
                            for x in operator.body))
        ui=(root/"_guide_parts/08_export_final_ui_registration.py").read_text("utf8")
        self.assertIn("'dsg.inspect_final_boolean_path'",ui)


if __name__=="__main__":
    unittest.main()
