from __future__ import annotations

"""External multi-engine CBCT worker for DSG 9.10 / Blender 5.2.

Every engine is reduced to the same DSG compatibility labelmap before any mesh
work begins. This makes TotalSegmentator, ToothSeg and U-Mamba2 directly
comparable on the same patient and through the same geometry pipeline.
"""

import importlib.util
import json
import logging
import os
import re
import sys
import threading
import time
import types
from pathlib import Path

_LOG = logging.getLogger("dsg.segmentation_worker")

try:
    from dsg import error_handling
except ImportError:
    import error_handling  # type: ignore


def atomic_json(path: Path, payload: dict) -> None:
    data = json.dumps(payload, ensure_ascii=False, default=str)
    for attempt in range(20):
        tmp = path.with_name(f"{path.name}.{os.getpid()}.{attempt}.tmp")
        try:
            tmp.write_text(data, encoding="utf-8")
            os.replace(tmp, path)
            return
        except PermissionError:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                _LOG.debug('No se pudo retirar el temporal de progreso',exc_info=True)
            time.sleep(0.05)
    path.write_text(data, encoding="utf-8")


def bootstrap(req: dict) -> None:
    addon = Path(req["addon_dir"]).resolve()
    parent = str(addon.parent)
    engine = str(req.get("engine") or "TOTALSEG").upper()
    runtime_paths = [str(p) for p in (req.get("engine_site_paths") or []) if p]
    if parent not in sys.path:
        sys.path.insert(0, parent)
    for p in reversed(runtime_paths):
        if p and p not in sys.path:
            sys.path.insert(0, p)
    vendor = str(req.get("dicom_vendor_dir") or "")
    if vendor and vendor not in sys.path:
        sys.path.insert(0, vendor)
    os.environ.update({str(k): str(v) for k, v in dict(req.get("engine_env") or {}).items()})
    py_path = os.pathsep.join(runtime_paths + [parent] + ([vendor] if vendor else []))
    if py_path:
        existing = os.environ.get("PYTHONPATH", "")
        os.environ["PYTHONPATH"] = py_path + (os.pathsep + existing if existing else "")
    if "dsg" not in sys.modules:
        pkg = types.ModuleType("dsg")
        pkg.__path__ = [str(addon)]
        pkg.__package__ = "dsg"
        sys.modules["dsg"] = pkg
    logical = max(1, int(os.cpu_count() or 1))
    threads = max(1, logical - 1)
    for key in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        os.environ[key] = str(threads)
    os.environ["DSG_WORKER_CPU_THREADS"] = str(threads)
    os.environ["DSG_SEGMENTATION_ENGINE"] = engine


def _fdi_to_compat(fdi: int) -> int | None:
    fdi = int(fdi)
    if 11 <= fdi <= 18:
        return 19 - fdi
    if 21 <= fdi <= 28:
        return fdi - 12
    if 31 <= fdi <= 38:
        return 55 - fdi
    if 41 <= fdi <= 48:
        return fdi - 16
    return None


def _toothseg_class_to_fdi(label: int) -> int | None:
    label = int(label)
    if 1 <= label <= 8:
        return label + 10
    if 9 <= label <= 16:
        return label + 12
    if 17 <= label <= 24:
        return label + 14
    if 25 <= label <= 32:
        return label + 16
    return None


def _make_affine(np, spacing_zyx, orientation_xyz, origin_lps):
    from dsg.pipeline_core import ContractError
    sz, sy, sx = (float(v) for v in spacing_zyx)
    if orientation_xyz is not None:
        orient = np.asarray(orientation_xyz, dtype=np.float64)
        if orient.shape!=(3,3) or not np.isfinite(orient).all() or abs(float(np.linalg.det(orient)))<1e-8:
            raise ContractError('dicom_orientation','orientación inválida o singular')
        if origin_lps is not None and (len(origin_lps)!=3 or not np.isfinite(origin_lps).all()):
            raise ContractError('dicom_orientation','origen inválido')
        if orient.shape == (3, 3):
            lps = np.eye(4, dtype=np.float64)
            lps[:3, 0] = orient[:, 0] * sx
            lps[:3, 1] = orient[:, 1] * sy
            lps[:3, 2] = orient[:, 2] * sz
            if origin_lps is not None and len(origin_lps) >= 3:
                lps[:3, 3] = np.asarray(origin_lps[:3], dtype=np.float64)
            return np.diag([-1.0, -1.0, 1.0, 1.0]) @ lps
    affine = np.eye(4, dtype=np.float64)
    affine[0, 0] = sx
    affine[1, 1] = sy
    affine[2, 2] = sz
    return affine


def _physical_fov_mm(dims_zyx, spacing_zyx):
    return tuple(float(dims_zyx[i]) * float(spacing_zyx[i]) for i in range(3))


def _direct113_supported(fov_mm) -> bool:
    try:
        return max(float(v) for v in fov_mm) <= 160.0
    except Exception:
        return False


def _predict_totalseg_direct(image, *, device: str, resamp_threads: int):
    import torch
    from totalsegmentator.config import setup_nnunet, setup_totalseg
    from totalsegmentator.nnunet import nnUNet_predict_image

    setup_nnunet()
    setup_totalseg()
    resolved = torch.device("cuda:0") if device == "gpu" else torch.device("cpu")
    seg, _ct, _stats = nnUNet_predict_image(
        image, None, 113,
        model="3d_lowres_high", folds=[0], trainer="nnUNetTrainer_onlyMirror01",
        tta=False, multilabel_image=True, resample=[0.5, 0.5, 0.5], crop=None,
        crop_path=None, task_name="teeth", output_task_name="teeth", nora_tag="None",
        preview=False, save_binary=False, nr_threads_resampling=max(1, int(resamp_threads)),
        nr_threads_saving=1, crop_addon=[0, 0, 0], output_type="nifti",
        statistics=False, quiet=True, verbose=False, test=0, skip_saving=True,
        device=resolved, resampling_order=1, save_lowres=False,
        use_cropped_logits_resampling=False,
    )
    return seg


def _translate_totalseg(np, labels_zyx, class_map):
    max_id = max((int(v) for v in class_map.keys()), default=0)
    lut = np.zeros(max_id + 1, dtype=np.uint8)
    names = {}
    for raw_id, name in class_map.items():
        raw_id = int(raw_id)
        name = str(name)
        names[raw_id] = name
        if name == "lower_jawbone":
            lut[raw_id] = 53
        elif name == "upper_jawbone":
            lut[raw_id] = 54
        elif name in {"left_inferior_alveolar_canal", "right_inferior_alveolar_canal"}:
            lut[raw_id] = 55
        elif "_pulp_" not in name:
            match = re.search(r"_fdi(\d+)$", name)
            if match:
                compat = _fdi_to_compat(int(match.group(1)))
                if compat:
                    lut[raw_id] = int(compat)
    arr = np.asarray(labels_zyx)
    if arr.dtype.kind not in 'iu' or (arr.size and (int(arr.min())<0 or int(arr.max())>max_id)):
        raise RuntimeError("TotalSegmentator devolvió clases fuera del registro task=teeth")
    compat = lut[arr.astype(np.int64, copy=False)]
    present,voxel_counts = np.unique(arr,return_counts=True)
    counts = {names[int(v)]: int(count) for v,count in zip(present,voxel_counts) if int(v) in names and int(v) != 0}
    return np.ascontiguousarray(compat, dtype=np.uint8), counts


def infer_totalseg(req, image, input_nifti: Path, np, nib, torch, status):
    from totalsegmentator.registry import get_task_classes
    device_pref = str(req.get("device_preference") or "AUTO").upper()
    device = "cpu" if device_pref == "CPU" else ("gpu" if torch.cuda.is_available() else "cpu")
    fov = _physical_fov_mm(req["dims_zyx"], req["spacing_zyx"])
    resamp_threads = 1 if os.name == "nt" else max(1, min(8, int(os.cpu_count() or 1) - 1))
    started = time.perf_counter()
    gpu_error = ""
    direct = _direct113_supported(fov)
    try:
        if direct:
            status("inference", f"TotalSegmentator Dataset113 directo · {device.upper()}…", 0.18)
            seg = _predict_totalseg_direct(image, device=device, resamp_threads=resamp_threads)
        else:
            status("inference", f"TotalSegmentator task=teeth con recorte automático · {device.upper()}…", 0.18)
            from totalsegmentator.python_api import totalsegmentator
            seg = totalsegmentator(
                input_nifti, None, task="teeth", ml=True, quiet=True,
                device=device, nr_thr_resamp=resamp_threads, nr_thr_saving=1,
                resampling_order=1,
            )
        used = device
    except Exception as exc:
        if device == "cpu":
            raise
        gpu_error = f"{type(exc).__name__}: {exc}"
        try:
            torch.cuda.empty_cache()
        except RuntimeError:
            _LOG.warning('No se pudo liberar la caché CUDA antes del fallback',exc_info=True)
        status("fallback", "CUDA falló · reintentando TotalSegmentator en CPU…", 0.20)
        if direct:
            seg = _predict_totalseg_direct(image, device="cpu", resamp_threads=resamp_threads)
        else:
            from totalsegmentator.python_api import totalsegmentator
            seg = totalsegmentator(
                input_nifti, None, task="teeth", ml=True, quiet=True,
                device="cpu", nr_thr_resamp=resamp_threads, nr_thr_saving=1,
                resampling_order=1,
            )
        used = "cpu"
    raw_xyz = np.asanyarray(seg.dataobj)
    expected_xyz = tuple(int(v) for v in image.shape)
    if tuple(raw_xyz.shape) != expected_xyz:
        raise RuntimeError(f"TotalSegmentator devolvió {tuple(raw_xyz.shape)} y se esperaba {expected_xyz}")
    raw_zyx = np.ascontiguousarray(np.transpose(raw_xyz, (2, 1, 0)))
    compat, counts = _translate_totalseg(np, raw_zyx, get_task_classes("teeth"))
    return compat, {
        "engine": "TotalSegmentator",
        "engine_id": "TOTALSEG",
        "task": "teeth",
        "device": used,
        "inference_s": float(time.perf_counter() - started),
        "mode": "DIRECT_DATASET113" if direct else "OFFICIAL_CROP_PIPELINE",
        "gpu_fallback_error": gpu_error,
        "class_voxels": counts,
        "capabilities": ["TEETH", "FDI", "JAW", "CANAL", "SINUS", "PULP", "IMPLANT", "CROWN", "BRIDGE"],
    }


def _find_model_folder(results_root: Path, dataset_token: str):
    candidates = []
    for name in ("checkpoint_best.pth", "checkpoint_final.pth"):
        for cp in results_root.rglob(name):
            if dataset_token.lower() not in str(cp).lower():
                continue
            if cp.parent.name.startswith("fold_"):
                fold = cp.parent.name.replace("fold_", "")
                candidates.append((cp.parent.parent, fold, cp.name, cp))
    if not candidates:
        raise RuntimeError(f"No se encontró checkpoint {dataset_token}")
    # Prefer the ToothSeg paper's fold_5, otherwise a fold_all, otherwise first.
    candidates.sort(key=lambda x: (0 if x[1] == "5" else 1 if x[1] == "all" else 2, str(x[3])))
    return candidates[0]


def _predict_nnunet_folder(model_folder: Path, fold: str, checkpoint: str, input_dir: Path, output_dir: Path, *, device, save_probabilities: bool):
    from nnunetv2.inference.predict_from_raw_data import nnUNetPredictor
    predictor = nnUNetPredictor(
        tile_step_size=0.5,
        use_gaussian=True,
        use_mirroring=True,
        perform_everything_on_device=(getattr(device, "type", "cpu") == "cuda"),
        device=device,
        verbose=False,
        verbose_preprocessing=False,
        allow_tqdm=False,
    )
    predictor.initialize_from_trained_model_folder(
        str(model_folder), use_folds=(fold,), checkpoint_name=checkpoint
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    predictor.predict_from_files(
        str(input_dir), str(output_dir),
        save_probabilities=bool(save_probabilities), overwrite=True,
        num_processes_preprocessing=1, num_processes_segmentation_export=1,
    )


def _resample_nifti_to_spacing(input_file: Path, output_file: Path, target_spacing=(0.2, 0.2, 0.2)):
    import SimpleITK as sitk
    image = sitk.ReadImage(str(input_file))
    spacing = image.GetSpacing()
    size = image.GetSize()
    new_size = [max(1, int(round(size[i] * spacing[i] / float(target_spacing[i])))) for i in range(3)]
    resampler = sitk.ResampleImageFilter()
    resampler.SetOutputSpacing(tuple(float(v) for v in target_spacing))
    resampler.SetSize(new_size)
    resampler.SetOutputDirection(image.GetDirection())
    resampler.SetOutputOrigin(image.GetOrigin())
    resampler.SetTransform(sitk.Transform())
    resampler.SetDefaultPixelValue(0)
    resampler.SetInterpolator(sitk.sitkLinear)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    sitk.WriteImage(resampler.Execute(image), str(output_file))


def infer_toothseg(req, input_nifti: Path, np, nib, torch, status):
    started = time.perf_counter()
    root = Path(req["job_dir"]) / "toothseg"
    input_dir = root / "imagesTs"
    resized_dir = root / "imagesTs_spacing02"
    sem_dir = root / "semantic"
    border_dir = root / "instance_border_core"
    inst_dir = root / "instances"
    inst_resized_dir = root / "instances_resized"
    final_dir = root / "final"
    for p in (input_dir, resized_dir, sem_dir, border_dir, inst_dir, inst_resized_dir, final_dir):
        p.mkdir(parents=True, exist_ok=True)
    case_file = input_dir / "DSGCASE_0000.nii.gz"
    if case_file.resolve() != input_nifti.resolve():
        import shutil
        shutil.copy2(input_nifti, case_file)
    resized_file = resized_dir / "DSGCASE_0000.nii.gz"
    status("toothseg_prepare", "ToothSeg · remuestreando rama de instancias a 0,2 mm…", 0.16)
    _resample_nifti_to_spacing(case_file, resized_file, (0.2, 0.2, 0.2))

    results = Path(dict(req.get("engine_env") or {})["nnUNet_results"])
    sem_model, sem_fold, sem_ckpt, _ = _find_model_folder(results, "Dataset121")
    inst_model, inst_fold, inst_ckpt, _ = _find_model_folder(results, "Dataset123")
    pref = str(req.get("device_preference") or "AUTO").upper()
    device = torch.device("cpu" if pref == "CPU" or not torch.cuda.is_available() else "cuda:0")
    status("toothseg_semantic", f"ToothSeg · rama semántica · {device.type.upper()}…", 0.24)
    _predict_nnunet_folder(sem_model, sem_fold, sem_ckpt, input_dir, sem_dir, device=device, save_probabilities=True)
    status("toothseg_instance", "ToothSeg · rama de instancias border-core…", 0.48)
    _predict_nnunet_folder(inst_model, inst_fold, inst_ckpt, resized_dir, border_dir, device=device, save_probabilities=False)

    status("toothseg_instances", "ToothSeg · separando instancias…", 0.64)
    from toothseg.toothseg.postprocess_predictions.border_core_to_instances import convert_all_sem_to_instance
    convert_all_sem_to_instance(str(border_dir), str(inst_dir), num_processes=1, overwrite=True)

    status("toothseg_resize", "ToothSeg · devolviendo instancias a la rejilla CBCT…", 0.70)
    from toothseg.toothseg.postprocess_predictions.resize_predictions import resample_segmentations_to_ref
    resample_segmentations_to_ref(
        str(input_dir), str(inst_dir), str(inst_resized_dir), overwrite=True,
        num_threads_cpu_resampling=max(1, min(8, int(os.cpu_count() or 1))),
        threads_loading=1, threads_saving=1,
    )

    status("toothseg_fdi", "ToothSeg · autocorrección FDI por coste mínimo…", 0.76)
    from scipy.stats import multivariate_normal
    from toothseg.toothseg.postprocess_predictions.assign_mincost_tooth_labels import process_case
    repo = Path(req["toothseg_repo"])
    distributions = repo / "toothseg" / "datasets" / "toothfairy2" / "fdi_pair_distrs.json"
    pair_dists = json.loads(distributions.read_text(encoding="utf-8"))
    normals = []
    for i in range(32):
        row = []
        for j in range(32):
            if i // 16 != j // 16:
                row.append(None)
            else:
                row.append(multivariate_normal(
                    mean=pair_dists["means"][i][j][:2],
                    cov=np.asarray(pair_dists["covs"][i][j], dtype=np.float64)[:2, :2],
                ))
        normals.append(row)
    inst_file = inst_resized_dir / "DSGCASE.nii.gz"
    if not inst_file.is_file():
        candidates = sorted(inst_resized_dir.glob("*.nii.gz"))
        if not candidates:
            raise RuntimeError("ToothSeg no produjo instancias remuestreadas")
        inst_file = candidates[0]
    process_case(sem_dir, final_dir, normals, True, inst_file)
    final_file = final_dir / inst_file.name
    final_img = nib.load(str(final_file))
    class_xyz = np.asanyarray(final_img.dataobj).astype(np.uint8, copy=False)
    class_zyx = np.ascontiguousarray(np.transpose(class_xyz, (2, 1, 0)))
    compat = np.zeros(class_zyx.shape, dtype=np.uint8)
    for cls in range(1, 33):
        fdi = _toothseg_class_to_fdi(cls)
        ul = _fdi_to_compat(fdi) if fdi else None
        if ul:
            compat[class_zyx == cls] = int(ul)
    if not np.any((compat >= 1) & (compat <= 32)):
        raise RuntimeError("ToothSeg no devolvió dientes FDI válidos")
    return compat, {
        "engine": "ToothSeg",
        "engine_id": "TOOTHSEG",
        "device": device.type,
        "inference_s": float(time.perf_counter() - started),
        "semantic_model": str(sem_model),
        "instance_model": str(inst_model),
        "capabilities": ["TEETH", "FDI", "INSTANCE"],
        "teeth_only": True,
    }


def _load_module_from_file(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"No se puede cargar {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _find_umamba_model(req):
    root = Path(req["umamba2_models"])
    candidates = []
    for name in ("checkpoint_best.pth", "checkpoint_final.pth"):
        for cp in root.rglob(name):
            if cp.parent.name.startswith("fold_") and cp.stat().st_size >= 1_000_000:
                candidates.append((cp.parent.parent, cp.parent.name.replace("fold_", ""), cp.name, cp))
    if not candidates:
        raise RuntimeError(
            "U-Mamba2 no tiene checkpoint final de segmentación. Los pesos SSL de preentrenamiento no son inferibles."
        )
    candidates.sort(key=lambda x: (0 if x[1] == "all" else 1, str(x[3])))
    return candidates[0]


def infer_umamba2(req, input_nifti: Path, np, nib, torch, status):
    started = time.perf_counter()
    repo = Path(req["umamba2_repo"])
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    # The U-Mamba2 repo is a fork of nnU-Net and must win module resolution in
    # this dedicated worker process. No other engine runs in this process.
    for key in [k for k in list(sys.modules) if k == "nnunetv2" or k.startswith("nnunetv2.")]:
        del sys.modules[key]
    status("umamba_load", "U-Mamba2 · cargando arquitectura y checkpoint…", 0.18)
    module = _load_module_from_file(
        "dsg_umamba2_task1",
        repo / "documentation" / "competitions" / "Toothfairy3" / "task1_inference.py",
    )
    model_dir, fold, checkpoint_name, checkpoint_path = _find_umamba_model(req)
    pref = str(req.get("device_preference") or "AUTO").upper()
    device = torch.device("cpu" if pref == "CPU" or not torch.cuda.is_available() else "cuda:0")
    mapping = [(3, 4), (5, 6), (43, 44)]
    for l, r in zip(range(19, 27), range(11, 19)):
        mapping.append((l, r))
    for l, r in zip(range(27, 35), range(35, 43)):
        mapping.append((l, r))
    predictor = module.BasePredictor(
        tile_step_size=0.95,
        use_mirroring=True,
        use_gaussian=True,
        perform_everything_on_device=(device.type == "cuda"),
        allow_tqdm=False,
        tta_batch_size=1,
        lr_mapping=mapping,
        n_class=47,
        verbose=False,
        device=device,
    )
    predictor.initialize_from_trained_model_folder(
        str(model_dir), use_folds=(fold,), checkpoint_name=checkpoint_name
    )
    status("umamba_inference", f"U-Mamba2 ToothFairy3 · {device.type.upper()}…", 0.30)
    rw = module.SimpleITKIO()
    image_arr, prop = rw.read_images([input_nifti])
    with torch.no_grad():
        raw = module.predict_semseg(image_arr, prop, predictor)
    raw = np.asarray(raw, dtype=np.uint8)
    compat = np.zeros(raw.shape, dtype=np.uint8)
    compat[raw == 1] = 53
    compat[raw == 2] = 54
    compat[(raw == 3) | (raw == 4)] = 55
    for fdi in list(range(11, 19)) + list(range(21, 29)) + list(range(31, 39)) + list(range(41, 49)):
        ul = _fdi_to_compat(fdi)
        if ul:
            compat[raw == fdi] = int(ul)
    if tuple(compat.shape) != tuple(int(v) for v in req["dims_zyx"]):
        # SimpleITKIO returns Z,Y,X; this is the desired DSG order. Be explicit.
        raise RuntimeError(f"U-Mamba2 devolvió {tuple(compat.shape)} y se esperaba {tuple(req['dims_zyx'])}")
    if not np.any((compat >= 1) & (compat <= 32)):
        raise RuntimeError("U-Mamba2 no devolvió dientes FDI válidos")
    return np.ascontiguousarray(compat), {
        "engine": "U-Mamba2",
        "engine_id": "UMAMBA2",
        "device": device.type,
        "inference_s": float(time.perf_counter() - started),
        "checkpoint": str(checkpoint_path),
        "capabilities": ["TEETH", "FDI", "JAW", "CANAL", "SINUS", "PULP"],
        "experimental": True,
    }


def main(trace=None,stop_event=None):
    req_path = Path(sys.argv[-1]).resolve()
    req = json.loads(req_path.read_text(encoding="utf-8"))
    job = Path(req["job_dir"]).resolve()
    job.mkdir(parents=True, exist_ok=True)
    status_path = job / "status.json"
    manifest_path = job / "manifest.json"
    t0 = time.perf_counter()
    lock = threading.Lock()
    stop = stop_event or threading.Event()
    live = {"phase": "bootstrap", "message": "Worker iniciado", "factor": 0.01}

    def status(phase, message, factor, extra=None):
        if trace is not None:
            trace.start(str(phase))
            _LOG.info('phase=%s',phase)
            if phase=='fallback':trace.fallback('TOTALSEG_GPU','TOTALSEG_CPU','CUDA_FAILURE')
        with lock:
            live.update(phase=str(phase), message=str(message), factor=float(factor))
            payload = {
                "status": "RUNNING", "phase": str(phase), "message": str(message),
                "factor": float(factor), "elapsed_s": float(time.perf_counter() - t0),
                "engine": str(req.get("engine") or "TOTALSEG"), "time": time.time(),
                "run_id":str(req.get('run_id','')),
            }
            if extra:
                payload.update(extra)
            atomic_json(status_path, payload)

    def heartbeat():
        while not stop.wait(2.0):
            with lock:
                atomic_json(status_path, {
                    "status": "RUNNING", "phase": live["phase"], "message": live["message"],
                    "factor": live["factor"], "elapsed_s": float(time.perf_counter() - t0),
                    "engine": str(req.get("engine") or "TOTALSEG"), "heartbeat": True, "time": time.time(),
                    "run_id":str(req.get('run_id','')),
                })

    status("bootstrap", "Worker externo de segmentación iniciado…", 0.01)
    bootstrap(req)
    threading.Thread(target=heartbeat, daemon=True, name="DSG-Segmentation-Heartbeat").start()

    status("runtime", "Cargando NumPy/NIfTI/PyTorch…", 0.04)
    import numpy as np
    import nibabel as nib
    import torch
    from dsg import cbct_pipeline_tasks

    logical = max(1, int(os.cpu_count() or 1))
    try:
        torch.set_num_threads(max(1, logical - 1))
    except RuntimeError:
        _LOG.warning('No se pudo configurar la cantidad de hilos Torch',exc_info=True)
    if torch.cuda.is_available():
        try:
            torch.backends.cudnn.benchmark = True
            if hasattr(torch.backends.cuda.matmul, "allow_tf32"):
                torch.backends.cuda.matmul.allow_tf32 = True
            if hasattr(torch.backends.cudnn, "allow_tf32"):
                torch.backends.cudnn.allow_tf32 = True
        except (RuntimeError,AttributeError):
            _LOG.warning('No se pudo configurar la optimización CUDA',exc_info=True)

    volume = np.load(req["volume_path"], mmap_mode="r")
    slopes = np.load(req["slopes_path"], mmap_mode="r")
    intercepts = np.load(req["intercepts_path"], mmap_mode="r")
    spacing = tuple(float(v) for v in req["spacing_zyx"])
    dims = tuple(int(v) for v in req["dims_zyx"])
    signature = str(req["source_signature"])
    route_mode = str(req.get("route_mode") or "FULL").upper()
    engine = str(req.get("engine") or "TOTALSEG").upper()
    from dsg.pipeline_core import VolumeInput,Labelmap

    status("input", "Calibrando CBCT y construyendo NIfTI común…", 0.08)
    VolumeInput.parse(volume,slopes,intercepts,dims,spacing)
    calibrated = np.asarray(volume, dtype=np.float32).copy()
    calibrated *= np.asarray(slopes, dtype=np.float32)[:, None, None]
    calibrated += np.asarray(intercepts, dtype=np.float32)[:, None, None]
    xyz = np.ascontiguousarray(np.transpose(calibrated, (2, 1, 0)))
    del calibrated
    affine = _make_affine(np, spacing, req.get("orientation_xyz"), req.get("image_origin_patient"))
    image = nib.Nifti1Image(xyz, affine)
    input_nifti = job / "input_cbct.nii.gz"
    nib.save(image, str(input_nifti))

    status("engine", f"Cargando {engine}…", 0.12)
    if engine == "TOTALSEG":
        labels, metadata = infer_totalseg(req, image, input_nifti, np, nib, torch, status)
    elif engine == "TOOTHSEG":
        labels, metadata = infer_toothseg(req, input_nifti, np, nib, torch, status)
    elif engine == "UMAMBA2":
        labels, metadata = infer_umamba2(req, input_nifti, np, nib, torch, status)
    else:
        raise RuntimeError(f"Motor desconocido: {engine}")
    if trace is not None:
        trace.payload['engine_metadata']={'device':str(metadata.get('device') or 'unknown')}
        trace.write()
    del xyz, image

    status('labelmap','Comprobando el contrato de salida del motor…',0.79)
    labelmap=Labelmap.parse(labels,dims,spacing,engine)

    status("normalize", "Salida normalizada · preparando geometría común DSG…", 0.80)
    normalized_path = job / f"{engine.lower()}_normalized_labels.npy"
    np.save(str(normalized_path), np.ascontiguousarray(labels, dtype=np.uint8), allow_pickle=False)

    if route_mode == "SIMPLE_ARCHES":
        if engine == "TOOTHSEG":
            raise RuntimeError("ToothSeg sólo segmenta dientes; la ruta de dos arcadas para implantes necesita maxila/mandíbula")
        simple_dir = job / "simple_arches"
        simple_dir.mkdir(exist_ok=True)
        simple = cbct_pipeline_tasks.prepare_simple_arches(
            labels, spacing, dims, simple_dir,
            lambda m: status("simple_arches", str(m), 0.90),
        )
        timings = {
            "engine_inference_s": float(metadata.get("inference_s", 0.0)),
            "simple_surface_s": float(simple.get("surface_prepare_s", 0.0)),
            "total_external_s": float(time.perf_counter() - t0),
        }
        manifest = {
            'schema_version':1,'run_id':req['run_id'],'labelmap_contract':labelmap.summary(),
            "status": "OK", "source_signature": signature, "route_mode": "SIMPLE_ARCHES",
            "simple_arches": True, "normalized_labels_path": str(normalized_path),
            "universal_labels_path": str(normalized_path), "prepared_surfaces": simple,
            "prepared_meshes": {}, "path_stats": {},
            "semantic_info": {"identity_exposed": False, "route": "SIMPLE_ARCHES"},
            "semantic_metadata": metadata, "universal_metadata": metadata,
            "timings": timings, "segmentation_engine": metadata.get("engine", engine),
            "engine_id": engine, "capabilities": metadata.get("capabilities", []),
        }
        atomic_json(manifest_path, manifest)
        status("ready", f"{metadata.get('engine', engine)} terminado · dos arcadas listas", 0.98, {"done": True})
        stop.set()
        return

    status("meshes", "Preparando dientes FDI…", 0.84)
    teeth_dir = job / "teeth_task"
    teeth_req = {
        "task": "teeth", "output_dir": str(teeth_dir),
        "spacing_zyx": list(spacing), "dims_zyx": list(dims),
        "normalized_labels_path": str(normalized_path),
        "engine_id": engine, "segmentation_engine": str(metadata.get("engine", engine)),
    }
    teeth = cbct_pipeline_tasks.run_teeth_task(
        teeth_req, lambda m: status("meshes", str(m), 0.88)
    )

    surfaces = {"prepared_surfaces": {}, "elapsed_s": 0.0}
    if "JAW" in set(metadata.get("capabilities") or []):
        status("surfaces", "Preparando maxila, mandíbula y canal…", 0.91)
        surf_dir = job / "surfaces_task"
        surf_req = {
            "task": "surfaces", "output_dir": str(surf_dir),
            "spacing_zyx": list(spacing), "dims_zyx": list(dims),
            "normalized_labels_path": str(normalized_path),
            "engine_id": engine, "segmentation_engine": str(metadata.get("engine", engine)),
        }
        surfaces = cbct_pipeline_tasks.run_surfaces_task(
            surf_req, lambda m: status("surfaces", str(m), 0.94)
        )

    timings = {
        "engine_inference_s": float(metadata.get("inference_s", 0.0)),
        "tooth_mesh_s": float(teeth.get("elapsed_s", 0.0)),
        "surface_mesh_s": float(surfaces.get("elapsed_s", 0.0)),
        "total_external_s": float(time.perf_counter() - t0),
    }
    manifest = {
        'schema_version':1,'run_id':req['run_id'],'labelmap_contract':labelmap.summary(),
        "status": "OK", "source_signature": signature,
        "normalized_labels_path": str(normalized_path),
        # Compatibility key retained only at the manifest boundary so existing
        # Blender mesh import code can migrate without duplicating the labelmap.
        "universal_labels_path": str(normalized_path),
        "path_stats": teeth.get("path_stats") or {},
        "semantic_info": teeth.get("semantic_info") or {},
        "prepared_meshes": teeth.get("prepared_meshes") or {},
        "prepared_surfaces": surfaces.get("prepared_surfaces") or {},
        "semantic_metadata": metadata, "universal_metadata": metadata,
        "timings": timings, "segmentation_engine": metadata.get("engine", engine),
        "engine_id": engine, "capabilities": metadata.get("capabilities", []),
        "teeth_only": bool(metadata.get("teeth_only", False)),
    }
    atomic_json(manifest_path, manifest)
    status("ready", f"{metadata.get('engine', engine)} terminado · listo para importar", 0.98, {"done": True})
    stop.set()


def run_request():
    import hashlib
    req=json.loads(Path(sys.argv[-1]).read_text(encoding='utf-8'))
    bootstrap(req)
    from dsg.pipeline_core import RunTrace
    from dsg.pipeline_core import ContractError
    from dsg.version import DSG_VERSION_STR
    trace=RunTrace(req.get('diagnostic_path') or Path(req['job_dir'])/'diagnostic.json',req['run_id'],DSG_VERSION_STR,
                   str(req.get('engine') or 'TOTALSEG'),{'dims_zyx':req['dims_zyx'],'spacing_zyx':req['spacing_zyx'],
                   'source_hash':hashlib.sha256(str(req.get('source_signature','')).encode()).hexdigest()})
    for event in req.get('launcher_fallbacks',[]):trace.fallback('PYTHON_WORKER','BLENDER_WORKER',event)
    stop=threading.Event()
    try:
        if req.get('schema_version')!=1:raise ContractError('request','versión incompatible')
        logging.basicConfig(level=logging.INFO,format=f"%(asctime)s [run={req['run_id']}] %(name)s %(levelname)s %(message)s")
        main(trace,stop);trace.finish()
    except Exception as exc:  # subprocess boundary: persist evidence and propagate
        trace.fail(exc);raise
    finally:stop.set()

if __name__ == "__main__":
    try:
        run_request()
    except Exception as exc:
        try:
            req = json.loads(Path(sys.argv[-1]).read_text(encoding="utf-8"))
            job = Path(req["job_dir"])
            job.mkdir(parents=True, exist_ok=True)
            error_handling.log_exception(_LOG, "DSG-E230", exc, context={"phase": "worker_main"})
            message = error_handling.redact(f"{type(exc).__name__}: {exc}")
            atomic_json(job / "manifest.json", {"schema_version":1,'run_id':req.get('run_id',''),"status": "ERROR", "code": "DSG-E230", "error": message})
            atomic_json(job / "status.json", {
                "status": "ERROR", "phase": "error", "message": message,
                "factor": 0.02, "engine": str(req.get("engine") or ""), "time": time.time(),
            })
        except (OSError,ValueError,KeyError) as diagnostic_error:
            error_handling.log_exception(_LOG,'DSG-E900',diagnostic_error,context={'phase':'write_error_evidence'})
        raise
