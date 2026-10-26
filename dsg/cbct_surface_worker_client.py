"""Optional process-isolated client for DSG surface extraction.

The sidecar is intentionally opt-in (environment variable
``DSG_SURFACE_SIDECAR=1``). One native VTK pass is normally faster in-process;
forcing an external Blender is useful when isolation or UI/process resilience is
more important than startup overhead.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

import numpy as np


def sidecar_requested() -> bool:
    return str(os.environ.get("DSG_SURFACE_SIDECAR", "0")).strip().lower() in {"1", "true", "yes", "on"}


def extract_multilabel_sidecar(labels_crop, label_values, *, crop_origin_zyx, spacing_zyx):
    if not sidecar_requested():
        return None
    try:
        import bpy
    except Exception:
        return None
    binary = str(getattr(getattr(bpy, "app", None), "binary_path", "") or "")
    if not binary or not Path(binary).exists():
        return None

    from . import cbct_surface_meshing
    addon_dir = Path(__file__).resolve().parent
    addon_parent = addon_dir.parent
    worker = addon_dir / "cbct_surface_sidecar.py"
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="dsg_surface_sidecar_") as td:
        root = Path(td)
        labels_path = root / "labels.npy"
        output_path = root / "surface.npz"
        job_path = root / "job.json"
        np.save(labels_path, np.ascontiguousarray(labels_crop), allow_pickle=False)
        job = {
            "addon_parent": str(addon_parent),
            "labels_path": str(labels_path),
            "output_path": str(output_path),
            "labels": [int(v) for v in label_values],
            "crop_origin_zyx": [int(v) for v in crop_origin_zyx],
            "spacing_zyx": [float(v) for v in spacing_zyx],
        }
        job_path.write_text(json.dumps(job), encoding="utf-8")
        proc = subprocess.run(
            [binary, "--background", "--factory-startup", "--python", str(worker), "--", str(job_path)],
            capture_output=True, text=True, timeout=180,
        )
        if proc.returncode != 0 or not output_path.exists():
            raise RuntimeError((proc.stderr or proc.stdout or "surface sidecar failed")[-2000:])
        data = np.load(output_path, allow_pickle=False)
        meta = json.loads(str(data["meta_json"].item()))
        items = {}
        for label in meta.get("labels", []):
            label = int(label)
            topology = json.loads(str(data[f"t_{label}"].item()))
            items[label] = cbct_surface_meshing.LabelSurfaceExtraction(
                label=label,
                vertices_zyx=np.asarray(data[f"v_{label}"], dtype=np.float64),
                faces=np.asarray(data[f"f_{label}"], dtype=np.int32),
                topology=topology,
            )
        return cbct_surface_meshing.MultiLabelSurfaceExtraction(
            items=items,
            engine=str(meta.get("engine", "SIDECAR")) + "_SIDECAR",
            elapsed_s=float(time.perf_counter() - started),
            source_shape_zyx=tuple(int(v) for v in np.asarray(labels_crop).shape),
            crop_origin_zyx=tuple(int(v) for v in crop_origin_zyx),
            crop_shape_zyx=tuple(int(v) for v in np.asarray(labels_crop).shape),
            diagnostics={**dict(meta.get("diagnostics") or {}), "process_isolated": True},
            fallback_reason=str(meta.get("fallback_reason", "") or ""),
        )
