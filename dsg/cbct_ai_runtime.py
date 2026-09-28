"""DSG 9.5 compatibility facade.

The historical CBCT AI runtime was removed.  TotalSegmentator is the only
segmentation engine in DSG 9.5.  This module remains only because some older
DSG UI/diagnostic code imports its public names.  It does not contain a neural
network, checkpoint loader, predictor, or legacy segmenter.
"""
from __future__ import annotations

import logging as _dsg_logging
_DSG_LOG = _dsg_logging.getLogger(__name__)
import os
from dataclasses import dataclass
from pathlib import Path
from . import totalseg_runtime as _ts

PACKAGED_SEMANTIC_MODEL = Path(__file__).resolve().parent / "_removed_legacy_model"

@dataclass(frozen=True)
class RuntimeStatus:
    dependencies_ready: bool
    semantic_model_ready: bool
    universal_model_ready: bool
    device: str
    cuda_available: bool = False
    gpu_name: str = ""
    cuda_runtime: str = ""
    vram_free_gb: float = 0.0
    vram_total_gb: float = 0.0
    detail: str = ""


def quick_status():
    s=_ts.quick_status(); return RuntimeStatus(s.dependencies_ready,s.model_ready,s.model_ready,s.device,s.device=="CUDA","NVIDIA GPU" if s.device=="CUDA" else "","",0.0,0.0,s.error)
def runtime_status(): return quick_status()
def install_state(): return _ts.install_state()
def _nvidia_driver_present(): return _ts._nvidia_driver_present()
def _prepend_runtime_paths(): return _ts._prepend_paths()
def runtime_site_packages(): return _ts.runtime_site_packages()
def active_runtime_site_packages(): return os.pathsep.join(_ts.active_site_paths())
def semantic_model_dir(): return _ts.totalseg_home()
def universal_model_dir(): return _ts.totalseg_home()
def _user_semantic_model_dir(): return _ts.totalseg_home()
def _user_universal_model_dir(): return _ts.totalseg_home()
def _packaged_universal_model_dir(): return _ts.totalseg_home()
def universal_model_ready(): return _ts.quick_status().model_ready
def _universal_candidate_ready(path): return _ts.quick_status().model_ready
def dependency_diagnostics(): return _ts.dependency_diagnostics()
def model_metadata(kind="universal"): return {"engine":"TotalSegmentator","task":"teeth","version":_ts.TOTALSEG_VERSION,"compat_kind":str(kind)}
def last_performance_plan(): return _ts.last_performance_plan()
def shutdown_persistent_worker(force=False): return None
def clear_predictor_cache():
    try:
        _prepend_runtime_paths(); import torch
        if torch.cuda.is_available(): torch.cuda.empty_cache()
    except Exception: _DSG_LOG.debug("suppressed exception", exc_info=True)

def prediction_job_state(include_result=True): return {"running":False,"done":False,"message":"DSG 9.5 usa TotalSegmentator en el pipeline externo","error":""}
def consume_prediction_result(): return None
def cancel_parallel_dual_jobs(): return None

def _legacy_disabled(*args,**kwargs):
    raise RuntimeError("Ruta IA heredada desactivada en DSG 9.5. Usa el pipeline externo TotalSegmentator task=teeth.")
_start_prediction_job_inprocess=_legacy_disabled
predict_volume=_legacy_disabled

def build_inference_plan(*args,**kwargs): return {"engine":"TotalSegmentator","task":"teeth","mode":"EXTERNAL","actual_mode":"EXTERNAL_TOTALSEGMENTATOR"}
def _enable_disk_accumulator_if_needed(plan,*args,**kwargs): return dict(plan or {}),True,0,0

def restore_crop(labels,full_shape,crop_slices):
    import numpy as np
    if tuple(getattr(labels,"shape",()))==tuple(int(v) for v in full_shape): return labels
    out=np.zeros(tuple(int(v) for v in full_shape),dtype=getattr(labels,"dtype",np.uint8)); out[crop_slices]=labels; return out

def _dental_roi_from_semantic(labels,spacing_zyx,margin_mm=28.0):
    import numpy as np
    arr=np.asarray(labels); mask=(arr==3)|(arr==4)
    coords=np.argwhere(mask)
    if coords.size==0: return None,{"valid":False,"reason":"no_teeth"}
    lo=coords.min(axis=0); hi=coords.max(axis=0)+1
    spacing=np.asarray(tuple(float(v) for v in spacing_zyx)); margin=np.maximum(1,np.ceil(float(margin_mm)/np.maximum(spacing,1e-6)).astype(int))
    lo=np.maximum(0,lo-margin); hi=np.minimum(np.asarray(arr.shape),hi+margin)
    sl=tuple(slice(int(lo[i]),int(hi[i])) for i in range(3))
    return sl,{"valid":True,"engine":"TotalSegmentator","origin_zyx":[int(v) for v in lo],"shape_zyx":[int(hi[i]-lo[i]) for i in range(3)]}

def calibrate_and_autocrop(volume,slopes,intercepts,*args,**kwargs):
    import numpy as np
    arr=np.asarray(volume,dtype=np.float32).copy(); arr*=np.asarray(slopes,dtype=np.float32)[:,None,None]; arr+=np.asarray(intercepts,dtype=np.float32)[:,None,None]
    sl=tuple(slice(0,int(v)) for v in arr.shape); return arr,sl,{"engine":"TotalSegmentator","crop":"none_legacy_facade"}

def _import_runtime_stack():
    _prepend_runtime_paths(); import torch; from totalsegmentator.python_api import totalsegmentator; return torch,totalsegmentator

def install_all(*args,**kwargs):
    if not _ts.start_install(): return _ts.install_state()
    return _ts.install_state()
def _pip_install_runtime(*args,**kwargs): return install_all(*args,**kwargs)
def recover_universal_model_to_current(*args,**kwargs): return _ts.start_install()
def _set_install_state(**kwargs): return None
