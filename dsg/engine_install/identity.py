"""Runtime identity: *what* is installed, never *which DSG version* installed it.

Before 9.7.3 the runtime folder was named after the add-on release
(``dsg_ts965``, ``dsg_ts967``, ``dsg_ts968``). Every release therefore forced a
multi-GB reinstall although PyTorch and TotalSegmentator were unchanged, and
the old folders (~6 GB each) were never removed.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

TOTALSEG_VERSION = "2.18.0"
TORCH_VERSION = "2.8.0"
CUDA_TAG = "cu126"
ACCELERATORS = ("cuda126", "cpu")
LEGACY_DIR_PATTERN = re.compile(r"^dsg_ts\d+_py\d+$")
ACTIVE_FILE = "active_runtime.json"


@dataclass(frozen=True)
class RuntimeIdentity:
    totalseg: str
    torch: str
    accel: str                 # "cuda126" | "cpu"
    python_abi: str            # "cp313"
    platform: str              # "win_amd64" | "linux_x86_64" | "macosx_arm64"

    def __post_init__(self):
        if self.accel not in ACCELERATORS:
            raise ValueError(f"unknown accelerator {self.accel!r}")

    @property
    def key(self) -> str:
        return f"ts{self.totalseg}-torch{self.torch}-{self.accel}-{self.python_abi}-{self.platform}"

    def as_dict(self) -> dict:
        return {**asdict(self), "key": self.key}


def current_python_abi() -> str:
    return f"cp{sys.version_info.major}{sys.version_info.minor}"


def current_platform() -> str:
    if sys.platform.startswith("win"):
        return "win_amd64"
    if sys.platform == "darwin":
        return "macosx_arm64" if os.uname().machine == "arm64" else "macosx_x86_64"
    return "linux_x86_64"


def choose_accelerator(nvidia_driver_present: bool, override: str | None = None) -> str:
    """CUDA only when an NVIDIA driver exists (macOS never has CUDA)."""
    override = (override or os.environ.get("DSG_AI_ACCEL", "")).strip().lower()
    if override in ACCELERATORS:
        return override
    if current_platform().startswith("macosx"):
        return "cpu"
    return "cuda126" if nvidia_driver_present else "cpu"


def desired_identity(accel: str) -> RuntimeIdentity:
    return RuntimeIdentity(TOTALSEG_VERSION, TORCH_VERSION, accel, current_python_abi(), current_platform())


# ── Runtime folder layout ───────────────────────────────────────────────────
def runtime_dir(base: Path, identity: RuntimeIdentity) -> Path:
    return Path(base) / identity.key


def cache_dir(base: Path) -> Path:
    """Downloads and uv/pip caches: outside the add-on, reused by every update."""
    return Path(base) / "cache"


def site_packages(runtime: Path) -> Path:
    return Path(runtime) / "site-packages"


def weights_dir(runtime: Path) -> Path:
    return Path(runtime) / "totalseg_home" / "nnunet" / "results"


def runtime_ready(runtime: Path) -> bool:
    site = site_packages(runtime)
    if not all((site / pkg).is_dir() for pkg in ("torch", "nnunetv2", "totalsegmentator")):
        return False
    wd = weights_dir(runtime)
    if not wd.is_dir():
        return False
    names = [p.name.lower() for p in wd.iterdir() if p.is_dir()]
    return any("dataset113" in n for n in names) and any("dataset115" in n for n in names)


def installed_torch_accel(runtime: Path) -> str | None:
    """'cuda126' / 'cpu' from torch/version.py of an installed runtime."""
    version_py = site_packages(runtime) / "torch" / "version.py"
    try:
        text = version_py.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    match = re.search(r"cuda\s*(?::\s*\w+(?:\[\w+\])?)?\s*=\s*['\"]([\d.]+)['\"]", text)
    if match:
        return "cuda" + match.group(1).replace(".", "")[:3]
    return "cpu" if "cuda" in text else None


# ── Active pointer (which runtime DSG uses) ─────────────────────────────────
def read_active(base: Path) -> dict:
    try:
        return json.loads((Path(base) / ACTIVE_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_active(base: Path, identity: RuntimeIdentity, source: str) -> None:
    base = Path(base)
    base.mkdir(parents=True, exist_ok=True)
    from .fsio import write_json_atomic
    write_json_atomic(base / ACTIVE_FILE, {**identity.as_dict(), "source": source}, indent=2)


def active_runtime_dir(base: Path) -> Path | None:
    key = read_active(base).get("key")
    if key and (Path(base) / key).is_dir():
        return Path(base) / key
    return None


# ── Legacy runtimes (dsg_tsNNN_pyXY) ────────────────────────────────────────
def legacy_runtime_dirs(base: Path) -> list[Path]:
    base = Path(base)
    if not base.is_dir():
        return []
    dirs = [p for p in base.iterdir() if p.is_dir() and LEGACY_DIR_PATTERN.match(p.name)]
    return sorted(dirs, key=lambda p: p.stat().st_mtime, reverse=True)


def adoptable_legacy_runtime(base: Path, identity: RuntimeIdentity) -> Path | None:
    """Newest legacy runtime that already contains this exact engine."""
    py_suffix = "_py" + identity.python_abi[2:]
    for candidate in legacy_runtime_dirs(base):
        if not candidate.name.endswith(py_suffix):
            continue
        if runtime_ready(candidate) and installed_torch_accel(candidate) == identity.accel:
            return candidate
    return None


def removable_runtime_dirs(base: Path, keep_key: str) -> list[Path]:
    """Every other runtime folder (legacy and old identities); never the cache."""
    base = Path(base)
    if not base.is_dir():
        return []
    out = []
    for p in base.iterdir():
        if not p.is_dir() or p.name in (keep_key, "cache") or p.name.startswith((".", "_")):
            continue
        if LEGACY_DIR_PATTERN.match(p.name) or p.name.startswith("ts"):
            out.append(p)
    return out


def remove_tree(path: Path) -> bool:
    try:
        shutil.rmtree(path)
        return True
    except OSError:
        return False
