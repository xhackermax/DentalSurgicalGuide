from __future__ import annotations

"""DSG 9.10 multi-engine runtime manager for Blender 5.2 only.

This module is intentionally light-weight: UI/status checks never import torch.
The heavy numerical stacks live in an isolated runtime under Blender 5.2's
user scripts directory and are consumed only by external worker processes.
"""

import json
import os
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from .installation_lock import installation_running

ENGINE_TOTALSEG = "TOTALSEG"
ENGINE_TOOTHSEG = "TOOTHSEG"
ENGINE_UMAMBA2 = "UMAMBA2"
ENGINE_IDS = (ENGINE_TOTALSEG, ENGINE_TOOTHSEG, ENGINE_UMAMBA2)
ENGINE_LABELS = {
    ENGINE_TOTALSEG: "TotalSegmentator teeth",
    ENGINE_TOOTHSEG: "ToothSeg dual-branch",
    ENGINE_UMAMBA2: "U-Mamba2 ToothFairy3",
}
ENGINE_CAPABILITIES = {
    ENGINE_TOTALSEG: frozenset({"TEETH", "FDI", "JAW", "CANAL", "SINUS", "PULP", "IMPLANT", "CROWN", "BRIDGE"}),
    ENGINE_TOOTHSEG: frozenset({"TEETH", "FDI", "INSTANCE"}),
    ENGINE_UMAMBA2: frozenset({"TEETH", "FDI", "JAW", "CANAL", "SINUS", "PULP"}),
}
TOTALSEG_VERSION = "2.18.0"
TOOTHSEG_COMMIT = "b29d1017fa124f89645fa56f98649e3f3f43bdb0"
UMAMBA2_COMMIT = "2046d29785087b656ca69fa02dd40e43e69cfb42"
RUNTIME_SCHEMA = "dsg_v910_blender52"

_LOCK = threading.RLock()
_PROC = None
_LOG = None
_STATE = {
    "running": False,
    "done": False,
    "progress": 0.0,
    "phase": "IDLE",
    "message": "",
    "error": "",
    "engine": "ALL",
}
_CACHE = {"t": 0.0, "value": {}}
_CACHE_TTL = 5.0


@dataclass(frozen=True)
class EngineStatus:
    engine: str
    label: str
    code_ready: bool
    dependencies_ready: bool
    model_ready: bool
    ready: bool
    device_hint: str
    runtime_dir: str
    model_path: str = ""
    error: str = ""
    experimental: bool = False
    capabilities: tuple[str, ...] = ()

    def public(self) -> dict:
        return asdict(self)


def _require_blender_52() -> None:
    try:
        import bpy
        major, minor = tuple(int(v) for v in bpy.app.version[:2])
        if (major, minor) != (5, 2):
            raise RuntimeError(
                f"DSG 9.10 está construido exclusivamente para Blender 5.2; se detectó {major}.{minor}."
            )
    except ImportError:
        # Pure-python tests and external workers intentionally run without bpy.
        return


def _scripts_root() -> Path:
    try:
        import bpy
        _require_blender_52()
        root = Path(bpy.utils.user_resource("SCRIPTS", create=True))
    except Exception:
        root = Path.home() / ".dsg" / "blender52" / "scripts"
        root.mkdir(parents=True, exist_ok=True)
    return root


def addon_dir() -> Path:
    return Path(__file__).resolve().parent


def runtime_root() -> Path:
    configured = os.environ.get("DSG_SEGMENTATION_RUNTIME_ROOT", "").strip()
    if configured:
        root = Path(configured).expanduser().resolve()
    else:
        root = _scripts_root() / "dsg_runtime" / f"{RUNTIME_SCHEMA}_py{sys.version_info.major}{sys.version_info.minor}"
    root.mkdir(parents=True, exist_ok=True)
    return root


def site_packages() -> Path:
    p = runtime_root() / "site-packages"
    p.mkdir(parents=True, exist_ok=True)
    return p


def repos_root() -> Path:
    p = runtime_root() / "repos"
    p.mkdir(parents=True, exist_ok=True)
    return p


def models_root() -> Path:
    p = runtime_root() / "models"
    p.mkdir(parents=True, exist_ok=True)
    return p


def totalseg_home() -> Path:
    p = runtime_root() / "totalsegmentator"
    p.mkdir(parents=True, exist_ok=True)
    return p


def totalseg_results() -> Path:
    p = totalseg_home() / "nnunet" / "results"
    p.mkdir(parents=True, exist_ok=True)
    return p


def toothseg_results() -> Path:
    p = models_root() / "toothseg" / "nnUNet_results"
    p.mkdir(parents=True, exist_ok=True)
    return p


def umamba2_models() -> Path:
    p = models_root() / "umamba2"
    p.mkdir(parents=True, exist_ok=True)
    return p


def active_site_paths(engine: str | None = None) -> list[str]:
    paths = [str(site_packages())]
    eng = str(engine or "").upper()
    if eng == ENGINE_TOOTHSEG:
        repo = repos_root() / "ToothSeg"
        if repo.is_dir():
            paths.insert(0, str(repo))
    elif eng == ENGINE_UMAMBA2:
        repo = repos_root() / "U-Mamba2"
        if repo.is_dir():
            paths.insert(0, str(repo))
    return paths


def environment_for_engine(engine: str) -> dict[str, str]:
    engine = str(engine).upper()
    env = {
        "DSG_SEGMENTATION_ENGINE": engine,
        "DSG_SEGMENTATION_RUNTIME_ROOT": str(runtime_root()),
    }
    if engine == ENGINE_TOTALSEG:
        env.update({
            "TOTALSEG_HOME_DIR": str(totalseg_home()),
            "TOTALSEG_WEIGHTS_PATH": str(totalseg_results()),
            "nnUNet_raw": str(totalseg_results()),
            "nnUNet_preprocessed": str(totalseg_results()),
            "nnUNet_results": str(totalseg_results()),
        })
    elif engine == ENGINE_TOOTHSEG:
        raw = models_root() / "toothseg" / "nnUNet_raw"
        prep = models_root() / "toothseg" / "nnUNet_preprocessed"
        raw.mkdir(parents=True, exist_ok=True)
        prep.mkdir(parents=True, exist_ok=True)
        env.update({
            "nnUNet_raw": str(raw),
            "nnUNet_preprocessed": str(prep),
            "nnUNet_results": str(toothseg_results()),
        })
    elif engine == ENGINE_UMAMBA2:
        raw = models_root() / "umamba2" / "nnUNet_raw"
        prep = models_root() / "umamba2" / "nnUNet_preprocessed"
        res = models_root() / "umamba2" / "nnUNet_results"
        for p in (raw, prep, res):
            p.mkdir(parents=True, exist_ok=True)
        env.update({
            "nnUNet_raw": str(raw),
            "nnUNet_preprocessed": str(prep),
            "nnUNet_results": str(res),
        })
    return env


def _contains_checkpoint(root: Path, *, dataset_tokens: tuple[str, ...] = ()) -> tuple[bool, str]:
    # Blender's Windows executable is not long-path-aware. The isolated Python
    # installer can write these files, while Blender otherwise reports them
    # missing once the nnU-Net model/fold path exceeds MAX_PATH.
    if os.name == "nt" and not str(root).startswith("\\\\?\\"):
        absolute = os.path.abspath(root)
        root = Path("\\\\?\\UNC\\" + absolute[2:] if absolute.startswith("\\\\") else "\\\\?\\" + absolute)
    if not root.is_dir():
        return False, ""
    try:
        checkpoints = sorted(root.rglob("checkpoint_best.pth")) + sorted(root.rglob("checkpoint_final.pth"))
    except OSError:
        return False, ""
    for ckpt in checkpoints:
        low = str(ckpt).lower()
        if dataset_tokens and not any(token.lower() in low for token in dataset_tokens):
            continue
        try:
            if ckpt.stat().st_size >= 1_000_000:
                return True, str(ckpt)
        except OSError:
            continue
    return False, ""


def _totalseg_status() -> EngineStatus:
    site = site_packages()
    code = (site / "totalsegmentator").is_dir() and (site / "nnunetv2").is_dir() and (site / "torch").is_dir()
    ds113, p113 = _contains_checkpoint(totalseg_results(), dataset_tokens=("dataset113",))
    ds115, _p115 = _contains_checkpoint(totalseg_results(), dataset_tokens=("dataset115",))
    model = bool(ds113 and ds115)
    err = ""
    if not code:
        err = "Runtime TotalSegmentator 2.18.0 no instalado"
    elif not ds113:
        err = "Faltan pesos task=teeth (Dataset113)"
    elif not ds115:
        err = "Falta el modelo de recorte craneofacial (Dataset115)"
    return EngineStatus(
        ENGINE_TOTALSEG, ENGINE_LABELS[ENGINE_TOTALSEG], code, code, model, bool(code and model),
        "CUDA/CPU", str(runtime_root()), p113, err, False, tuple(sorted(ENGINE_CAPABILITIES[ENGINE_TOTALSEG]))
    )


def _toothseg_status() -> EngineStatus:
    repo = repos_root() / "ToothSeg"
    code = (
        (repo / "toothseg" / "toothseg" / "postprocess_predictions" / "assign_mincost_tooth_labels.py").is_file()
        and (site_packages() / "nnunetv2").is_dir()
        and (site_packages() / "torch").is_dir()
    )
    sem, psem = _contains_checkpoint(toothseg_results(), dataset_tokens=("dataset121",))
    inst, pinst = _contains_checkpoint(toothseg_results(), dataset_tokens=("dataset123",))
    model = bool(sem and inst)
    err = ""
    if not code:
        err = "Código/dependencias ToothSeg no instalados"
    elif not sem:
        err = "Falta checkpoint semántico Dataset121"
    elif not inst:
        err = "Falta checkpoint de instancias Dataset123"
    return EngineStatus(
        ENGINE_TOOTHSEG, ENGINE_LABELS[ENGINE_TOOTHSEG], code, code, model, bool(code and model),
        "CUDA/CPU", str(runtime_root()), psem or pinst, err, False, tuple(sorted(ENGINE_CAPABILITIES[ENGINE_TOOTHSEG]))
    )


def find_umamba2_model_dir() -> tuple[Path | None, str]:
    root = umamba2_models()
    ok, ckpt = _contains_checkpoint(root, dataset_tokens=())
    if not ok:
        return None, ""
    cp = Path(ckpt)
    try:
        # nnU-Net layout: <model-folder>/fold_X/checkpoint_best.pth
        model_dir = cp.parent.parent if cp.parent.name.startswith("fold_") else cp.parent
        return model_dir, str(cp)
    except Exception:
        return None, str(cp)


def _umamba2_status() -> EngineStatus:
    repo = repos_root() / "U-Mamba2"
    code = (
        (repo / "nnunetv2" / "nets" / "UMambaBot_3d.py").is_file()
        and (site_packages() / "torch").is_dir()
        and (site_packages() / "mamba_ssm").is_dir()
        and (site_packages() / "causal_conv1d").is_dir()
    )
    model_dir, ckpt = find_umamba2_model_dir()
    model = bool(model_dir and ckpt)
    # Do not accept the authors' SSL pretraining weights as a final segmenter.
    err = ""
    if not code:
        err = (
            "U-Mamba2 requiere Linux/CUDA y un checkpoint final ToothFairy3; "
            "la instalación nativa en Windows no está soportada"
            if os.name == "nt" else
            "Código U-Mamba2 o kernels mamba-ssm/causal-conv1d no instalados"
        )
    elif not model:
        err = (
            "U-Mamba2 listo a nivel de código, pero falta un checkpoint FINAL de segmentación ToothFairy3; "
            "los pesos SSL de preentrenamiento no se marcan como modelo inferible"
        )
    return EngineStatus(
        ENGINE_UMAMBA2, ENGINE_LABELS[ENGINE_UMAMBA2], code, code, model, bool(code and model),
        "CUDA recomendado", str(runtime_root()), ckpt, err, True, tuple(sorted(ENGINE_CAPABILITIES[ENGINE_UMAMBA2]))
    )


def verify_engine(engine: str, *, force: bool = False) -> EngineStatus:
    engine = str(engine or ENGINE_TOTALSEG).upper()
    if engine not in ENGINE_IDS:
        raise ValueError(f"Motor desconocido: {engine}")
    now = time.time()
    key = engine
    cached = _CACHE.get("value", {}).get(key) if isinstance(_CACHE.get("value"), dict) else None
    if not force and cached is not None and now - float(_CACHE.get("t") or 0.0) < _CACHE_TTL:
        return cached
    status = {
        ENGINE_TOTALSEG: _totalseg_status,
        ENGINE_TOOTHSEG: _toothseg_status,
        ENGINE_UMAMBA2: _umamba2_status,
    }[engine]()
    values = dict(_CACHE.get("value") or {})
    values[key] = status
    _CACHE.update(t=now, value=values)
    return status


def verify_all(*, force: bool = False) -> dict[str, EngineStatus]:
    return {engine: verify_engine(engine, force=force) for engine in ENGINE_IDS}


def invalidate_cache() -> None:
    _CACHE.update(t=0.0, value={})


def engine_supports(engine: str, capability: str) -> bool:
    return str(capability).upper() in ENGINE_CAPABILITIES.get(str(engine).upper(), frozenset())


def _nvidia_driver_present() -> bool:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    try:
        return subprocess.run(
            ["nvidia-smi", "-L"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=3, creationflags=flags,
        ).returncode == 0
    except Exception:
        return False


def runtime_compute_status() -> dict:
    """Use numerical proof for the current wheel; ignore stale receipts."""
    try:
        result = json.loads((runtime_root() / "compute_status.json").read_text(encoding="utf-8"))
        version_file = (site_packages() / "torch" / "version.py").resolve()
        if result.get("ready") and result.get("version_file") == str(version_file) and result.get("version_mtime_ns") == version_file.stat().st_mtime_ns:
            return result
    except (OSError, ValueError):
        pass
    return {"ready": False, "cuda": False, "device": "CPU", "gpu_name": "", "error": "Comprobación de PyTorch pendiente"}


def refresh_runtime_compute_status() -> dict:
    py = _python_path()
    if not py:
        return runtime_compute_status()
    env = os.environ.copy()
    env["PYTHONPATH"] = str(site_packages())
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    subprocess.run([py, str(addon_dir() / "compute_probe.py"), str(site_packages()), str(runtime_root() / "compute_status.json")], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90, creationflags=flags)
    return runtime_compute_status()


def _python_path() -> str:
    candidates: list[Path] = []
    try:
        candidates.extend([
            Path(sys.prefix) / "bin" / ("python.exe" if os.name == "nt" else "python3"),
            Path(sys.prefix) / ("python.exe" if os.name == "nt" else "bin/python3"),
        ])
    except Exception:
        pass
    try:
        import bpy
        _require_blender_52()
        blender = Path(str(getattr(bpy.app, "binary_path", "") or ""))
        if blender:
            base = blender.parent
            candidates.extend([
                base / "5.2" / "python" / "bin" / ("python.exe" if os.name == "nt" else "python3"),
                base / "python" / "bin" / ("python.exe" if os.name == "nt" else "python3"),
            ])
    except Exception:
        pass
    for candidate in candidates:
        try:
            if candidate.is_file():
                return str(candidate)
        except OSError:
            continue
    return ""


def _blender_binary_path() -> str:
    try:
        import bpy
        _require_blender_52()
        candidate = Path(str(getattr(bpy.app, "binary_path", "") or ""))
        if candidate.is_file():
            return str(candidate)
    except Exception:
        pass
    return ""


def _status_file() -> Path:
    return runtime_root() / "install_status.json"


def _request_file() -> Path:
    return runtime_root() / "install_request.json"


def _install_log() -> Path:
    return runtime_root() / "install.log"


def _write_state(**kwargs) -> None:
    with _LOCK:
        _STATE.update(kwargs)
        payload = dict(_STATE)
        payload["time"] = time.time()
        try:
            _status_file().write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass


def install_state() -> dict:
    global _PROC
    with _LOCK:
        try:
            if _status_file().is_file():
                data = json.loads(_status_file().read_text(encoding="utf-8"))
                _STATE.update(data)
        except Exception:
            pass
        if _PROC is not None:
            rc = _PROC.poll()
            if rc is None:
                _STATE["running"] = True
            else:
                _STATE["running"] = False
                if rc != 0 and not _STATE.get("error"):
                    _STATE["error"] = f"Instalador terminó con código {rc}"
                _PROC = None
        return dict(_STATE)


def start_install(engine: str = "ALL", *, force: bool = False) -> bool:
    global _PROC, _LOG
    _require_blender_52()
    engine = str(engine or "ALL").upper()
    if engine not in (*ENGINE_IDS, "ALL"):
        raise ValueError(f"Motor desconocido: {engine}")
    with _LOCK:
        if _PROC is not None and _PROC.poll() is None:
            return False
        if installation_running(runtime_root()):
            return False
        worker = addon_dir() / "segmentation_install_worker.py"
        if not worker.is_file():
            raise RuntimeError("Falta segmentation_install_worker.py")
        py = _python_path()
        blender = _blender_binary_path()
        if not py and not blender:
            raise RuntimeError("No encuentro Python de Blender 5.2 ni blender.exe")
        request = {
            "engine": engine,
            "force": bool(force),
            "runtime_root": str(runtime_root()),
            "site_packages": str(site_packages()),
            "repos_root": str(repos_root()),
            "models_root": str(models_root()),
            "totalseg_home": str(totalseg_home()),
            "totalseg_results": str(totalseg_results()),
            "toothseg_results": str(toothseg_results()),
            "umamba2_models": str(umamba2_models()),
            "totalseg_version": TOTALSEG_VERSION,
            "toothseg_commit": TOOTHSEG_COMMIT,
            "umamba2_commit": UMAMBA2_COMMIT,
            "python_executable": py,
            "blender_binary": blender,
        }
        from . import dicom_module
        request.update(dicom_vendor_dir=str(dicom_module.VENDOR_DIR), dicom_wheelhouse=str(dicom_module.DICOM_OFFLINE_WHEELHOUSE), dicom_requirements=list(dicom_module.DICOM_RUNTIME_REQUIREMENTS))
        request_text = json.dumps(request, ensure_ascii=False, indent=2)
        _request_file().write_text(request_text, encoding="utf-8")
        # A reloaded Blender process must not overwrite a request that an
        # already launched worker has not read yet.
        request_path = runtime_root() / f"install_request_{uuid.uuid4().hex}.json"
        request_path.write_text(request_text, encoding="utf-8")
        _write_state(
            running=True, done=False, progress=0.01, phase="STARTING",
            message=f"Preparando instalación {engine}…", error="", engine=engine,
        )
        _LOG = _install_log().open("a", encoding="utf-8", errors="replace")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        if py:
            cmd = [py, str(worker), str(request_path)]
        else:
            cmd = [blender, "--background", "--factory-startup", "--python", str(worker), "--", str(request_path)]
        _PROC = subprocess.Popen(
            cmd, stdout=_LOG, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            env=env, creationflags=flags,
        )
        invalidate_cache()
        return True


def quick_status(engine: str = ENGINE_TOTALSEG) -> EngineStatus:
    return verify_engine(engine, force=False)


def diagnostics() -> dict:
    statuses = verify_all(force=True)
    return {
        "runtime_schema": RUNTIME_SCHEMA,
        "runtime_root": str(runtime_root()),
        "python": _python_path(),
        "nvidia_driver": _nvidia_driver_present(),
        "engines": {k: v.public() for k, v in statuses.items()},
    }
