"""Regression tests for the 9.5.8 TotalSegmentator single-source contract.

These tests are bpy-free.  They protect the cleanup that removed the duplicate
semantic/support labelmaps and make sure the compatibility map remains the only
postprocess source for teeth, jaws and mandibular canal.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1] / "dsg"


def _load_worker_module():
    spec = importlib.util.spec_from_file_location("dsg_cbct_pipeline_worker_pure", ROOT / "cbct_pipeline_worker.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_totalseg_translation_single_map_contains_all_clinical_classes():
    worker = _load_worker_module()
    raw = np.zeros((6, 6, 6), dtype=np.uint8)
    raw[0, 0, 0] = 1   # upper jaw
    raw[1, 1, 1] = 2   # lower jaw
    raw[2, 2, 2] = 3   # canal
    raw[3, 3, 3] = 4   # FDI 11
    classes = {
        1: "upper_jawbone",
        2: "lower_jawbone",
        3: "left_inferior_alveolar_canal",
        4: "tooth_fdi11",
    }
    compat, counts = worker._translate_totalseg(np, raw, classes)
    assert compat[0, 0, 0] == 54
    assert compat[1, 1, 1] == 53
    assert compat[2, 2, 2] == 55
    assert compat[3, 3, 3] == 8
    assert counts["tooth_fdi11"] == 1


def test_totalseg_translation_ignores_pulp_identity_as_tooth_surface():
    worker = _load_worker_module()
    raw = np.zeros((3, 3, 3), dtype=np.uint8)
    raw[1, 1, 1] = 7
    compat, _ = worker._translate_totalseg(np, raw, {7: "tooth_pulp_fdi11"})
    assert not compat.any()


def test_active_pipeline_has_no_orphan_support_labelmap_contract():
    worker_source = (ROOT / "cbct_pipeline_worker.py").read_text(encoding="utf-8")
    tasks_source = (ROOT / "cbct_pipeline_tasks.py").read_text(encoding="utf-8")
    forbidden = (
        "upper_support_path",
        "lower_support_path",
        "canal_support.npy",
        "totalseg_support_labels.npy",
        "canal_verifier_stats",
        "semantic_labels_path",
    )
    for token in forbidden:
        assert token not in worker_source
        assert token not in tasks_source


def test_teeth_task_does_not_write_duplicate_corrected_labelmap():
    source = (ROOT / "cbct_pipeline_tasks.py").read_text(encoding="utf-8")
    assert "open_memmap" not in source
    assert "corrected_path=Path(req['universal_labels_path']).resolve()" in source


def test_single_source_canal_refinement_preserves_original_voxels():
    import sys, types, importlib
    root = ROOT
    pkg = sys.modules.get("dsg")
    if pkg is None or not hasattr(pkg, "__path__"):
        pkg = types.ModuleType("dsg")
        pkg.__path__ = [str(root)]
        pkg.__package__ = "dsg"
        sys.modules["dsg"] = pkg
    tasks = importlib.import_module("dsg.cbct_pipeline_tasks")
    mask = np.zeros((9, 9, 9), dtype=bool)
    mask[4, 4, 2:7] = True
    refined, origin, meta = tasks.refine_single_source_canal(mask, (10, 20, 30), (0.3, 0.3, 0.3))
    assert refined.shape == mask.shape
    assert np.all(refined[mask])
    assert origin == (10, 20, 30)
    assert meta["independent_verifier"] is False
    assert meta["source"] == "TOTALSEGMENTATOR_SINGLE_SOURCE"
