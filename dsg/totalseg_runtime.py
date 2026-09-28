from __future__ import annotations

import logging as _dsg_logging
_DSG_LOG = _dsg_logging.getLogger(__name__)
import json, os, subprocess, sys, threading, time
from dataclasses import dataclass
from pathlib import Path

from .engine_install import identity as _engine_identity
from .engine_install import manifest as _engine_manifest

TOTALSEG_VERSION = _engine_identity.TOTALSEG_VERSION
# 9.7.3: the runtime folder is named after its *content* (TotalSegmentator,
# PyTorch, accelerator, Python ABI, platform), never after the DSG release.
# Older releases used dsg_ts965/…/dsg_ts968 and forced a multi-GB reinstall on
# every update; such folders are adopted (renamed) when they hold the same engine.
RUNTIME_SCHEMA = "engine-identity-v1"
_TASK_IDS = (115, 113)
_LOCK = threading.RLock()
_PROC = None
_LOG = None
_STATE = {"running": False, "progress": 0.0, "phase": "IDLE", "message": "", "error": "", "done": False}

@dataclass(frozen=True)
class RuntimeStatus:
    dependencies_ready: bool
    model_ready: bool
    semantic_model_ready: bool
    universal_model_ready: bool
    device: str
    version: str
    runtime_dir: str
    error: str = ""


def _scripts_root() -> Path:
    try:
        import bpy
        p = Path(bpy.utils.user_resource("SCRIPTS", create=True))
    except Exception:
        p = Path.home() / ".dsg" / "scripts"
        p.mkdir(parents=True, exist_ok=True)
    return p


def addon_dir() -> Path:
    return Path(__file__).resolve().parent


def offline_payload_root() -> Path:
    return addon_dir() / "offline_totalseg"


def runtime_base() -> Path:
    """Parent of every runtime + the shared download cache (outside the add-on)."""
    configured = os.environ.get("DSG_TOTALSEG_RUNTIME_ROOT", "").strip()
    p = Path(configured).expanduser() if configured else (_scripts_root() / "dsg_runtime")
    p.mkdir(parents=True, exist_ok=True)
    return p


def desired_accelerator() -> str:
    return _engine_identity.choose_accelerator(_nvidia_driver_present())


def desired_identity():
    return _engine_identity.desired_identity(desired_accelerator())


def runtime_root() -> Path:
    """Folder of the active engine (or of the one that will be installed)."""
    base = runtime_base()
    active = _engine_identity.active_runtime_dir(base)
    if active is not None:
        return active
    p = _engine_identity.runtime_dir(base, desired_identity())
    p.mkdir(parents=True, exist_ok=True)
    return p


def runtime_site_packages() -> Path:
    p = runtime_root() / "site-packages"
    p.mkdir(parents=True, exist_ok=True)
    return p


def totalseg_home() -> Path:
    p = runtime_root() / "totalseg_home"
    p.mkdir(parents=True, exist_ok=True)
    return p


def active_site_paths() -> list[str]:
    # v9.5.5 keeps the verified 2.18.0 runtime schema; only the DSG integration changed.
    return [str(runtime_site_packages())]


def _prepend_paths():
    p = str(runtime_site_packages())
    if p not in sys.path:
        sys.path.insert(0, p)
    os.environ["TOTALSEG_HOME_DIR"] = str(totalseg_home())
    os.environ["TOTALSEG_WEIGHTS_PATH"] = str(totalseg_home() / "nnunet" / "results")


def _dataset_ready(token: str) -> bool:
    base = totalseg_home() / "nnunet" / "results"
    return base.is_dir() and any(p.is_dir() and token.lower() in p.name.lower() for p in base.iterdir())


def _weights_ready() -> bool:
    return _dataset_ready("Dataset113") and _dataset_ready("Dataset115")


def payload_diagnostics() -> dict:
    root = offline_payload_root()
    manifest = root / "OFFLINE_PAYLOAD_MANIFEST.json"
    info = {"payload_root": str(root), "manifest": manifest.is_file(), "runtime_archive": False, "dataset113": False, "dataset115": False}
    if manifest.is_file():
        try:
            d = json.loads(manifest.read_text(encoding="utf-8"))
            files = d.get("files", {})
            for key in ("runtime_archive", "dataset113", "dataset115"):
                rec = files.get(key, {}) if isinstance(files, dict) else {}
                rel = rec.get("path", "") if isinstance(rec, dict) else ""
                info[key] = bool(rel and (root / rel).is_file())
        except Exception as exc:
            info["error"] = f"{type(exc).__name__}: {exc}"
    return info


def quick_status() -> RuntimeStatus:
    site = runtime_site_packages()
    pkg = (site / "totalsegmentator").is_dir()
    torch_pkg = (site / "torch").is_dir()
    nnunet_pkg = (site / "nnunetv2").is_dir()
    deps = bool(pkg and torch_pkg and nnunet_pkg)
    models = _weights_ready() if deps else False
    device = "CUDA" if _nvidia_driver_present() else "CPU"
    error = ""
    if not deps:
        error = "Motor de IA no instalado"
    elif not models:
        error = "Modelos dentales (Dataset113/115) no instalados"
    return RuntimeStatus(deps, models, models, models, device, TOTALSEG_VERSION, str(runtime_root()), error)

runtime_status = quick_status

def universal_model_ready(): return quick_status().model_ready

def dependency_diagnostics():
    s = quick_status()
    return {"ready": s.dependencies_ready, "device": s.device, "error": s.error, "runtime": s.runtime_dir, "engine": "TotalSegmentator", "version": TOTALSEG_VERSION, "offline": True, "payload": payload_diagnostics()}


def install_state():
    _poll_install()
    with _LOCK:
        return dict(_STATE)


def _status_file(): return runtime_base() / "install_status.json"
def _request_file(): return runtime_base() / "install_request.json"
def _log_file(): return runtime_base() / "install.log"

def _set(**kw):
    with _LOCK:
        _STATE.update(kw)




def _click_log_file(): return runtime_base() / "install_click.json"

def record_install_click(*, click_id: str, operator_id: str):
    """Persist proof that Blender executed the current installer operator."""
    py = _python_path()
    data = {
        "timestamp": time.time(),
        "click_id": str(click_id),
        "operator_id": str(operator_id),
        "dsg_runtime_schema": RUNTIME_SCHEMA,
        "totalseg_version": TOTALSEG_VERSION,
        "sys_executable": str(sys.executable),
        "sys_prefix": str(sys.prefix),
        "python_worker": str(py),
        "python_worker_exists": bool(py and Path(py).is_file()),
        "payload": payload_diagnostics(),
    }
    _click_log_file().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data

def mark_install_requested(message="Preparando instalación…"):
    _set(running=True, done=False, progress=0.005, phase="REQUESTED", message=message, error="")


def mark_install_error(message):
    _set(running=False, done=True, progress=0.0, phase="ERROR", message="Instalación TotalSegmentator fallida", error=str(message))


def _poll_install():
    global _PROC, _LOG
    # Always consume the persistent worker status. This survives add-on reloads
    # where the in-memory Popen handle is lost but the installer is still alive.
    sf = _status_file()
    if sf.is_file():
        try:
            data = json.loads(sf.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                _set(**data)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    p = _PROC
    if p is None:
        return
    rc = p.poll()
    if rc is None:
        return
    try:
        if _LOG:
            _LOG.close()
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    _LOG = None
    _PROC = None
    st = dict(_STATE)
    if rc != 0 and not st.get("error"):
        tail = ""
        try:
            tail = _log_file().read_text(encoding="utf-8", errors="replace")[-5000:]
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        _set(running=False, done=True, phase="ERROR", error=f"El instalador de motores terminó con código {rc}: {tail[-1200:]}", message="Instalación de motores fallida")
    elif rc == 0:
        s = quick_status()
        ok = s.dependencies_ready and s.model_ready
        _set(running=False, done=True, progress=1.0 if ok else float(st.get("progress", 0.95)), phase="READY" if ok else "VERIFY", message=str(st.get("message") or "Motor listo ✓") if ok else "Instalado · verificación pendiente", error="" if ok else s.error)


def _python_path() -> str:
    """Return Blender's embedded standalone Python executable (Windows)."""
    candidates = []
    try:
        candidates.append(Path(sys.prefix) / "bin" / ("python.exe" if os.name == "nt" else "python3"))
        candidates.append(Path(sys.prefix) / ("python.exe" if os.name == "nt" else "bin/python3"))
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    try:
        import bpy
        blender = Path(str(getattr(bpy.app, "binary_path", "") or ""))
        if blender:
            base = blender.parent
            ver = f"{bpy.app.version[0]}.{bpy.app.version[1]}"
            candidates.extend([
                base / ver / "python" / "bin" / ("python.exe" if os.name == "nt" else "python3"),
                base / "python" / "bin" / ("python.exe" if os.name == "nt" else "python3"),
            ])
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    for candidate in candidates:
        try:
            if candidate.is_file():
                return str(candidate)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
    return ""


def start_install(force: bool = False) -> bool:
    """Start the external engine installer (``engine_install_worker.py``).

    Fastest source first: reuse → adopt legacy runtime → payload in the ZIP →
    prebuilt download (manifest v2, GitHub/Google Drive mirrors) → local build
    with uv. ``force`` reinstalls even if the engine is ready (CUDA repair).
    """
    global _PROC, _LOG
    _poll_install()
    if _PROC is not None and _PROC.poll() is None:
        return False
    mark_install_requested("Localizando Python de Blender…")
    py = _python_path()
    if not py:
        raise RuntimeError(
            "No encuentro el Python interno de Blender 5.2. "
            "Esperaba ...\\Blender 5.2\\5.2\\python\\bin\\python.exe"
        )
    req = {
        "addon_dir": str(addon_dir()),
        "base_dir": str(runtime_base()),
        "python": py,
        "accel": desired_accelerator(),
        "force": bool(force),
        "offline_payload_dir": str(offline_payload_root()),
        "locks_dir": str(addon_dir() / "engine_install" / "locks"),
        "manifest_urls": list(_manifest_urls()),
        "workers": 4,
    }
    _request_file().write_text(json.dumps(req, ensure_ascii=False), encoding="utf-8")
    try:
        _status_file().unlink(missing_ok=True)
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)
    worker = addon_dir() / "engine_install_worker.py"
    if not worker.is_file():
        raise RuntimeError(f"Falta el instalador de motores: {worker.name}")
    _LOG = open(_log_file(), "w", encoding="utf-8", errors="replace")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    env = os.environ.copy(); env["PYTHONUNBUFFERED"] = "1"
    try:
        cmd=[py, str(worker), str(_request_file())]
        _log_file().parent.mkdir(parents=True, exist_ok=True)
        _PROC = subprocess.Popen(
            cmd,
            stdout=_LOG,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            env=env,
            creationflags=flags,
        )
        # Catch launch/import failures synchronously so the button can report them.
        time.sleep(0.20)
        rc=_PROC.poll()
        if rc is not None and rc != 0:
            try:
                _LOG.flush()
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            tail=""
            try:
                tail=_log_file().read_text(encoding="utf-8", errors="replace")[-3000:]
            except Exception:
                _DSG_LOG.debug("suppressed exception", exc_info=True)
            _PROC=None
            raise RuntimeError(f"El bootstrap terminó inmediatamente con código {rc}. {tail[-1200:]}")
    except Exception as exc:
        try:
            _LOG.close()
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
        _LOG = None
        _PROC = None
        msg = f"No se pudo iniciar el instalador: {type(exc).__name__}: {exc}"
        mark_install_error(msg)
        raise RuntimeError(msg) from exc
    _set(running=True, done=False, progress=0.01, phase="BOOT",
         message=f"Preparando motor de IA ({req['accel'].upper()})…", error="")
    return True


def _manifest_urls() -> tuple[str, ...]:
    """Remote engine manifests; ``DSG_ENGINE_MANIFEST_URL`` adds a first mirror."""
    extra = os.environ.get("DSG_ENGINE_MANIFEST_URL", "").strip()
    return ((extra,) if extra else ()) + tuple(_engine_manifest.DEFAULT_MANIFEST_URLS)


_NVIDIA_CACHE = {"t": 0.0, "value": False}


def _nvidia_driver_present():
    """nvidia-smi probe, cached for 5 min: it is called from panel draw code."""
    now = time.time()
    if now - _NVIDIA_CACHE["t"] < 300.0:
        return _NVIDIA_CACHE["value"]
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        r = subprocess.run(["nvidia-smi", "-L"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2, creationflags=flags)
        value = r.returncode == 0
    except Exception:
        value = False
    _NVIDIA_CACHE.update(t=now, value=value)
    return value


def active_runtime_site_packages(): return str(runtime_site_packages())
def shutdown_persistent_worker(force=False): return None
def prediction_job_state(): return {"running": False, "done": False, "message": "TotalSegmentator usa el pipeline externo 9.5", "error": ""}
def last_performance_plan():
    s = quick_status(); return {"engine": "TotalSegmentator", "task": "teeth", "device": s.device, "version": TOTALSEG_VERSION, "offline": True}
