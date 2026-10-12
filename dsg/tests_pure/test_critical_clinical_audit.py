"""Safety regression tests for the 2026-10 clinical DSG audit.

Pure-Python tests verify both executable contracts and Blender glue structure.
Real clinical Blender operators require separate headless/full-scene integration.
"""
import ast
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from dsg.pipeline_core import ContractError, Labelmap, ResultManifest
from dsg import cbct_pipeline_client as client
from dsg import frame_fem_core as fem
from dsg.frame_geodesic_fem import append_geodesic_beams

ROOT = Path(__file__).resolve().parents[1]


class EdentulousSimpleContractsTests(unittest.TestCase):
    def test_simple_jaw_only_accepted_but_full_requires_teeth(self):
        arr = np.zeros((4, 5, 6), np.uint8)
        arr[0] = 53
        arr[1] = 54
        parsed = Labelmap.parse(arr, arr.shape, (0.2,0.3,0.4), "TOTALSEG",
                                require_teeth=False)
        self.assertFalse(parsed.fdis)
        with self.assertRaisesRegex(ContractError, "dientes individualizados"):
            Labelmap.parse(arr, arr.shape, (0.2,0.3,0.4), "TOTALSEG")
        with self.assertRaisesRegex(ContractError, "SIMPLE_ARCHES"):
            Labelmap.parse(np.zeros_like(arr), arr.shape, (.2,.3,.4), "TOTALSEG",
                           require_teeth=False)

    def test_manifest_route_confusion_and_edentulous_rules(self):
        valid = {
            "schema_version":1, "run_id":"test_simple", "status":"OK",
            "route_mode":"SIMPLE_ARCHES", "normalized_labels_path":"private.npy",
            "labelmap_contract":{"dims_zyx":[4,5,6],"dtype":"uint8",
                                 "labels":[0,53,54]}
        }
        self.assertEqual(
            ResultManifest.parse(valid,"test_simple",
                                 require_teeth=False,
                                 expected_route_mode="SIMPLE_ARCHES").payload,valid)
        with self.assertRaisesRegex(ContractError,"dientes"):
            ResultManifest.parse(valid,"test_simple")
        with self.assertRaisesRegex(ContractError,"otra ruta"):
            ResultManifest.parse(valid,"test_simple",require_teeth=False,
                                 expected_route_mode="FULL")
        with self.assertRaisesRegex(ContractError,"maxila ni mandíbula"):
            ResultManifest.parse({**valid,"labelmap_contract":
                                 {**valid["labelmap_contract"],"labels":[0]}},
                                 require_teeth=False)


class WorkerLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.original=client._JOB.copy()
        client._JOB.update(process=None,job_dir="",error="",started=0.0,
                           consumed=False,fallback_attempted=False,
                           request_path="",route_mode="FULL",fallback_events=[])

    def tearDown(self):
        client._JOB.clear()
        client._JOB.update(self.original)

    def test_idle_state_never_reads_cwd_status_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            import os
            prev=os.getcwd()
            try:
                os.chdir(tmp)
                Path("status.json").write_text(json.dumps(
                    {"done":True,"message":"FOREIGN_PATIENT_STATUS"}))
                r=client.state()
                self.assertFalse(r["done"])
                self.assertNotEqual(r["message"],"FOREIGN_PATIENT_STATUS")
            finally:
                os.chdir(prev)

    def test_startup_timeout_stays_terminal_after_process_exits(self):
        class Process:
            dead=False
            def poll(self):return None if not self.dead else -15
            def terminate(self):self.dead=True
        with tempfile.TemporaryDirectory() as folder:
            proc=Process()
            client._JOB.update(process=proc,job_dir=folder,started=time.perf_counter()-25)
            report=client.state()
            self.assertFalse(report["running"])
            self.assertTrue(report["error"])
            self.assertTrue(client._JOB["fallback_attempted"])
            with patch.object(client,"_launch_blender_fallback",
                              side_effect=AssertionError("unexpected fallback")):
                again=client.state()
            self.assertEqual(again["error"],report["error"])

    def test_fallback_restarts_elapsed_timer_and_forgets_stale_status(self):
        class Old:
            def poll(self):return 2
        class New:
            def poll(self):return None
        with tempfile.TemporaryDirectory() as folder:
            job=Path(folder)
            req=job/"request.json"
            req.write_text(json.dumps({"launcher_fallbacks":[]}))
            (job/"status.json").write_text(json.dumps({"phase":"OLD_WORKER"}))
            client._JOB.update(process=Old(),job_dir=folder,request_path=str(req),
                               started=time.perf_counter()-80,run_id="abc",
                               fallback_attempted=False,env={})
            with patch.object(client,"_launch_blender_fallback",return_value=New()):
                state=client.state()
            self.assertTrue(state["running"])
            self.assertFalse((job/"status.json").exists())
            self.assertLess(time.perf_counter()-client._JOB["started"],2)
            self.assertTrue(client._JOB["fallback_attempted"])


class FEMSafetyTests(unittest.TestCase):
    def test_buckling_uses_whole_member_not_discretization(self):
        nodes=[fem.Node([0,0,0],[True]*6),fem.Node([1.5,0,0],[False]*6)]
        short=fem.BeamElement(0,1,.6)
        long=fem.BeamElement(0,1,.6,buckling_length_mm=30.)
        u=np.zeros(12)
        u[6]=-0.01
        naive=fem._element_result(nodes,short,u)["buckling_ratio"]
        corrected=fem._element_result(nodes,long,u)["buckling_ratio"]
        self.assertGreater(naive,0)
        self.assertAlmostEqual(corrected/naive,(30/1.5)**2,places=5)

    def test_geodesic_beams_share_full_route_length(self):
        xyz=np.linspace(0,30,21)
        nodes=[fem.Node([0,0,0],[True]*6),
               fem.Node([30,0,0],[False]*6)]
        elements=[]
        ids=append_geodesic_beams(nodes,elements,[[x,0,0] for x in xyz],
                                  start_node=0,end_node=1,
                                  beam_template=fem.BeamElement(0,1,.6),
                                  label="LONG",max_segment_mm=1.51)
        self.assertEqual(len(ids),20)
        self.assertTrue(all(e.buckling_length_mm==30 for e in elements))

    def test_dense_large_fem_fails_before_matrix_allocation(self):
        with patch.object(fem,"_HAVE_SCIPY",False),patch.object(fem.np,"zeros",
                                                        side_effect=AssertionError("allocated")):
            nodes=[fem.Node([i,0,0],[False]*6) for i in range(401)]
            with self.assertRaisesRegex(fem.StructuralSolveError,"SPARSE_BACKEND"):
                fem.assemble_stiffness(nodes,[])

    def test_nonfinite_direct_solution_is_rejected(self):
        nodes=[fem.Node([0,0,0],[True]*6),
               fem.Node([1,0,0],[False]*6)]
        e=fem.BeamElement(0,1,1)
        with patch.object(fem,"_HAVE_SCIPY",False),patch.object(
                fem.np.linalg,"solve",return_value=np.full(6,np.nan)):
            with self.assertRaisesRegex(fem.StructuralSolveError,"NONFINITE"):
                fem.solve_load_cases(nodes,[e],[fem.LoadCase("nonfinite")],
                                     monitor_nodes=[1])


class BlenderGlueRegressionTests(unittest.TestCase):
    def function(self,path,name):
        tree=ast.parse((ROOT/path).read_text(encoding="utf-8"))
        return next(n for n in ast.walk(tree)
                    if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))
                    and n.name==name)

    def test_immediate_join_imports_dicom_runtime_explicitly(self):
        fn=self.function("cbct_dental_module.py","_join_immediate_arch_sources")
        self.assertTrue(any(isinstance(x,ast.ImportFrom)
                            and any(y.name=="dicom_module" for y in x.names)
                            for x in ast.walk(fn)))

    def test_immediate_join_rollback_on_second_model_failure(self):
        fn=self.function("cbct_dental_module.py","build_immediate_arch_composites")
        self.assertTrue(any(isinstance(x,ast.Try)
                            and any(isinstance(n,ast.Name) and n.id=="_delete_named_mesh"
                                    for h in x.handlers for n in ast.walk(h))
                            for x in ast.walk(fn)))

    def test_segment_auto_binds_scene_before_reading_route(self):
        fn=self.function("_dicom_parts/03_updates_segmentation.py",
                         "segment_tissue_automatically")
        self.assertTrue(any(isinstance(x,ast.Assign)
                            and any(isinstance(t,ast.Name) and t.id=="scene"
                                    for t in x.targets)
                            for x in fn.body))

    def test_undo_discovers_frame_private_classes(self):
        src=(ROOT/"workflow_history.py").read_text()
        self.assertIn("getattr(module,'_CLASSES',())",src)
        self.assertIn("lifecycle.cancel_module_timers(core.__name__)",src)

    def test_immediate_timer_is_managed_and_lock_survives_retry(self):
        fn=self.function("core.py","_deferred_launch")
        src=ast.unparse(fn)
        self.assertIn("retry_pending = True",src)
        self.assertIn("if not retry_pending:",src)
        start=self.function("core.py","execute")
        # Core has multiple execute functions; check complete source for the
        # explicit lifecycle timer registration, independent of AST traversal.
        src=(ROOT/"core.py").read_text()
        self.assertIn("lifecycle.register_timer(_deferred_launch",src)


if __name__=="__main__":
    unittest.main()
