from pathlib import Path
import ast
import numpy as np


def _load_tasks_without_package_import():
    # Importing dsg normally requires bpy. Execute the pure helper source with
    # tiny stubs for its two relative modules.
    import types, sys
    base = Path(__file__).resolve().parents[1] / "dsg"
    pkg = types.ModuleType("dsg"); pkg.__path__=[str(base)]; sys.modules.setdefault("dsg", pkg)
    ta=types.ModuleType("dsg.tooth_analysis"); ta.universal_to_fdi=lambda *a,**k: None; sys.modules["dsg.tooth_analysis"]=ta
    sm=types.ModuleType("dsg.cbct_surface_meshing"); sys.modules["dsg.cbct_surface_meshing"]=sm
    ns={"__name__":"dsg.cbct_pipeline_tasks","__package__":"dsg"}
    exec(compile((base/"cbct_pipeline_tasks.py").read_text("utf-8"), str(base/"cbct_pipeline_tasks.py"), "exec"), ns)
    return ns


def test_simple_arch_masks_are_exactly_upper_and_lower_without_canal():
    ns=_load_tasks_without_package_import()
    labels=np.zeros((4,5,6),dtype=np.uint8)
    labels[0,0,0]=54; labels[0,0,1]=1; labels[0,0,2]=16
    labels[3,4,5]=53; labels[3,4,4]=17; labels[3,4,3]=32
    labels[2,2,2]=55
    upper,uo,lower,lo=ns["simple_arch_masks"](labels)
    assert int(upper.sum())==3
    assert int(lower.sum())==3
    assert 55 not in ns["UPPER_SIMPLE_CLASSES"] and 55 not in ns["LOWER_SIMPLE_CLASSES"]


def test_simple_worker_skips_fdi_child_workers():
    src=(Path(__file__).resolve().parents[1]/"dsg"/"cbct_pipeline_worker.py").read_text("utf-8")
    assert "if route_mode == 'SIMPLE_ARCHES':" in src
    simple=src.split("if route_mode == 'SIMPLE_ARCHES':",1)[1].split("# FULL/IMMEDIATE",1)[0]
    assert "prepare_simple_arches" in simple
    assert "teeth_request.json" not in simple
    assert "surfaces_request.json" not in simple
    assert "totalseg_compat_labels.npy" not in simple


def test_simple_translation_collapses_directly_to_two_arches_without_fdi_or_canal():
    import importlib.util, sys
    base = Path(__file__).resolve().parents[1] / "dsg"
    p = base / "cbct_pipeline_worker.py"
    spec = importlib.util.spec_from_file_location("dsg_simple_worker_pure", p)
    mod = importlib.util.module_from_spec(spec); sys.modules[spec.name] = mod; spec.loader.exec_module(mod)
    raw = np.array([[[1, 2, 3, 4, 5]]], dtype=np.uint8)
    classes = {
        1: "upper_jawbone",
        2: "lower_jawbone",
        3: "tooth_example_fdi11",
        4: "tooth_example_fdi47",
        5: "left_inferior_alveolar_canal",
    }
    route, counts = mod._translate_totalseg_simple_arches(np, raw, classes)
    assert route.tolist() == [[[1, 2, 1, 2, 0]]]
    assert counts == {"upper_voxels": 2, "lower_voxels": 2}
