"""DSG v9.2.64 optional process-isolated surface worker.

This script is launched by a background Blender process only when explicitly
requested by the surface worker client. It never creates Blender datablocks.
The default clinical fast path stays in-process because process startup and IPC
can be slower than one native VTK multi-label pass; the sidecar exists for very
large cases and isolation/debug workloads.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys


def _arg_job_path() -> Path:
    args = list(sys.argv)
    if "--" in args:
        args = args[args.index("--") + 1:]
    if not args:
        raise RuntimeError("Falta job.json")
    return Path(args[0]).resolve()


def main() -> int:
    job_path = _arg_job_path()
    job = json.loads(job_path.read_text(encoding="utf-8"))
    addon_parent = str(job["addon_parent"])
    if addon_parent not in sys.path:
        sys.path.insert(0, addon_parent)

    import numpy as np
    import dsg.cbct_ai_runtime as runtime
    runtime._prepend_runtime_paths()
    import importlib
    importlib.invalidate_caches()
    import dsg.cbct_surface_meshing as meshing

    try:
        import vtk
    except Exception:
        vtk = None
    try:
        from skimage import measure
    except Exception:
        measure = None

    labels = np.load(job["labels_path"], mmap_mode="r")
    result = meshing.extract_multilabel_surface(
        labels,
        [int(v) for v in job["labels"]],
        crop_origin_zyx=tuple(int(v) for v in job["crop_origin_zyx"]),
        vtk_module=vtk,
        skimage_measure=measure,
        spacing_zyx=tuple(float(v) for v in job["spacing_zyx"]),
    )
    payload = {
        "engine": result.engine,
        "elapsed_s": result.elapsed_s,
        "fallback_reason": result.fallback_reason,
        "diagnostics": result.diagnostics or {},
        "labels": sorted(int(v) for v in result.items),
    }
    arrays = {"meta_json": np.asarray(json.dumps(payload, ensure_ascii=False))}
    for label, item in result.items.items():
        arrays[f"v_{int(label)}"] = np.asarray(item.vertices_zyx, dtype=np.float32)
        arrays[f"f_{int(label)}"] = np.asarray(item.faces, dtype=np.int32)
        arrays[f"t_{int(label)}"] = np.asarray(json.dumps(item.topology, ensure_ascii=False))
    np.savez(job["output_path"], **arrays)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
