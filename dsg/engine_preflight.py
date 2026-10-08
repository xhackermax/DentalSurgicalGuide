"""External Python check: imports, tensor operation and actual model loading.

No patient volume is read and no inference or download is performed.
"""
from pathlib import Path
import argparse
import json
import os
import sys
import time
import traceback

def validate(req, engine):
    root = Path(req["runtime_root"])
    sys.path.insert(0, str(req["site_packages"]))
    if engine == "TOOTHSEG":
        sys.path.insert(0, str(Path(req["repos_root"]) / "ToothSeg"))
    import torch
    torch.set_num_threads(max(1, min(4, os.cpu_count() or 1)))
    if not torch.equal(torch.ones(2) + 1, torch.tensor([2., 2.])):
        raise RuntimeError("PyTorch no supera la comprobación numérica")
    from nnunetv2.inference.predict_from_raw_data import nnUNetPredictor
    if engine == "TOTALSEG":
        from totalsegmentator.nnunet import nnUNet_predict_image
        from totalsegmentator.registry import get_task_classes
        if "lower_jawbone" not in get_task_classes("teeth").values():
            raise RuntimeError("El registro TotalSegmentator task=teeth no es compatible")
        models = Path(req["totalseg_results"])
        tokens, fold = ("Dataset113", "Dataset115"), 0
    elif engine == "TOOTHSEG":
        from toothseg.toothseg.postprocess_predictions.assign_mincost_tooth_labels import process_case
        from toothseg.toothseg.postprocess_predictions.border_core_to_instances import convert_all_sem_to_instance
        from toothseg.toothseg.postprocess_predictions.resize_predictions import resample_segmentations_to_ref
        models = Path(req["toothseg_results"])
        tokens, fold = ("Dataset121", "Dataset123"), 5
    else:
        raise RuntimeError("Preflight disponible para TotalSegmentator y ToothSeg")
    loaded = []
    for token in tokens:
        candidates = sorted(p for p in models.rglob("checkpoint_final.pth") if token.lower() in str(p).lower())
        candidates += sorted(p for p in models.rglob("checkpoint_best.pth") if token.lower() in str(p).lower())
        cp = next((p for p in candidates if p.stat().st_size >= 1_000_000 and p.parent.name == f"fold_{fold}"), None)
        if cp is None:
            raise RuntimeError(f"Falta un checkpoint válido {token}/fold_{fold}")
        model = cp.parent.parent
        if not (model / "plans.json").is_file() or not (model / "dataset.json").is_file():
            raise RuntimeError(f"Faltan plans.json o dataset.json para {token}")
        predictor = nnUNetPredictor(device=torch.device("cpu"), perform_everything_on_device=False, allow_tqdm=False)
        predictor.initialize_from_trained_model_folder(str(model), use_folds=(fold,), checkpoint_name=cp.name)
        smoke = False
        if torch.cuda.is_available():
            # Small synthetic tensor exercises the actual checkpoint on GPU.
            # It is a runtime check, not a clinical accuracy evaluation.
            predictor.network.to('cuda').eval()
            channels = len(predictor.dataset_json.get('channel_names', predictor.dataset_json.get('modality', {'0': 'CT'})))
            with torch.no_grad(), torch.autocast('cuda'):
                value = predictor.network(torch.zeros((1, channels, 64, 64, 64), device='cuda'))
            values = value if isinstance(value, (tuple, list)) else (value,)
            if not all(bool(torch.isfinite(item).all()) for item in values):
                raise RuntimeError(f'{token}: salida GPU no finita')
            smoke = True
            del value, values
        loaded.append({"dataset": token, "checkpoint": str(cp), "bytes": cp.stat().st_size, "gpu_forward_pass": smoke})
        del predictor
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    return {"ready": True, "engine": engine, "torch": torch.__version__, "cuda": torch.cuda.is_available(), "models_loaded": loaded, "time": time.time(), "python": sys.version}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("request")
    parser.add_argument("engine", choices=("TOTALSEG", "TOOTHSEG"))
    parser.add_argument("output")
    args = parser.parse_args()
    req = json.loads(Path(args.request).read_text(encoding="utf-8"))
    try:
        result = validate(req, args.engine)
    except Exception as exc:
        Path(args.output).write_text(json.dumps({"ready": False, "engine": args.engine, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False, indent=2), encoding="utf-8")
        raise
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("DSG_ENGINE_PREFLIGHT_PASS", args.engine, flush=True)

if __name__ == "__main__":
    main()
