from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path
try:
    from .installation_lock import installation_lock
except ImportError:
    from installation_lock import installation_lock


def _status_path(req):
    return Path(req["runtime_root"]) / "install_status.json"


def _write(req, progress, phase, message, *, error="", done=False, running=True, engine=None, detail=None):
    payload = {
        "running": bool(running),
        "done": bool(done),
        "progress": float(progress),
        "phase": str(phase),
        "message": str(message),
        "error": str(error or ""),
        "engine": str(engine or req.get("engine") or "ALL"),
        "time": time.time(),
    }
    if detail:
        payload["detail"] = detail
    path = _status_path(req)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _run(cmd, *, env=None, cwd=None):
    print("[DSG INSTALL]", " ".join(str(v) for v in cmd), flush=True)
    subprocess.run([str(v) for v in cmd], check=True, env=env, cwd=str(cwd) if cwd else None)


def _python(req):
    p = str(req.get("python_executable") or "").strip()
    if p and Path(p).is_file():
        return p
    return sys.executable


def _env(req, extra_paths=()):
    env = os.environ.copy()
    site = str(req["site_packages"])
    paths = [str(p) for p in extra_paths if p] + [site]
    current = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join(paths + ([current] if current else []))
    env["PYTHONUNBUFFERED"] = "1"
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    return env


def _pip(req, *args, env=None):
    site = Path(req["site_packages"])
    site.mkdir(parents=True, exist_ok=True)
    cmd = [_python(req), "-m", "pip", "install", "--upgrade", "--target", str(site), "--no-warn-script-location"]
    if req.get("torch_variant"):
        # Dependency repairs must preserve the tested CUDA build.
        variant = str(req["torch_variant"])
        constraints = Path(req["runtime_root"]) / "torch_constraints.txt"
        suffix = "+cu126" if variant == "cu126" else "+cpu"
        constraints.write_text(f"torch==2.14.1{suffix}\ntorchvision==0.29.1{suffix}\n", encoding="utf-8")
        cmd.extend(["--constraint", str(constraints), "--extra-index-url", f"https://download.pytorch.org/whl/{variant}"])
    cmd.extend(args)
    _run(cmd, env=env or _env(req))


def prepare_compute(req):
    output = Path(req["runtime_root"]) / "compute_status.json"
    probe = Path(__file__).with_name("compute_probe.py")
    def check():
        try:
            _run([_python(req), probe, req["site_packages"], output], env=_env(req))
            return json.loads(output.read_text(encoding="utf-8"))
        except subprocess.CalledProcessError:
            return {}
    current = check()
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    try:
        nvidia = subprocess.run(["nvidia-smi", "-L"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5, creationflags=flags).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        nvidia = False
    variant = "cu126" if nvidia else "cpu"
    req["torch_variant"] = "cu126" if current.get("cuda") else variant
    if current.get("ready") and (current.get("cuda") or not nvidia):
        return current
    _write(req, .02, "PYTORCH", f"Preparando PyTorch {variant}… (CUDA: descarga de 2.6 GB)")
    suffix = "+cu126" if variant == "cu126" else "+cpu"
    _pip(req, "--no-deps", "--only-binary=:all:", "--index-url", f"https://download.pytorch.org/whl/{variant}", f"torch==2.14.1{suffix}", f"torchvision==0.29.1{suffix}")
    current = check()
    if not current.get("ready") or (nvidia and not current.get("cuda")):
        raise RuntimeError("PyTorch no supera la prueba CUDA/cuDNN; revisa compute_status.json")
    return current


def prepare_dicom(req):
    vendor = Path(req["dicom_vendor_dir"])
    probe = Path(__file__).with_name("dicom_probe.py")
    env = _env(req)
    try:
        _run([_python(req), probe, vendor], env=env)
        return
    except subprocess.CalledProcessError:
        pass
    wheels = Path(req["dicom_wheelhouse"])
    if not wheels.is_dir() or not any(wheels.glob("*.whl")):
        raise RuntimeError("Falta el wheelhouse DICOM completo en el ZIP")
    _run([_python(req), "-m", "pip", "install", "--no-index", "--no-deps", "--only-binary=:all:", "--find-links", wheels, "--upgrade", "--target", vendor, *req["dicom_requirements"]], env=env)
    _run([_python(req), probe, vendor], env=env)


def _download(url, destination: Path, *, expected_md5="", description="archivo"):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and destination.stat().st_size > 1024:
        if expected_md5:
            h = hashlib.md5()
            with destination.open("rb") as fh:
                for chunk in iter(lambda: fh.read(4 * 1024 * 1024), b""):
                    h.update(chunk)
            if h.hexdigest().lower() == expected_md5.lower():
                print(f"[DSG INSTALL] {description} ya descargado y verificado", flush=True)
                return destination
        else:
            return destination
    tmp = destination.with_suffix(destination.suffix + ".part")
    if tmp.exists():
        tmp.unlink()
    print(f"[DSG INSTALL] descargando {description}: {url}", flush=True)
    req = urllib.request.Request(url, headers={"User-Agent": "DSG-Blender-5.2/9.10"})
    with urllib.request.urlopen(req, timeout=90) as src, tmp.open("wb") as dst:
        total = int(src.headers.get("Content-Length") or 0)
        copied = 0
        while True:
            chunk = src.read(4 * 1024 * 1024)
            if not chunk:
                break
            dst.write(chunk)
            copied += len(chunk)
            if total:
                print(f"[DSG INSTALL] {description}: {100.0 * copied / total:.1f}%", flush=True)
    os.replace(tmp, destination)
    if expected_md5:
        h = hashlib.md5()
        with destination.open("rb") as fh:
            for chunk in iter(lambda: fh.read(4 * 1024 * 1024), b""):
                h.update(chunk)
        actual = h.hexdigest().lower()
        if actual != expected_md5.lower():
            destination.unlink(missing_ok=True)
            raise RuntimeError(f"MD5 inválido para {description}: {actual}")
    return destination


def _github_snapshot(owner_repo: str, commit: str, destination: Path):
    marker = destination / ".dsg_commit"
    if destination.is_dir() and marker.is_file() and marker.read_text(encoding="utf-8").strip() == commit:
        return
    url = f"https://github.com/{owner_repo}/archive/{commit}.zip"
    cache = destination.parent / f"{destination.name}-{commit[:12]}.zip"
    _download(url, cache, description=f"{owner_repo}@{commit[:12]}")
    with tempfile.TemporaryDirectory(prefix="dsg_repo_") as td:
        with zipfile.ZipFile(cache) as zf:
            zf.extractall(td)
        roots = [p for p in Path(td).iterdir() if p.is_dir()]
        if len(roots) != 1:
            raise RuntimeError(f"Snapshot GitHub inesperado para {owner_repo}")
        if destination.exists():
            shutil.rmtree(destination, ignore_errors=True)
        shutil.copytree(roots[0], destination)
    marker.write_text(commit, encoding="utf-8")


def _find_dataset(root: Path, token: str):
    found = [p for p in root.rglob("*") if p.is_dir() and token.lower() in p.name.lower()]
    return sorted(found, key=lambda p: len(p.parts))[0] if found else None


def _has_checkpoint(root: Path, token: str = ""):
    if not root.is_dir():
        return False
    for name in ("checkpoint_best.pth", "checkpoint_final.pth"):
        for p in root.rglob(name):
            if token and token.lower() not in str(p).lower():
                continue
            try:
                if p.stat().st_size >= 1_000_000:
                    return True
            except OSError:
                pass
    return False


def _verify_runtime(req, engine):
    """A folder's presence is insufficient: load each official model on CPU."""
    path = Path(req["runtime_root"]) / f"preflight_request_{engine}.json"
    output = Path(req["runtime_root"]) / f"preflight_{engine}.json"
    path.write_text(json.dumps(req, ensure_ascii=False), encoding="utf-8")
    extra = (Path(req["repos_root"]) / "ToothSeg",) if engine == "TOOTHSEG" else ()
    env = _env(req, extra)
    results = str(req["toothseg_results"] if engine == "TOOTHSEG" else req["totalseg_results"])
    env.update(nnUNet_raw=results, nnUNet_preprocessed=results, nnUNet_results=results)
    if engine == "TOTALSEG":
        env.update(TOTALSEG_HOME_DIR=str(req["totalseg_home"]), TOTALSEG_WEIGHTS_PATH=results)
    try:
        _run([_python(req), Path(__file__).with_name("engine_preflight.py"), path, engine, output], env=env)
    except subprocess.CalledProcessError as exc:
        try:
            detail = json.loads(output.read_text(encoding="utf-8")).get("error", "")
        except (OSError, ValueError):
            detail = str(exc)
        raise RuntimeError(f"{engine}: comprobación de runtime fallida: {detail}") from exc


def install_totalseg(req, base_progress=0.0, span=1.0):
    site = Path(req["site_packages"]); results = Path(req["totalseg_results"])
    if not bool(req.get("force")) and (site / "totalsegmentator").is_dir() and (site / "torch").is_dir() and _has_checkpoint(results, "dataset113") and _has_checkpoint(results, "dataset115"):
        _verify_runtime(req, "TOTALSEG")
        _write(req, base_progress + span * 0.98, "TOTALSEG_VERIFY", "TotalSegmentator ya verificado ✓", engine="TOTALSEG")
        return
    _write(req, base_progress + span * 0.04, "TOTALSEG_CODE", "Instalando TotalSegmentator 2.18.0…", engine="TOTALSEG")
    _pip(req, f"TotalSegmentator=={req['totalseg_version']}")
    results.mkdir(parents=True, exist_ok=True)
    env = _env(req)
    env["TOTALSEG_HOME_DIR"] = str(req["totalseg_home"])
    env["TOTALSEG_WEIGHTS_PATH"] = str(results)
    env["nnUNet_raw"] = str(results)
    env["nnUNet_preprocessed"] = str(results)
    env["nnUNet_results"] = str(results)
    _write(req, base_progress + span * 0.45, "TOTALSEG_WEIGHTS", "Descargando pesos task=teeth (Dataset113)…", engine="TOTALSEG")
    code = (
        "from totalsegmentator.config import setup_nnunet,setup_totalseg;"
        "setup_nnunet();setup_totalseg();"
        "from totalsegmentator.libs import download_pretrained_weights;"
        "download_pretrained_weights(113);download_pretrained_weights(115)"
    )
    _run([_python(req), "-c", code], env=env)
    if not _has_checkpoint(results, "dataset113"):
        raise RuntimeError("TotalSegmentator terminó sin un checkpoint Dataset113 válido")
    if not _has_checkpoint(results, "dataset115"):
        raise RuntimeError("TotalSegmentator terminó sin el modelo Dataset115 de recorte")
    _verify_runtime(req, "TOTALSEG")
    _write(req, base_progress + span * 0.98, "TOTALSEG_VERIFY", "TotalSegmentator verificado ✓", engine="TOTALSEG")


def install_toothseg(req, base_progress=0.0, span=1.0):
    repos = Path(req["repos_root"]); target = Path(req["toothseg_results"]); site = Path(req["site_packages"])
    repos.mkdir(parents=True, exist_ok=True)
    repo = repos / "ToothSeg"
    marker = repo / ".dsg_commit"
    if not bool(req.get("force")) and marker.is_file() and marker.read_text(encoding="utf-8").strip() == req["toothseg_commit"] and (site / "nnunetv2").is_dir() and (site / "torch").is_dir() and _has_checkpoint(target, "dataset121") and _has_checkpoint(target, "dataset123"):
        _verify_runtime(req, "TOOTHSEG")
        _write(req, base_progress + span * 0.98, "TOOTHSEG_VERIFY", "ToothSeg ya verificado ✓", engine="TOOTHSEG")
        return
    _write(req, base_progress + span * 0.05, "TOOTHSEG_CODE", "Descargando código ToothSeg oficial…", engine="TOOTHSEG")
    _github_snapshot("MIC-DKFZ/ToothSeg", req["toothseg_commit"], repo)
    _write(req, base_progress + span * 0.18, "TOOTHSEG_DEPS", "Instalando dependencias ToothSeg/nnU-Net…", engine="TOOTHSEG")
    _pip(req, "nnunetv2", "nibabel", "SimpleITK", "scipy", "pandas", "connected-components-3d")
    weights_zip = Path(req["models_root"]) / "downloads" / "ToothSeg.zip"
    _write(req, base_progress + span * 0.36, "TOOTHSEG_WEIGHTS", "Descargando ToothSeg.zip oficial (920 MB)…", engine="TOOTHSEG")
    _download(
        "https://zenodo.org/records/14893540/files/ToothSeg.zip?download=1",
        weights_zip,
        expected_md5="5d8dd061cce9529943567aeba3271143",
        description="ToothSeg.zip",
    )
    target.mkdir(parents=True, exist_ok=True)
    _write(req, base_progress + span * 0.78, "TOOTHSEG_EXTRACT", "Extrayendo checkpoints ToothSeg…", engine="TOOTHSEG")
    with tempfile.TemporaryDirectory(prefix="dsg_toothseg_") as td:
        with zipfile.ZipFile(weights_zip) as zf:
            zf.extractall(td)
        root = Path(td)
        for token in ("Dataset121", "Dataset123"):
            src = _find_dataset(root, token)
            if src is None:
                raise RuntimeError(f"ToothSeg.zip no contiene {token}")
            dst = target / src.name
            if dst.exists():
                shutil.rmtree(dst, ignore_errors=True)
            shutil.copytree(src, dst)
    if not _has_checkpoint(target, "dataset121") or not _has_checkpoint(target, "dataset123"):
        raise RuntimeError("ToothSeg extraído pero faltan checkpoints Dataset121/Dataset123")
    _verify_runtime(req, "TOOTHSEG")
    _write(req, base_progress + span * 0.98, "TOOTHSEG_VERIFY", "ToothSeg dual-branch verificado ✓", engine="TOOTHSEG")


def install_umamba2(req, base_progress=0.0, span=1.0):
    if os.name == "nt":
        raise RuntimeError(
            "U-Mamba2 no admite instalación nativa en Windows: los kernels "
            "mamba-ssm/causal-conv1d requieren Linux/CUDA. Además se necesita "
            "un checkpoint final ToothFairy3; los pesos SSL no sirven para segmentar. "
            "TotalSegmentator y ToothSeg se conservan y pueden usarse por separado."
        )
    repos = Path(req["repos_root"]); site = Path(req["site_packages"]); model_dir = Path(req["umamba2_models"])
    repos.mkdir(parents=True, exist_ok=True)
    repo = repos / "U-Mamba2"
    marker = repo / ".dsg_commit"
    code_ready = marker.is_file() and marker.read_text(encoding="utf-8").strip() == req["umamba2_commit"] and (site / "torch").is_dir() and (site / "mamba_ssm").is_dir() and (site / "causal_conv1d").is_dir()
    if not bool(req.get("force")) and code_ready and _has_checkpoint(model_dir):
        model_dir.mkdir(parents=True, exist_ok=True)
        _write(req, base_progress + span * 0.98, "UMAMBA_VERIFY", "U-Mamba2 código/kernels ya preparados; checkpoint final se valida aparte", engine="UMAMBA2")
        return
    _write(req, base_progress + span * 0.08, "UMAMBA_CODE", "Descargando U-Mamba2 oficial…", engine="UMAMBA2")
    _github_snapshot("zhiqin1998/U-Mamba2", req["umamba2_commit"], repo)
    _write(req, base_progress + span * 0.28, "UMAMBA_DEPS", "Instalando dependencias base U-Mamba2…", engine="UMAMBA2")
    _pip(req, "nnunetv2", "nibabel", "SimpleITK", "connected-components-3d")
    # Mamba's CUDA extensions are intentionally attempted separately so a failure
    # does not corrupt TotalSegmentator or ToothSeg in the shared runtime.
    _write(req, base_progress + span * 0.50, "UMAMBA_KERNELS", "Instalando kernels Mamba2…", engine="UMAMBA2")
    env = _env(req)
    _pip(req, "causal-conv1d==1.5.2", "mamba-ssm==2.2.5", "--no-build-isolation", env=env)
    model_dir.mkdir(parents=True, exist_ok=True)
    notice = model_dir / "README_CHECKPOINT_FINAL.txt"
    notice.write_text(
        "U-Mamba2 está integrado en DSG, pero el repositorio oficial enlaza pesos SSL de preentrenamiento, "
        "no un checkpoint final de segmentación listo para inferencia.\n\n"
        "Coloca aquí (o en una subcarpeta nnU-Net) un checkpoint_best.pth o checkpoint_final.pth final de "
        "ToothFairy3 junto con su estructura de modelo. DSG no marcará U-Mamba2 como READY hasta detectarlo.\n",
        encoding="utf-8",
    )
    _write(
        req, base_progress + span * 0.98, "UMAMBA_VERIFY",
        "U-Mamba2: código instalado; checkpoint final pendiente (no se aceptan pesos SSL como segmentador)",
        engine="UMAMBA2",
    )
    if not _has_checkpoint(model_dir):
        raise RuntimeError("U-Mamba2: falta un checkpoint FINAL ToothFairy3; los pesos SSL no son un segmentador")


def main():
    req_path = Path(sys.argv[-1]).resolve()
    req = json.loads(req_path.read_text(encoding="utf-8"))
    with installation_lock(req["runtime_root"]):
        _install_request(req)


def _install_request(req):
    engine = str(req.get("engine") or "ALL").upper()
    Path(req["runtime_root"]).mkdir(parents=True, exist_ok=True)
    Path(req["site_packages"]).mkdir(parents=True, exist_ok=True)
    failures = []
    outcomes = {}
    components = {}
    if engine != "UMAMBA2" and req.get("dicom_vendor_dir"):
        for name, prepare in (("DICOM", prepare_dicom), ("PYTORCH", prepare_compute)):
            try:
                prepare(req)
                components[name] = {"status": "READY", "error": ""}
            except Exception as exc:
                components[name] = {"status": "ERROR", "error": str(exc)}
                failures.append(f"{name}: {type(exc).__name__}: {exc}")
    if engine == "ALL":
        jobs = [
            ("TOTALSEG", install_totalseg),
            ("TOOTHSEG", install_toothseg),
            ("UMAMBA2", install_umamba2),
        ]
        for idx, (name, fn) in enumerate(jobs):
            try:
                fn(req, idx / 3.0, 1.0 / 3.0)
                outcomes[name] = {"status": "READY", "error": ""}
            except Exception as exc:
                failures.append(f"{name}: {type(exc).__name__}: {exc}")
                outcomes[name] = {"status": "ERROR", "error": str(exc)}
                print("[DSG INSTALL ERROR]", failures[-1], flush=True)
        message = "Instalación terminada"
        if failures:
            message += " · algunos motores quedaron pendientes"
        _write(
            req, 1.0, "PARTIAL" if failures else "DONE", message, error=" | ".join(failures),
            done=True, running=False, engine="ALL", detail={"failures": failures, "engines": outcomes, "components": components},
        )
        return
    fn = {"TOTALSEG": install_totalseg, "TOOTHSEG": install_toothseg, "UMAMBA2": install_umamba2}.get(engine)
    if fn is None:
        raise RuntimeError(f"Motor desconocido: {engine}")
    try:
        fn(req, 0.0, 1.0)
        message = (
            "U-Mamba2 código preparado; checkpoint final pendiente de validación"
            if engine == "UMAMBA2" else f"{engine} instalado/verificado"
        )
        _write(req, 1.0, "PARTIAL" if failures else "DONE", message, error=" | ".join(failures), done=True, running=False, engine=engine, detail={"components": components})
    except Exception as exc:
        _write(req, 1.0, "ERROR", f"Error instalando {engine}", error=f"{type(exc).__name__}: {exc}", done=True, running=False, engine=engine)
        raise


if __name__ == "__main__":
    main()
