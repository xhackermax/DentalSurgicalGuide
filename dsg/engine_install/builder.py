"""Local build fallback: install the engine with ``uv`` (fast) or ``pip``.

Used only when no prebuilt archive is reachable. Measured on the same network
(Python 3.13, cold caches): ``uv`` 38 s vs ``pip`` 138 s for the full
TotalSegmentator + PyTorch runtime.

One single resolution installs PyTorch *and* TotalSegmentator: two separate
``pip --target`` runs (as before 9.7.3) cannot see each other's packages, so
the second run could replace the CUDA build of PyTorch with PyPI's.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Callable, Sequence

from .identity import TORCH_VERSION, TOTALSEG_VERSION

UV_VERSION = "0.12.19"
PYPI_INDEX = "https://pypi.org/simple"
TORCH_INDEXES = {
    "cuda126": "https://download.pytorch.org/whl/cu126",
    "cpu": "https://download.pytorch.org/whl/cpu",
}
Runner = Callable[[Sequence[str], dict | None], int]


def torch_requirement(accel: str) -> str:
    return f"torch=={TORCH_VERSION}+cu126" if accel == "cuda126" else f"torch=={TORCH_VERSION}"


def requirements(accel: str) -> list[str]:
    return [torch_requirement(accel), f"TotalSegmentator=={TOTALSEG_VERSION}"]


def _uv_binary(root: Path) -> Path | None:
    for name in ("uv.exe", "uv"):
        for candidate in Path(root).rglob(name):
            if candidate.is_file() and candidate.parent.name in ("bin", "Scripts", "scripts"):
                return candidate
    return None


def ensure_uv(python: str, cache: Path, run: Runner) -> Path | None:
    """uv binary from the shared cache, bootstrapped once with pip (≈15 MB)."""
    root = Path(cache) / "uv-tool"
    found = _uv_binary(root)
    if found:
        return found
    code = run([python, "-m", "pip", "install", "--disable-pip-version-check", "--no-input",
                "--target", str(root), f"uv=={UV_VERSION}"], None)
    return _uv_binary(root) if code == 0 else None


def uv_command(uv: Path, python: str, target: Path, accel: str, cache: Path,
               lock_file: Path | None = None) -> list[str]:
    cmd = [str(uv), "pip", "install", "--python", python, "--target", str(target),
           "--cache-dir", str(Path(cache) / "uv"), "--link-mode", "copy",
           "--index-url", TORCH_INDEXES[accel], "--extra-index-url", PYPI_INDEX,
           "--index-strategy", "unsafe-best-match"]
    if lock_file is not None:
        return cmd + ["--require-hashes", "--no-deps", "-r", str(lock_file)]
    return cmd + requirements(accel)


def pip_command(python: str, target: Path, accel: str, cache: Path,
                lock_file: Path | None = None) -> list[str]:
    cmd = [python, "-m", "pip", "install", "--disable-pip-version-check", "--no-input",
           "--prefer-binary", "--target", str(target), "--cache-dir", str(Path(cache) / "pip"),
           "--index-url", PYPI_INDEX, "--extra-index-url", TORCH_INDEXES[accel]]
    if lock_file is not None:
        return cmd + ["--require-hashes", "--no-deps", "-r", str(lock_file)]
    return cmd + requirements(accel)


def lock_file_for(locks_dir: Path, platform: str, python_abi: str, accel: str) -> Path | None:
    candidate = Path(locks_dir) / f"{platform}-{python_abi}-{accel}.txt"
    return candidate if candidate.is_file() else None


def build_site_packages(python: str, target: Path, accel: str, cache: Path, run: Runner, *,
                        locks_dir: Path | None = None, platform: str = "", python_abi: str = "",
                        log: Callable[[str], None] = print) -> str:
    """Install into ``target``; returns the tool used ('uv' or 'pip')."""
    target.mkdir(parents=True, exist_ok=True)
    lock = lock_file_for(locks_dir, platform, python_abi, accel) if locks_dir else None
    env = dict(os.environ, PYTHONNOUSERSITE="1")
    uv = ensure_uv(python, cache, run)
    if uv is not None:
        log(f"installing with uv ({'lock file' if lock else 'pinned versions'})")
        if run(uv_command(uv, python, target, accel, cache, lock), env) == 0:
            return "uv"
        log("uv failed: falling back to pip")
    if run(pip_command(python, target, accel, cache, lock), env) == 0:
        return "pip"
    raise RuntimeError("both uv and pip failed to install the AI engine (see install.log)")


def subprocess_runner(log_path: Path, heartbeat: Callable[[str], None] | None = None,
                      timeout: float = 7200.0) -> Runner:
    """Runner that streams child output to ``log_path`` and keeps a heartbeat."""
    import threading
    import time

    def run(cmd: Sequence[str], env: dict | None) -> int:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        with open(log_path, "a", encoding="utf-8", errors="replace") as log:
            log.write("\n> " + " ".join(map(str, cmd)) + "\n")
            log.flush()
            proc = subprocess.Popen(list(map(str, cmd)), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL, env=env, text=True, encoding="utf-8",
                                    errors="replace", creationflags=flags)
            last = {"line": ""}

            def pump():
                assert proc.stdout is not None
                for line in proc.stdout:
                    log.write(line)
                    last["line"] = line.strip()[-160:]
                log.flush()

            reader = threading.Thread(target=pump, daemon=True)
            reader.start()
            started = time.time()
            while proc.poll() is None:
                if heartbeat:
                    heartbeat(last["line"])
                if time.time() - started > timeout:
                    proc.kill()
                    return 124
                time.sleep(0.5)
            reader.join(timeout=5)
            return int(proc.returncode or 0)

    return run
