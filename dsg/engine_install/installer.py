"""Engine installation orchestration.

Order of sources (fastest first):

1. **reuse**    – the runtime for this exact identity is already installed (0 s);
2. **adopt**    – a legacy ``dsg_tsNNN_pyXY`` folder already holds the same engine:
                  it is renamed, not reinstalled (0 s);
3. **offline**  – the add-on ZIP itself carries the payload (manifest schema 1);
4. **prebuilt** – download the prebuilt runtime + weights listed in the remote
                  manifest (schema 2): parallel, resumable, hash-verified;
5. **build**    – install locally with uv (pip fallback) while the weights
                  download in parallel.

Everything is installed into ``_stage-<key>`` first, verified by importing the
engine in a separate Python, and only then activated with a directory rename.
A failure never damages a working runtime.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import archive, builder, download, identity, manifest
from .fsio import DIR_RETRY_DELAYS, replace_with_retry

Emit = Callable[..., None]

# Official weights (used when no manifest mirror is reachable).
OFFICIAL_WEIGHTS = (
    manifest.Asset("w113", "weights", 232066830,
                   "cf28693eec49b7a8448e2ebf0a372da41855a099a26d52d1cffe15a3c7e4b740",
                   (manifest.Part("Dataset113_ToothFairy3.zip", 232066830,
                                  "cf28693eec49b7a8448e2ebf0a372da41855a099a26d52d1cffe15a3c7e4b740",
                                  ("https://github.com/wasserth/TotalSegmentator/releases/download/"
                                   "v2.5.0-weights/Dataset113_ToothFairy3.zip",)),)),
    manifest.Asset("w115", "weights", 230321497, "",
                   (manifest.Part("Dataset115_mandible.zip", 230321497, "",
                                  ("https://github.com/wasserth/TotalSegmentator/releases/download/"
                                   "v2.5.0-weights/Dataset115_mandible.zip",)),)),
)

VERIFY_SNIPPET = r"""
import json, sys, os
import torch, nnunetv2, totalsegmentator
from totalsegmentator.registry import get_task_classes
n = len(get_task_classes("teeth"))
print(json.dumps({"torch": torch.__version__, "cuda": torch.version.cuda, "teeth_classes": n}))
sys.exit(0 if n >= 40 else 3)
"""



def _never_raising(emit):
    """Progress reporting must never abort an installation (e.g. a status file
    locked on Windows); the install result is what matters."""
    def safe(*args, **kwargs):
        try:
            emit(*args, **kwargs)
        except Exception:                           # noqa: BLE001
            import logging
            logging.getLogger("dsg.engine_install").debug("progress callback failed", exc_info=True)
    return safe


@dataclass
class InstallRequest:
    base_dir: Path                     # <Blender user scripts>/dsg_runtime
    python: str                        # Blender's Python (same ABI as the runtime)
    accel: str                         # "cuda126" | "cpu"
    force: bool = False
    manifest_urls: tuple[str, ...] = manifest.DEFAULT_MANIFEST_URLS
    offline_payload_dir: Path | None = None
    locks_dir: Path | None = None
    workers: int = 4
    allow_build: bool = True
    keep_downloads: bool = False       # archives are ~4 GB: delete them once installed


@dataclass
class InstallResult:
    source: str
    key: str
    runtime: Path
    seconds: float
    details: dict = field(default_factory=dict)


class InstallError(RuntimeError):
    pass


def fetch_manifest(urls, timeout: float = 20.0) -> manifest.Manifest | None:
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": download.USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return manifest.parse(resp.read())
        except Exception:                      # noqa: BLE001 - try the next source
            continue
    return None


def verify_runtime(python: str, stage: Path, accel: str, timeout: float = 600.0) -> dict:
    """Import the engine from the staged folder in a clean Python process."""
    env = dict(os.environ, PYTHONPATH=str(identity.site_packages(stage)), PYTHONNOUSERSITE="1",
               TOTALSEG_HOME_DIR=str(stage / "totalseg_home"),
               TOTALSEG_WEIGHTS_PATH=str(identity.weights_dir(stage)))
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    proc = subprocess.run([python, "-c", VERIFY_SNIPPET], env=env, capture_output=True, text=True,
                          timeout=timeout, creationflags=flags)
    if proc.returncode != 0:
        raise InstallError("engine import check failed: " + (proc.stderr or proc.stdout)[-1500:])
    info = json.loads(proc.stdout.strip().splitlines()[-1])
    if accel == "cuda126" and not info.get("cuda"):
        raise InstallError("a CPU-only PyTorch was installed although CUDA was requested")
    names = [p.name.lower() for p in identity.weights_dir(stage).iterdir()] if identity.weights_dir(stage).is_dir() else []
    if not (any("dataset113" in n for n in names) and any("dataset115" in n for n in names)):
        raise InstallError("Dataset113/Dataset115 weights missing after extraction")
    return info


class Installer:
    def __init__(self, request: InstallRequest, emit: Emit, *,
                 runner: builder.Runner | None = None,
                 manifest_loader: Callable[[tuple[str, ...]], manifest.Manifest | None] = fetch_manifest,
                 verifier: Callable[[str, Path, str], dict] = verify_runtime,
                 log: Callable[[str], None] = print):
        self.req = request
        self.emit = _never_raising(emit)
        self.runner = runner
        self.manifest_loader = manifest_loader
        self.verifier = verifier
        self.log = log
        self.identity = identity.desired_identity(request.accel)
        self.base = Path(request.base_dir)
        self.target = identity.runtime_dir(self.base, self.identity)
        self.cache = identity.cache_dir(self.base)
        self.stage = self.base / f"_stage-{self.identity.key}"
        self.cancel = threading.Event()

    # ── public ──────────────────────────────────────────────────────────
    def run(self) -> InstallResult:
        t0 = time.time()
        self.base.mkdir(parents=True, exist_ok=True)
        if not self.req.force and identity.runtime_ready(self.target):
            return self._finish("reuse", t0)
        if not self.req.force:
            legacy = identity.adoptable_legacy_runtime(self.base, self.identity)
            if legacy is not None:
                self.emit("ADOPT", f"Reutilizando motor ya instalado ({legacy.name})", 0.5)
                if self.target.exists():
                    shutil.rmtree(self.target, ignore_errors=True)
                replace_with_retry(legacy, self.target, delays=DIR_RETRY_DELAYS)
                return self._finish("adopted", t0, {"from": legacy.name})

        shutil.rmtree(self.stage, ignore_errors=True)
        (self.stage / "site-packages").mkdir(parents=True)
        identity.weights_dir(self.stage).mkdir(parents=True)
        errors = []
        for source in ("offline", "prebuilt", "build"):
            try:
                if getattr(self, f"_from_{source}")():
                    info = self._verify()
                    self._activate(source)
                    return self._finish(source, t0, {"verify": info, "errors_before": errors})
            except Exception as exc:                 # noqa: BLE001 - fall through to the next source
                errors.append(f"{source}: {type(exc).__name__}: {exc}")
                self.log(f"[engine] source {source} failed: {exc}")
                shutil.rmtree(self.stage, ignore_errors=True)
                (self.stage / "site-packages").mkdir(parents=True)
                identity.weights_dir(self.stage).mkdir(parents=True)
        shutil.rmtree(self.stage, ignore_errors=True)
        raise InstallError("no installation source succeeded: " + " || ".join(errors))

    # ── sources ─────────────────────────────────────────────────────────
    def _from_offline(self) -> bool:
        payload = self.req.offline_payload_dir
        mf = Path(payload) / "OFFLINE_PAYLOAD_MANIFEST.json" if payload else None
        if not mf or not mf.is_file() or self.identity.accel != "cuda126":
            return False
        data = json.loads(mf.read_text(encoding="utf-8"))
        if str(data.get("python_abi", "")).replace("py", "cp") != self.identity.python_abi:
            return False
        files = data.get("files", {})
        paths = {k: Path(payload) / files.get(k, {}).get("path", "") for k in ("runtime_archive", "dataset113", "dataset115")}
        if not all(p.is_file() for p in paths.values()):
            return False
        for key, path in paths.items():
            expected = str(files[key].get("sha256", "") or "")
            if expected and download.sha256_file(path) != expected:
                raise InstallError(f"offline payload {path.name}: SHA-256 mismatch")
        self.emit("EXTRACT", "Extrayendo motor incluido en el ZIP…", 0.6)
        self._extract_site(paths["runtime_archive"])
        for key in ("dataset113", "dataset115"):
            archive.safe_extract(paths[key], identity.weights_dir(self.stage))
        return True

    def _from_prebuilt(self) -> bool:
        mf = self.manifest_loader(tuple(self.req.manifest_urls))
        if mf is None:
            return False
        try:
            assets = mf.assets_for(self.identity.platform, self.identity.python_abi, self.identity.accel)
        except manifest.ManifestError as exc:
            self.log(f"[engine] {exc}")
            return False
        self._download_and_extract(assets, 0.05, 0.80, "Descargando motor precompilado")
        return True

    def _from_build(self) -> bool:
        if not self.req.allow_build:
            return False
        runner = self.runner or builder.subprocess_runner(
            self.base / "install.log", heartbeat=lambda line: self.emit(
                "BUILD", "Instalando PyTorch + TotalSegmentator (uv)…" + (f" · {line[:90]}" if line else ""), 0.4))
        weights_error: list[BaseException] = []

        mf = self.manifest_loader(tuple(self.req.manifest_urls))
        published = {a.id: a for a in mf.weights_assets()} if mf is not None else {}
        weights = [published.get(w.id, w) for w in OFFICIAL_WEIGHTS]     # manifest mirrors win, official fill gaps

        def fetch_weights():
            try:
                self._download_and_extract(weights, 0.05, 0.35, "Descargando modelos dentales", emit_progress=False)
            except BaseException as exc:          # noqa: BLE001
                weights_error.append(exc)

        worker = threading.Thread(target=fetch_weights, daemon=True)
        worker.start()                               # weights download while uv installs
        tool = builder.build_site_packages(
            self.req.python, self.stage / "site-packages", self.identity.accel, self.cache, runner,
            locks_dir=self.req.locks_dir, platform=self.identity.platform,
            python_abi=self.identity.python_abi, log=self.log)
        self.emit("BUILD", f"Motor instalado con {tool} · esperando modelos…", 0.8)
        worker.join()
        if weights_error:
            raise weights_error[0]
        return True

    # ── helpers ─────────────────────────────────────────────────────────
    def _download_and_extract(self, assets, p0: float, p1: float, label: str, emit_progress: bool = True):
        def progress(done, total, name):
            if emit_progress and total:
                self.emit("DOWNLOAD", f"{label} · {done / 1e6:,.0f}/{total / 1e6:,.0f} MB", p0 + (p1 - p0) * 0.85 * done / total,
                          bytes_done=done, bytes_total=total, current=name)
        files = download.download_assets(assets, self.cache / "downloads", workers=self.req.workers,
                                         progress=progress, cancel=self.cancel)
        for index, asset in enumerate(assets):
            if emit_progress:
                self.emit("EXTRACT", f"Extrayendo {asset.id}…", p0 + (p1 - p0) * (0.85 + 0.15 * index / len(assets)))
            if asset.install == "weights":
                archive.safe_extract(files[asset.id], identity.weights_dir(self.stage))
            else:
                self._extract_site(files[asset.id])

    def _extract_site(self, zip_path: Path):
        tmp = self.stage / "_extract"
        shutil.rmtree(tmp, ignore_errors=True)
        archive.safe_extract(zip_path, tmp)
        source = tmp / "site-packages" if (tmp / "site-packages").is_dir() else tmp
        dest = self.stage / "site-packages"
        for item in list(source.iterdir()):
            target = dest / item.name
            if target.exists():                      # layered archives may share dist-info dirs
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
            shutil.move(str(item), str(target))
        shutil.rmtree(tmp, ignore_errors=True)

    def _verify(self) -> dict:
        self.emit("VERIFY", "Verificando PyTorch, nnU-Net y TotalSegmentator…", 0.92)
        home = self.stage / "totalseg_home"
        home.mkdir(parents=True, exist_ok=True)
        (home / "config.json").write_text(json.dumps(
            {"totalseg_id": "dsg_offline", "send_usage_stats": False, "prediction_counter": 0}), encoding="utf-8")
        return self.verifier(self.req.python, self.stage, self.identity.accel)

    def _activate(self, source: str):
        self.emit("ACTIVATE", "Activando motor…", 0.97)
        old = self.base / f"_old-{self.identity.key}"
        shutil.rmtree(old, ignore_errors=True)
        if self.target.exists():
            replace_with_retry(self.target, old, delays=DIR_RETRY_DELAYS)
        replace_with_retry(self.stage, self.target, delays=DIR_RETRY_DELAYS)
        shutil.rmtree(old, ignore_errors=True)
        if not self.req.keep_downloads:
            for sub in ("downloads", "uv", "pip"):
                shutil.rmtree(self.cache / sub, ignore_errors=True)

    def _finish(self, source: str, t0: float, details: dict | None = None) -> InstallResult:
        identity.write_active(self.base, self.identity, source)
        removed = []
        for path in identity.removable_runtime_dirs(self.base, self.identity.key):
            if identity.remove_tree(path):
                removed.append(path.name)
        result = InstallResult(source, self.identity.key, self.target, time.time() - t0,
                               dict(details or {}, removed_old_runtimes=removed))
        self.emit("READY", f"Motor listo ✓ · {self.identity.accel.upper()} · {source}", 1.0, done=True,
                  running=False, source=source, seconds=round(result.seconds, 1), removed=removed)
        return result
