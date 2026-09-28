from __future__ import annotations

import logging as _dsg_logging
_DSG_LOG = _dsg_logging.getLogger(__name__)

import json
import pickle
import sys
import time
from pathlib import Path

def _status(path: Path, task: str, message: str):
    try:
        path.write_text(
            json.dumps(
                {"task": str(task), "message": str(message), "time": float(time.time())},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)

def _load_optional_npy(path_value):
    if not path_value:
        return None
    path = Path(str(path_value))
    if not path.is_file():
        return None
    import numpy as np
    return np.load(path, mmap_mode="r")

def main(argv=None):
    argv = list(sys.argv if argv is None else argv)
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = argv[1:]
    if not argv:
        raise SystemExit("Missing request json")
    request_path = Path(argv[0]).resolve()
    req = json.loads(request_path.read_text(encoding="utf-8"))
    output_dir = Path(req["output_dir"]).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    status_path = output_dir / "status.json"
    result_path = output_dir / "result.pkl"
    result_json = output_dir / "result.json"
    task = str(req.get("task") or "").strip().lower()

    runtime_site = str(req.get("runtime_site_packages") or "").strip()
    if runtime_site and runtime_site not in sys.path:
        sys.path.insert(0, runtime_site)

    addon_dir = Path(str(req.get("addon_dir") or "")).resolve()
    addon_parent = addon_dir.parent
    if str(addon_parent) not in sys.path:
        sys.path.insert(0, str(addon_parent))

    _status(status_path, task, "Importando módulos DSG…")
    import numpy as np
    from dsg import tooth_analysis, cbct_dental_module, dicom_module

    spacing_zyx = tuple(float(v) for v in (req.get("spacing_zyx") or (1.0, 1.0, 1.0)))
    labels = np.load(str(req["labels_path"]), mmap_mode="r")
    started = time.perf_counter()

    if task == "teeth":
        _status(status_path, task, "Copiando labelmap UniversalLab para reconciliación…")
        labels = np.array(labels, copy=True, order="C")
        upper_mask = _load_optional_npy(req.get("upper_support_mask_path"))
        lower_mask = _load_optional_npy(req.get("lower_support_mask_path"))
        upper_origin = tuple(int(v) for v in (req.get("upper_support_origin") or (0, 0, 0)))
        lower_origin = tuple(int(v) for v in (req.get("lower_support_origin") or (0, 0, 0)))

        _status(status_path, task, "Reconciliando continuidad corona-raíz…")
        path_started = time.perf_counter()
        path_stats = tooth_analysis.reconcile_universal_dentition_paths(
            np, labels, spacing_zyx,
            upper_support_mask=upper_mask, upper_support_origin=upper_origin,
            lower_support_mask=lower_mask, lower_support_origin=lower_origin,
        )
        path_s = float(time.perf_counter() - path_started)

        _status(status_path, task, "Extrayendo dientes full-resolution…")
        mesh_payload = cbct_dental_module.prepare_universal_dentition_meshes(labels)

        payload = {
            "task": "teeth",
            "path_stats": dict(path_stats or {}),
            "mesh_payload": mesh_payload,
            "labels": labels,
            "elapsed_s": float(time.perf_counter() - started),
            "timings": {
                "path_reconciliation_s": path_s,
                "mesh_prepare_s": float(mesh_payload.get("prepare_s", 0.0) or 0.0),
                "surface_extract_s": float(mesh_payload.get("surface_extract_s", 0.0) or 0.0),
            },
        }

    elif task == "surfaces":
        _status(status_path, task, "Preparando maxila, mandíbula y canal…")
        maxilla_semantic_mask = _load_optional_npy(req.get("maxilla_semantic_mask_path"))
        mandible_semantic_mask = _load_optional_npy(req.get("mandible_semantic_mask_path"))
        canal_verifier_mask = _load_optional_npy(req.get("canal_verifier_mask_path"))
        maxilla_semantic_origin = tuple(int(v) for v in (req.get("maxilla_semantic_origin") or (0, 0, 0)))
        mandible_semantic_origin = tuple(int(v) for v in (req.get("mandible_semantic_origin") or (0, 0, 0)))
        canal_verifier_origin = tuple(int(v) for v in (req.get("canal_verifier_origin") or (0, 0, 0)))
        canal_verifier_stats = dict(req.get("canal_verifier_stats") or {})

        u_max, u_max_origin = dicom_module._compact_mask_for_classes(labels, (54,))
        max_mask = u_max if u_max is not None and bool(u_max.any()) else maxilla_semantic_mask
        max_origin = u_max_origin if u_max is not None and bool(u_max.any()) else maxilla_semantic_origin
        max_class = 54 if u_max is not None and bool(u_max.any()) else 1
        max_source = "UNIVERSALLAB" if max_class == 54 else "DENTALSEGMENTATOR_8_7"

        u_man, u_man_origin = dicom_module._compact_mask_for_classes(labels, (53,))
        man_mask = u_man if u_man is not None and bool(u_man.any()) else mandible_semantic_mask
        man_origin = u_man_origin if u_man is not None and bool(u_man.any()) else mandible_semantic_origin
        man_class = 53 if u_man is not None and bool(u_man.any()) else 2
        man_source = "UNIVERSALLAB" if man_class == 53 else "DENTALSEGMENTATOR_8_7"

        surf_started = time.perf_counter()
        surfaces = {
            "maxilla": dicom_module._prepare_mask_surface_arrays(
                max_mask, max_origin, kind="JAW", label=max_class, max_axis=384, refine=True
            ),
            "mandible": dicom_module._prepare_mask_surface_arrays(
                man_mask, man_origin, kind="JAW", label=man_class, max_axis=384, refine=True
            ),
            "canal": dicom_module._prepare_canal_surface_arrays(
                labels,
                verifier_mask=canal_verifier_mask,
                verifier_origin=canal_verifier_origin,
                verifier_stats=canal_verifier_stats,
            ),
            "maxilla_class": int(max_class),
            "maxilla_source": str(max_source),
            "mandible_class": int(man_class),
            "mandible_source": str(man_source),
            "surface_prepare_s": float(time.perf_counter() - surf_started),
        }

        payload = {
            "task": "surfaces",
            "surfaces": surfaces,
            "elapsed_s": float(time.perf_counter() - started),
            "timings": {
                "surface_prepare_s": float(surfaces.get("surface_prepare_s", 0.0) or 0.0),
            },
        }
    else:
        raise RuntimeError(f"Tarea de postproceso desconocida: {task}")

    _status(status_path, task, "Guardando resultado…")
    with result_path.open("wb") as fh:
        pickle.dump(payload, fh, protocol=pickle.HIGHEST_PROTOCOL)
    result_json.write_text(
        json.dumps({"status": "OK", "task": task, "elapsed_s": float(time.perf_counter() - started)}, ensure_ascii=False),
        encoding="utf-8",
    )
    _status(status_path, task, "Listo")

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Try to recover output paths from argv.
        argv = sys.argv
        if "--" in argv:
            argv = argv[argv.index("--") + 1:]
        else:
            argv = argv[1:]
        output_dir = None
        try:
            if argv:
                req = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
                output_dir = Path(req["output_dir"]).resolve()
                output_dir.mkdir(parents=True, exist_ok=True)
                (output_dir / "result.json").write_text(
                    json.dumps({"status": "ERROR", "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False),
                    encoding="utf-8",
                )
                _status(output_dir / "status.json", str(req.get("task") or ""), f"Error: {type(exc).__name__}: {exc}")
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        raise
