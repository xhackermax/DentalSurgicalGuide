"""Engine manifest, schema 2.

Published at ``engines/manifest-v2.json`` in the DSG GitHub repository (the
schema-1 ``manifest.json`` stays untouched for DSG ≤ 9.2 clients). Example::

    {
      "schema_version": 2,
      "engine": {"totalseg": "2.18.0", "torch": "2.8.0"},
      "profiles": {
        "win_amd64": {"cp313": {"cuda126": ["rt_torch_cu126", "rt_core", "w113", "w115"],
                                 "cpu":     ["rt_torch_cpu",   "rt_core", "w113", "w115"]}}
      },
      "assets": {
        "w113": {
          "install": "weights", "size": 232066830, "sha256": "…",
          "parts": [{"name": "Dataset113_ToothFairy3.zip", "size": …, "sha256": "…",
                     "urls": ["https://github.com/…", "gdrive:<file-id>"]}]
        }
      }
    }

* ``install`` is ``site-packages`` (extracted into the runtime's site-packages)
  or ``weights`` (extracted into totalseg_home/nnunet/results).
* An asset may be split into parts (GitHub release assets must be < 2 GiB).
  Parts are concatenated in order and the whole is verified with ``sha256``.
* Every part lists mirrors in priority order; ``gdrive:<id>`` is expanded to a
  direct Google Drive download URL.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Iterable

SCHEMA_VERSION = 2
INSTALL_TARGETS = ("site-packages", "weights")
DEFAULT_MANIFEST_URLS = (
    "https://raw.githubusercontent.com/xhackermax/DentalSurgicalGuide/main/engines/manifest-v2.json",
)


class ManifestError(ValueError):
    pass


@dataclass(frozen=True)
class Part:
    name: str
    size: int
    sha256: str
    urls: tuple[str, ...]


@dataclass(frozen=True)
class Asset:
    id: str
    install: str
    size: int
    sha256: str
    parts: tuple[Part, ...]
    description: str = ""

    @property
    def filename(self) -> str:
        return self.parts[0].name if len(self.parts) == 1 else self.id + ".zip"


@dataclass
class Manifest:
    engine: dict
    profiles: dict
    assets: dict[str, Asset] = field(default_factory=dict)

    def assets_for(self, platform: str, python_abi: str, accel: str) -> list[Asset]:
        try:
            ids = self.profiles[platform][python_abi][accel]
        except KeyError as exc:
            raise ManifestError(f"no prebuilt engine for {platform}/{python_abi}/{accel}") from exc
        missing = [i for i in ids if i not in self.assets]
        if missing:
            raise ManifestError(f"profile references unknown assets: {missing}")
        return [self.assets[i] for i in ids]

    def weights_assets(self) -> list[Asset]:
        return [a for a in self.assets.values() if a.install == "weights"]


def expand_url(url: str) -> str:
    """``gdrive:<id>`` → direct download URL (large-file confirmation included)."""
    if url.startswith("gdrive:"):
        file_id = url.split(":", 1)[1].strip()
        return f"https://drive.usercontent.google.com/download?id={file_id}&export=download&confirm=t"
    return url


def _require(obj: dict, key: str, kind, where: str):
    value = obj.get(key)
    if not isinstance(value, kind):
        raise ManifestError(f"{where}: '{key}' must be {kind.__name__}")
    return value


def parse(data: dict | str | bytes) -> Manifest:
    if isinstance(data, (str, bytes)):
        try:
            data = json.loads(data)
        except ValueError as exc:
            raise ManifestError(f"manifest is not JSON: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
        raise ManifestError(f"unsupported manifest schema (need {SCHEMA_VERSION})")
    engine = _require(data, "engine", dict, "manifest")
    profiles = _require(data, "profiles", dict, "manifest")
    assets: dict[str, Asset] = {}
    for asset_id, raw in _require(data, "assets", dict, "manifest").items():
        where = f"asset {asset_id}"
        install = _require(raw, "install", str, where)
        if install not in INSTALL_TARGETS:
            raise ManifestError(f"{where}: install must be one of {INSTALL_TARGETS}")
        parts = []
        for index, part in enumerate(_require(raw, "parts", list, where)):
            pw = f"{where} part {index}"
            urls = tuple(str(u) for u in _require(part, "urls", list, pw))
            if not urls:
                raise ManifestError(f"{pw}: needs at least one URL")
            parts.append(Part(str(_require(part, "name", str, pw)), int(part.get("size", 0) or 0),
                              str(part.get("sha256", "") or "").lower(), urls))
        if not parts:
            raise ManifestError(f"{where}: no parts")
        sha = str(raw.get("sha256", "") or "").lower()
        if len(sha) != 64:
            raise ManifestError(f"{where}: sha256 is mandatory (64 hex chars)")
        assets[asset_id] = Asset(asset_id, install, int(raw.get("size", 0) or 0), sha, tuple(parts),
                                 str(raw.get("description", "")))
    return Manifest(engine=engine, profiles=profiles, assets=assets)


def build(engine: dict, profiles: dict, assets: Iterable[Asset]) -> dict:
    """Inverse of :func:`parse` (used by the release tool)."""
    return {
        "schema_version": SCHEMA_VERSION,
        "engine": engine,
        "profiles": profiles,
        "assets": {
            a.id: {
                "install": a.install, "size": a.size, "sha256": a.sha256, "description": a.description,
                "parts": [{"name": p.name, "size": p.size, "sha256": p.sha256, "urls": list(p.urls)}
                          for p in a.parts],
            } for a in assets
        },
    }
