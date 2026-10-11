"""Final Boolean guide adapter contracts with fake Blender objects and real mesh slicing."""
import ast
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from dsg import frame_boolean_section_core as sections


def box_mesh():
    pts=np.array([[-1,-1,-1],[1,-1,-1],[1,1,-1],[-1,1,-1],
                  [-1,-1,1],[1,-1,1],[1,1,1],[-1,1,1]],float)
    quad=[(0,1,2,3),(4,7,6,5),(0,4,5,1),(1,5,6,2),(2,6,7,3),(3,7,4,0)]
    tris=[]
    for a,b,c,d in quad:
        tris.extend([(a,b,c),(a,c,d)])
    return pts,np.array(tris,dtype=int)


class FakeGuide(dict):
    def __init__(self, final):
        super().__init__(DSG_final_cut_completed=final)
        self.name="DSG_Guide"
        self.type="MESH"


class FinalSectionAdapterTests(unittest.TestCase):
    def function(self, final=True, valid=True):
        guide=FakeGuide(final)
        input_calls=[]
        orig=Path(__file__).resolve().parents[1]/"frame_structural.py"
        tree=ast.parse(orig.read_text("utf-8"))
        function=next(x for x in tree.body if isinstance(x,ast.FunctionDef)
                      and x.name=="inspect_final_boolean_guide_section")
        module=ast.Module(body=[function],type_ignores=[])
        ast.fix_missing_locations(module)
        context=SimpleNamespace(scene=SimpleNamespace(dsg_props=object()))
        guide_module=SimpleNamespace(
            get_active_guide_obj=lambda props:guide,
            _valid_obj=lambda obj:valid,
        )
        env={"bpy":SimpleNamespace(context=context),"guide_module":guide_module,
             "boolean_sections":sections}
        exec(compile(module,str(orig),"exec"),env)
        def arrays(obj):
            self.assertIs(obj,guide)
            input_calls.append(obj)
            return box_mesh()
        return env["inspect_final_boolean_guide_section"],context,input_calls,arrays

    def test_real_mesh_measurement_is_read_only_and_not_clinically_approved(self):
        fn,ctx,calls,arrays=self.function()
        r=fn(ctx,point_mm=[0,0,0],axis=[1,0,0],mesh_arrays_fn=arrays)
        self.assertEqual(len(calls),1)
        self.assertEqual(r["section_area_mm2"],4)
        self.assertEqual(r["principal_inertia_min_mm4"],4/3)
        self.assertTrue(r["mesh_is_post_boolean"])
        self.assertFalse(r["design_approved"])
        self.assertFalse(r["full_frame_fem_validated"])
        self.assertFalse(r["geometry_mutated"])


    def test_nominal_reference_is_comparison_only(self):
        fn,ctx,calls,arrays=self.function()
        r=fn(ctx,point_mm=[0,0,0],axis=[1,0,0],
             nominal_radius_mm=1.0,mesh_arrays_fn=arrays)
        self.assertAlmostEqual(r["geometry_reference_area_ratio"],4/np.pi)
        self.assertAlmostEqual(r["geometry_reference_weak_inertia_ratio"],16/(3*np.pi))
        self.assertTrue(r["section_may_include_merged_frame"])
        self.assertFalse(r["design_approved"])

    def test_before_final_boolean_rejected_before_extraction(self):
        fn,ctx,calls,arrays=self.function(final=False)
        with self.assertRaisesRegex(RuntimeError,"REQUIRES_FINAL_GUIDE"):
            fn(ctx,point_mm=[0,0,0],axis=[1,0,0],mesh_arrays_fn=arrays)
        self.assertFalse(calls)

    def test_invalid_guide_fails_even_if_tagged(self):
        fn,ctx,calls,arrays=self.function(valid=False)
        with self.assertRaisesRegex(RuntimeError,"REQUIRES_FINAL_GUIDE"):
            fn(ctx,point_mm=[0,0,0],axis=[1,0,0],mesh_arrays_fn=arrays)
        self.assertFalse(calls)

    def test_outside_probe_rejected_instead_of_reporting_material(self):
        fn,ctx,calls,arrays=self.function()
        with self.assertRaisesRegex(sections.InvalidBooleanSection,"OUTSIDE"):
            fn(ctx,point_mm=[0,4,4],axis=[1,0,0],mesh_arrays_fn=arrays)

    def test_blender_rna_final_operator_contract_and_ui(self):
        root=Path(__file__).resolve().parents[1]
        source=ast.parse((root/"frame_structural.py").read_text("utf-8"))
        operator=next(x for x in source.body if isinstance(x,ast.ClassDef)
                      and x.name=="DSG_OT_InspectFinalBooleanSection")
        assert hasattr(operator,"body")
        props=[x for x in operator.body if isinstance(x,ast.Assign)
               and any(isinstance(y,ast.Name) and y.id=="__annotations__"
                       for y in x.targets)]
        self.assertEqual(len(props),1)
        self.assertIsInstance(props[0].value,ast.Dict)
        ui=(root/"_guide_parts/08_export_final_ui_registration.py").read_text("utf-8")
        self.assertIn("'dsg.inspect_final_boolean_section'",ui)
        self.assertIn("'DSG_final_cut_completed'",ui)


if __name__=="__main__":
    unittest.main()
